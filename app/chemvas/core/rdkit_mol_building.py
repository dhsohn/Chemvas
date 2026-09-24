"""Build an RDKit molecule from a Chemvas model, keeping the atom map and annotations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.core.rdkit_adapter import RDKitAdapter
    from chemvas.domain.document import (
        MoleculeModel,
    )

logger = logging.getLogger(__name__)


class _RDKitMolBuilding:
    adapter: RDKitAdapter

    def _build_rdkit_mol_with_map(self, model: MoleculeModel):
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            return None, None
        Chem, _ = rdkit
        rw = Chem.RWMol()
        atom_annotations = model.atom_annotations
        atom_map = {}
        for atom_id in sorted(model.atoms):
            atom = model.atoms[atom_id]
            formal_charge, radical_electrons = self._annotation_for_atom(
                atom_annotations, atom_id
            )
            # An abbreviation label is not an element here. The table is checked
            # first because "Ts" (tosyl) and "Ac" (acetyl) are also element
            # symbols, so Chem.Atom would happily build tennessine and actinium
            # and report a molecule the drawing never showed. Abbreviations and
            # unknown labels collapse to carbon: this tolerant build only feeds
            # substructure comparison, never an exported structure.
            rd_atom = None
            if atom.element not in self.adapter._alias_smiles:
                try:
                    rd_atom = Chem.Atom(atom.element)
                except Exception:
                    rd_atom = None
            if rd_atom is None:
                rd_atom = Chem.Atom("C")
            self._apply_atom_annotation(
                rd_atom,
                formal_charge=formal_charge,
                radical_electrons=radical_electrons,
            )
            atom_map[atom_id] = rw.AddAtom(rd_atom)
        seen_bonds: set[tuple[int, int]] = set()
        for bond in model.bonds:
            if bond is None or bond.a == bond.b:
                continue
            if bond.a not in atom_map or bond.b not in atom_map:
                continue
            key = (bond.a, bond.b) if bond.a <= bond.b else (bond.b, bond.a)
            if key in seen_bonds:
                continue
            seen_bonds.add(key)
            btype = self._bond_type(Chem, bond.order)
            rw.AddBond(atom_map[bond.a], atom_map[bond.b], btype)
        mol = rw.GetMol()
        # Sanitization is best-effort here: this substructure-comparison path
        # tolerates structures RDKit cannot fully sanitize (e.g. unusual
        # valences from a work-in-progress drawing) so a suggestion can still
        # be made. This deliberately differs from
        # ``_build_conversion_rdkit_mol``, which is strict and aborts on a
        # sanitize error. Keep the tolerant behavior (see
        # test_model_to_rdkit_with_map_tolerant_ignores_invalid_bonds_and_sanitize_errors
        # and test_real_rdkit_smoke_tolerant_build_returns_a_queryable_mol).
        try:
            Chem.SanitizeMol(mol)
        except Exception:
            logger.debug(
                "SanitizeMol failed for tolerant substructure build; continuing.",
                exc_info=True,
            )
            # A failed sanitize leaves the ring cache uninitialized, and every
            # ring-aware query on such a mol then raises a C++ pre-condition
            # violation rather than answering. Tolerating the failure is only
            # useful if the mol handed back is still queryable, so perceive
            # rings here. The valence cache survives the failure and needs no
            # such repair.
            Chem.FastFindRings(mol)
        return mol, atom_map

    def model_to_rdkit_with_map_tolerant(self, model: MoleculeModel):
        return self._build_rdkit_mol_with_map(model)

    @staticmethod
    def _bond_type(Chem, order: int):
        order_map = {
            1: Chem.BondType.SINGLE,
            2: Chem.BondType.DOUBLE,
            3: Chem.BondType.TRIPLE,
        }
        return order_map.get(order, Chem.BondType.SINGLE)

    @staticmethod
    def _annotation_for_atom(
        atom_annotations: Mapping[int, Mapping[str, int]] | None,
        atom_id: int,
    ) -> tuple[int, int]:
        if atom_annotations is None:
            return 0, 0
        annotation = atom_annotations.get(atom_id)
        if annotation is None:
            return 0, 0
        formal_charge = int(annotation.get("formal_charge", 0))
        radical_electrons = int(annotation.get("radical_electrons", 0))
        return formal_charge, radical_electrons

    @staticmethod
    def _format_atom_refs(refs: list[str]) -> str:
        detail = ", ".join(refs[:5])
        if len(refs) > 5:
            detail = f"{detail}, ..."
        return detail

    @staticmethod
    def _apply_atom_annotation(
        rd_atom, *, formal_charge: int, radical_electrons: int
    ) -> None:
        if formal_charge:
            rd_atom.SetFormalCharge(formal_charge)
        if radical_electrons:
            rd_atom.SetNumRadicalElectrons(radical_electrons)
