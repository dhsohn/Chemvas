from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Optional, cast

from core.model import MoleculeModel

if TYPE_CHECKING:
    from core.rdkit_adapter import RDKitAdapter


class RDKitImportHelper:
    def __init__(self, adapter: RDKitAdapter) -> None:
        self.adapter = adapter

    def smiles_to_2d(self, smiles: str, scale: float = 40.0) -> Optional[MoleculeModel]:
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            return None
        Chem, AllChem = rdkit
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            self.adapter.last_error = (
                "Invalid SMILES string. Example: CC(=O)O (acetic acid), "
                "c1ccccc1 (benzene), C1CCCCC1 (cyclohexane)."
            )
            return None
        AllChem.Compute2DCoords(mol)

        conf = mol.GetConformer()
        pos_by_idx = {}
        for atom in mol.GetAtoms():
            pos = conf.GetAtomPosition(atom.GetIdx())
            pos_by_idx[atom.GetIdx()] = (pos.x, pos.y)

        bond_lengths = []
        for bond in mol.GetBonds():
            ax, ay = pos_by_idx[bond.GetBeginAtomIdx()]
            bx, by = pos_by_idx[bond.GetEndAtomIdx()]
            dist = math.hypot(ax - bx, ay - by)
            if dist > 0.0:
                bond_lengths.append(dist)
        if bond_lengths:
            avg_len = sum(bond_lengths) / len(bond_lengths)
        else:
            nearest = []
            positions = list(pos_by_idx.values())
            if len(positions) > 1:
                for index, (x1, y1) in enumerate(positions):
                    min_dist = None
                    for other_index, (x2, y2) in enumerate(positions):
                        if index == other_index:
                            continue
                        dist = math.hypot(x1 - x2, y1 - y2)
                        if dist <= 0.0:
                            continue
                        if min_dist is None or dist < min_dist:
                            min_dist = dist
                    if min_dist is not None:
                        nearest.append(min_dist)
            avg_len = sum(nearest) / len(nearest) if nearest else 0.0
        scale_factor = (scale / avg_len) if avg_len > 0.0 else 1.0

        model = MoleculeModel()
        for atom in mol.GetAtoms():
            x, y = pos_by_idx[atom.GetIdx()]
            model.add_atom(atom.GetSymbol(), x * scale_factor, -y * scale_factor)

        for bond in mol.GetBonds():
            order = int(bond.GetBondTypeAsDouble())
            model.add_bond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(), order)

        return model

    def compute_props(self, model: MoleculeModel) -> tuple[str | None, float | None, str | None]:
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            return None, None, None
        Chem, _ = rdkit
        # Use strict label handling so abbreviation/unsupported atom labels
        # (e.g. Me, Ph, Boc) are not silently substituted with Carbon, which
        # would report a formula/MW that does not match the drawn structure.
        # When such a label is present the conversion returns ``None`` and we
        # leave formula/MW blank instead of showing a misleading value.
        mol = self.adapter.model_to_rdkit(model, strict_labels=True)
        if mol is None:
            return None, None, None
        try:
            mol_h = Chem.AddHs(mol)
            from rdkit.Chem import Descriptors, rdMolDescriptors

            formula = rdMolDescriptors.CalcMolFormula(mol_h)
            mw = cast(Any, Descriptors).MolWt(mol_h)
            smiles = Chem.MolToSmiles(mol, canonical=True)
            return formula, mw, smiles
        except Exception:
            return None, None, None

    def get_name_from_smiles(self, smiles: str) -> str | None:
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            return None
        Chem, _ = rdkit
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            canonical = Chem.MolToSmiles(mol, canonical=True)
            return self.adapter._name_map.get(canonical)
        except Exception:
            return None


__all__ = ["RDKitImportHelper"]
