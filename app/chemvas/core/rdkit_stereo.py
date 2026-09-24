"""Assign drawn wedge and double-bond stereochemistry to a conversion molecule."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.core.rdkit_adapter import RDKitAdapter
    from chemvas.domain.document import (
        Bond,
        MoleculeModel,
    )

logger = logging.getLogger(__name__)


class _RDKitStereo:
    adapter: RDKitAdapter

    def _assign_conversion_stereo(self, mol, Chem) -> None:
        try:
            if hasattr(Chem, "AssignChiralTypesFromBondDirs"):
                Chem.AssignChiralTypesFromBondDirs(mol)
            if hasattr(Chem, "SetBondStereoFromDirections"):
                Chem.SetBondStereoFromDirections(mol)
            if hasattr(Chem, "AssignStereochemistry"):
                Chem.AssignStereochemistry(mol, force=True, cleanIt=True)
        except Exception:
            logger.debug(
                "Stereochemistry assignment for conversion failed; continuing.",
                exc_info=True,
            )

    @staticmethod
    def _unambiguous_double_depiction(
        model: MoleculeModel, bond: Bond, adjacency: dict[int, list[int]]
    ) -> bool:
        """Require visible, separated substituent sides at both drawn endpoints."""
        # Match RDKit's two-degree near-linear depiction tolerance. Check both
        # directions (including coincident/overlapping substituents), rather
        # than letting a degenerate drawing choose a stereo-controlling bond.
        minimum_sine = math.sin(math.radians(2.0))
        for atom_id, other_id in ((bond.a, bond.b), (bond.b, bond.a)):
            atom, other = model.atoms[atom_id], model.atoms[other_id]
            axis_x, axis_y = other.x - atom.x, other.y - atom.y
            axis_length = math.hypot(axis_x, axis_y)
            neighbors = set(adjacency[atom_id]) - {other_id}
            if axis_length == 0.0 or not 1 <= len(neighbors) <= 2:
                return False
            sides = []
            for neighbor_id in neighbors:
                neighbor = model.atoms[neighbor_id]
                dx, dy = neighbor.x - atom.x, neighbor.y - atom.y
                length = math.hypot(dx, dy)
                cross = axis_x * dy - axis_y * dx
                if length == 0.0 or abs(cross) <= minimum_sine * axis_length * length:
                    return False
                sides.append(cross > 0.0)
            if len(sides) == 2 and sides[0] == sides[1]:
                return False
        return True

    def _assign_drawn_double_stereo(
        self, mol, Chem, model: MoleculeModel, valid_bonds, atom_map, adjacency
    ) -> bool:
        """Perceive ordinary drawn C=C/C=N without changing wedge/hash owners."""
        drawn = [
            (bond_id, bond)
            for bond_id, bond in valid_bonds
            if bond.order == 2
            and bond.style != "double_either"
            and {model.atoms[bond.a].element, model.atoms[bond.b].element}
            in ({"C"}, {"C", "N"})
        ]
        if not drawn:
            return True
        try:
            potential = {
                info.centeredOn
                for info in Chem.FindPotentialStereo(mol)
                if info.type == Chem.StereoType.Bond_Double
            }
            if not potential:
                return True
            candidates = []
            for bond_id, bond in drawn:
                rd_bond = mol.GetBondBetweenAtoms(atom_map[bond.a], atom_map[bond.b])
                if rd_bond.GetIdx() not in potential:
                    continue
                if not self._unambiguous_double_depiction(model, bond, adjacency):
                    self.adapter.last_error = (
                        f"Cannot determine drawn double-bond stereochemistry for "
                        f"bond {bond_id} (atoms {bond.a}-{bond.b}): ambiguous "
                        "substituent positions. Correct the drawing or use an "
                        "explicitly unspecified crossed double bond (double_either)."
                    )
                    return False
                candidates.append((bond_id, bond))
            if not candidates:
                return True
            # RDKit's conformer-aware neighbour-direction API is also used by
            # its molfile stereo reader. Work on a clone: temporary directions
            # must not consume or replace the original tetrahedral wedges.
            probe = Chem.Mol(mol)
            for rd_bond in probe.GetBonds():
                if rd_bond.GetBondDir() in (
                    Chem.BondDir.BEGINWEDGE,
                    Chem.BondDir.BEGINDASH,
                ):
                    rd_bond.SetBondDir(Chem.BondDir.NONE)
            Chem.SetDoubleBondNeighborDirections(probe, probe.GetConformer())
            Chem.SetBondStereoFromDirections(probe)
            Chem.AssignStereochemistry(probe, force=True, cleanIt=True)
            for bond_id, bond in candidates:
                a, b = atom_map[bond.a], atom_map[bond.b]
                perceived = probe.GetBondBetweenAtoms(a, b)
                if perceived.GetStereo() not in (
                    Chem.BondStereo.STEREOE,
                    Chem.BondStereo.STEREOZ,
                ):
                    self.adapter.last_error = (
                        f"Cannot determine drawn double-bond stereochemistry for "
                        f"bond {bond_id} (atoms {bond.a}-{bond.b}). Correct the "
                        "drawing or use an explicitly unspecified crossed double "
                        "bond (double_either)."
                    )
                    return False
                original = mol.GetBondBetweenAtoms(a, b)
                original.SetStereoAtoms(*perceived.GetStereoAtoms())
                original.SetStereo(perceived.GetStereo())
        except Exception as exc:
            self.adapter.last_error = (
                "Cannot determine drawn double-bond stereochemistry: " + str(exc)
            )
            return False
        return True

    def _consistent_conversion_wedges(
        self,
        mol,
        Chem,
        valid_bonds: list[tuple[int, Bond]],
        atom_map: dict[int, int],
    ) -> bool:
        """Require redundant directions to agree independently at their narrow end."""
        by_start: dict[int, list[tuple[int, Bond]]] = {}
        for bond_id, bond in valid_bonds:
            if bond.style in {"wedge", "hash"}:
                by_start.setdefault(bond.a, []).append((bond_id, bond))
        for atom_id, directed in by_start.items():
            if len(directed) < 2:
                continue
            atom_idx = atom_map[atom_id]
            expected = mol.GetAtomWithIdx(atom_idx).GetChiralTag()
            for chosen_id, _chosen in directed:
                # RDKit may consume just one of several directions; changing
                # bond storage order must not choose the opposite enantiomer.
                # Each clone retains the same neighbour order, so local chiral
                # tags can be compared without relying on CIP priority labels.
                probe = Chem.Mol(mol)
                probe.GetAtomWithIdx(atom_idx).SetChiralTag(
                    Chem.ChiralType.CHI_UNSPECIFIED
                )
                for bond_id, bond in directed:
                    if bond_id != chosen_id:
                        probe.GetBondBetweenAtoms(
                            atom_idx, atom_map[bond.b]
                        ).SetBondDir(Chem.BondDir.NONE)
                self._assign_conversion_stereo(probe, Chem)
                if probe.GetAtomWithIdx(atom_idx).GetChiralTag() != expected:
                    bond_ids = ", ".join(str(bond_id) for bond_id, _ in directed)
                    self.adapter.last_error = (
                        f"Conflicting wedge/hash directions at atom {atom_id}: "
                        f"bonds {bond_ids} do not independently define the same "
                        "tetrahedral stereochemistry. Correct the directions "
                        "before chemical conversion."
                    )
                    return False
        return True
