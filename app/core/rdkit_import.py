from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, cast

from core.model import MoleculeModel
from core.rdkit_types import MoleculeIdentifiers

if TYPE_CHECKING:
    from core.rdkit_adapter import RDKitAdapter


class RDKitImportHelper:
    def __init__(self, adapter: RDKitAdapter) -> None:
        self.adapter = adapter

    def smiles_to_2d(self, smiles: str, scale: float = 40.0) -> MoleculeModel | None:
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
        mol = self._kekulized_import_mol(Chem, mol)
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
        atom_id_by_rd_idx: dict[int, int] = {}
        for atom in mol.GetAtoms():
            x, y = pos_by_idx[atom.GetIdx()]
            atom_id = model.add_atom(atom.GetSymbol(), x * scale_factor, -y * scale_factor)
            atom_id_by_rd_idx[atom.GetIdx()] = atom_id
            annotation = self._atom_annotation(atom)
            if annotation:
                model.atom_annotations[atom_id] = annotation

        for bond in mol.GetBonds():
            order = self._bond_order_for_import(bond)
            model.add_bond(
                atom_id_by_rd_idx[bond.GetBeginAtomIdx()],
                atom_id_by_rd_idx[bond.GetEndAtomIdx()],
                order,
            )

        return model

    @staticmethod
    def _kekulized_import_mol(Chem, mol):
        try:
            has_aromatic_bond = any(
                bool(getattr(bond, "GetIsAromatic", lambda: False)())
                or abs(float(bond.GetBondTypeAsDouble()) - 1.5) < 1e-6
                for bond in mol.GetBonds()
            )
        except Exception:
            return mol
        if not has_aromatic_bond or not hasattr(Chem, "Kekulize"):
            return mol
        try:
            import_mol = Chem.Mol(mol) if hasattr(Chem, "Mol") else mol
            Chem.Kekulize(import_mol, clearAromaticFlags=True)
            return import_mol
        except Exception:
            return mol

    @staticmethod
    def _bond_order_for_import(bond) -> int:
        try:
            order_value = float(bond.GetBondTypeAsDouble())
        except Exception:
            return 1
        if abs(order_value - 1.5) < 1e-6 or bool(getattr(bond, "GetIsAromatic", lambda: False)()):
            return 2
        order = round(order_value)
        return max(1, min(3, order))

    @staticmethod
    def _atom_annotation(atom) -> dict[str, int]:
        annotation: dict[str, int] = {}
        formal_charge_getter = getattr(atom, "GetFormalCharge", None)
        if callable(formal_charge_getter):
            formal_charge = int(formal_charge_getter())
            if formal_charge:
                annotation["formal_charge"] = formal_charge
        radical_getter = getattr(atom, "GetNumRadicalElectrons", None)
        if callable(radical_getter):
            radical_electrons = int(radical_getter())
            if radical_electrons:
                annotation["radical_electrons"] = radical_electrons
        return annotation

    def compute_props(self, model: MoleculeModel) -> tuple[str | None, float | None, str | None]:
        identifiers = self.compute_identifiers(model)
        return identifiers.formula, identifiers.mw, identifiers.smiles

    def compute_identifiers(self, model: MoleculeModel) -> MoleculeIdentifiers:
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            return MoleculeIdentifiers()
        Chem, _ = rdkit
        # Use strict label handling so abbreviation/unsupported atom labels
        # (e.g. Me, Ph, Boc) are not silently substituted with Carbon, which
        # would report identifiers that do not match the drawn structure. When
        # such a label is present the conversion returns ``None`` and we leave
        # the identifiers blank instead of showing a misleading value.
        mol = self.adapter.model_to_rdkit_strict_labels(model)
        if mol is None:
            return MoleculeIdentifiers()
        try:
            mol_h = Chem.AddHs(mol)
            from rdkit.Chem import Descriptors, rdMolDescriptors

            formula = rdMolDescriptors.CalcMolFormula(mol_h)
            mw = cast(Any, Descriptors).MolWt(mol_h)
            smiles = Chem.MolToSmiles(mol, canonical=True)
        except Exception:
            return MoleculeIdentifiers()
        # InChI is computed separately so that a failure in the InChI backend
        # cannot blank out the formula/MW/SMILES we already have.
        try:
            inchi = Chem.MolToInchi(mol) or None
            inchikey = Chem.MolToInchiKey(mol) or None
        except Exception:
            inchi = None
            inchikey = None
        return MoleculeIdentifiers(
            formula=formula,
            mw=mw,
            smiles=smiles,
            inchi=inchi,
            inchikey=inchikey,
        )

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
