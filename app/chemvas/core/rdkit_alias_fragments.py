"""Expand alias labels (Ph, OMe, ...) into RDKit fragments during conversion."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from chemvas.domain.atom_aliases import (
    alias_attachment_error,
    alias_attachments_for_atom,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.core.rdkit_adapter import RDKitAdapter
    from chemvas.domain.document import (
        MoleculeModel,
    )
from chemvas.core.rdkit_mol_building import _RDKitMolBuilding

logger = logging.getLogger(__name__)


class _RDKitAliasFragments(_RDKitMolBuilding):
    adapter: RDKitAdapter

    def _parse_alias_fragment(
        self,
        label: str,
        *,
        atom_id: int,
        neighbors: list[int],
        Chem,
        AllChem,
    ) -> tuple[object, int, int] | None:
        """Expand the alias SMILES; (fragment, dummy_idx, attachment_idx) or None."""
        alias_smiles = self.adapter._alias_smiles.get(label)
        if alias_smiles is None:
            return None
        if len(neighbors) != 1:
            self.adapter.last_error = (
                f"Alias label '{label}' on atom {atom_id} requires exactly one attachment bond "
                f"for 3D conversion, but found {len(neighbors)}."
            )
            return None
        fragment = Chem.MolFromSmiles(alias_smiles)
        if fragment is None:
            self.adapter.last_error = (
                f"Failed to expand alias label '{label}' for 3D conversion."
            )
            return None
        if hasattr(AllChem, "Compute2DCoords"):
            try:
                AllChem.Compute2DCoords(fragment)
            except Exception:
                logger.debug(
                    "Compute2DCoords for alias fragment '%s' failed; continuing.",
                    label,
                    exc_info=True,
                )
        dummy_atoms = [
            frag_atom
            for frag_atom in fragment.GetAtoms()
            if frag_atom.GetAtomicNum() == 0
        ]
        if len(dummy_atoms) != 1:
            self.adapter.last_error = (
                f"Alias label '{label}' has an invalid attachment definition."
            )
            return None
        dummy_atom = dummy_atoms[0]
        dummy_neighbors = list(dummy_atom.GetNeighbors())
        if len(dummy_neighbors) != 1:
            self.adapter.last_error = (
                f"Alias label '{label}' has an invalid attachment topology."
            )
            return None
        return fragment, dummy_atom.GetIdx(), dummy_neighbors[0].GetIdx()

    def _copy_alias_fragment_into(
        self,
        fragment,
        *,
        dummy_idx: int,
        attachment_idx: int,
        formal_charge: int,
        radical_electrons: int,
        rw,
        Chem,
    ) -> tuple[dict[int, int], int | None]:
        """Copy fragment atoms/bonds (minus the dummy) into ``rw``."""
        fragment_map: dict[int, int] = {}
        attachment_new_idx = None
        for frag_atom in fragment.GetAtoms():
            if frag_atom.GetIdx() == dummy_idx:
                continue
            new_atom = Chem.Atom(frag_atom)
            if frag_atom.GetIdx() == attachment_idx:
                self._apply_atom_annotation(
                    new_atom,
                    formal_charge=formal_charge,
                    radical_electrons=radical_electrons,
                )
            new_idx = rw.AddAtom(new_atom)
            fragment_map[frag_atom.GetIdx()] = new_idx
            if frag_atom.GetIdx() == attachment_idx:
                attachment_new_idx = new_idx
        for frag_bond in fragment.GetBonds():
            begin_idx = frag_bond.GetBeginAtomIdx()
            end_idx = frag_bond.GetEndAtomIdx()
            if dummy_idx in {begin_idx, end_idx}:
                continue
            rw.AddBond(
                fragment_map[begin_idx], fragment_map[end_idx], frag_bond.GetBondType()
            )
        return fragment_map, attachment_new_idx

    def _alias_fragment_coords(
        self,
        fragment,
        *,
        label: str,
        atom,
        neighbors: list[int],
        model: MoleculeModel,
        dummy_idx: int,
        attachment_idx: int,
        fragment_map: dict[int, int],
        attachment_new_idx: int,
    ) -> dict[int, tuple[float, float]] | None:
        """Place fragment atoms around ``atom``, aligned toward its neighbor."""
        conf = fragment.GetConformer() if fragment.GetNumConformers() else None
        if conf is None:
            return {attachment_new_idx: (atom.x, atom.y)}

        dummy_pos = conf.GetAtomPosition(dummy_idx)
        attach_pos = conf.GetAtomPosition(attachment_idx)
        source_dx = dummy_pos.x - attach_pos.x
        source_dy = dummy_pos.y - attach_pos.y
        neighbor_atom = model.atoms.get(neighbors[0])
        if neighbor_atom is None:
            self.adapter.last_error = (
                f"Alias label '{label}' is attached to a missing atom."
            )
            return None
        target_dx = neighbor_atom.x - atom.x
        target_dy = neighbor_atom.y - atom.y
        source_angle = (
            math.atan2(source_dy, source_dx)
            if abs(source_dx) > 1e-6 or abs(source_dy) > 1e-6
            else 0.0
        )
        target_angle = (
            math.atan2(target_dy, target_dx)
            if abs(target_dx) > 1e-6 or abs(target_dy) > 1e-6
            else 0.0
        )
        rotation = target_angle - source_angle
        cos_theta = math.cos(rotation)
        sin_theta = math.sin(rotation)
        coord_map: dict[int, tuple[float, float]] = {}
        for frag_atom in fragment.GetAtoms():
            if frag_atom.GetIdx() == dummy_idx:
                continue
            frag_pos = conf.GetAtomPosition(frag_atom.GetIdx())
            rel_x = frag_pos.x - attach_pos.x
            rel_y = frag_pos.y - attach_pos.y
            rot_x = rel_x * cos_theta - rel_y * sin_theta
            rot_y = rel_x * sin_theta + rel_y * cos_theta
            coord_map[fragment_map[frag_atom.GetIdx()]] = (
                atom.x + rot_x,
                atom.y + rot_y,
            )
        return coord_map

    def _build_alias_fragment(
        self,
        label: str,
        *,
        atom_id: int,
        atom,
        neighbors: list[int],
        model: MoleculeModel,
        formal_charge: int,
        radical_electrons: int,
        annotation: Mapping[str, int] | None = None,
        rw,
        Chem,
        AllChem,
    ) -> tuple[int | None, dict[int, tuple[float, float]] | None]:
        attachment_error = alias_attachment_error(
            label,
            atom_id=atom_id,
            attachments=alias_attachments_for_atom(model, atom_id),
            annotation=annotation,
        )
        if attachment_error is not None:
            self.adapter.last_error = attachment_error
            return None, None
        parsed = self._parse_alias_fragment(
            label,
            atom_id=atom_id,
            neighbors=neighbors,
            Chem=Chem,
            AllChem=AllChem,
        )
        if parsed is None:
            return None, None
        fragment, dummy_idx, attachment_idx = parsed
        fragment_map, attachment_new_idx = self._copy_alias_fragment_into(
            fragment,
            dummy_idx=dummy_idx,
            attachment_idx=attachment_idx,
            formal_charge=formal_charge,
            radical_electrons=radical_electrons,
            rw=rw,
            Chem=Chem,
        )
        if attachment_new_idx is None:
            self.adapter.last_error = f"Alias label '{label}' could not be attached."
            return None, None
        coord_map = self._alias_fragment_coords(
            fragment,
            label=label,
            atom=atom,
            neighbors=neighbors,
            model=model,
            dummy_idx=dummy_idx,
            attachment_idx=attachment_idx,
            fragment_map=fragment_map,
            attachment_new_idx=attachment_new_idx,
        )
        if coord_map is None:
            return None, None
        return attachment_new_idx, coord_map
