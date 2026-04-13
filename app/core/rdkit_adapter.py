from __future__ import annotations

import math
from typing import Optional

from core.model import MoleculeModel


class RDKitAdapter:
    def __init__(self) -> None:
        self._rdkit = None
        self.last_error: str | None = None
        self._name_map = {
            "c1ccccc1": "Benzene",
            "C1CCCCC1": "Cyclohexane",
            "C1CCCC1": "Cyclopentane",
            "C1CCC1": "Cyclobutane",
            "C1CC1": "Cyclopropane",
            "c1cccc2ccccc12": "Naphthalene",
            "c1ccc2cc3ccccc3cc2c1": "Anthracene",
            "c1ccc2c(c1)ccc3ccccc23": "Phenanthrene",
            "n1ccccc1": "Pyridine",
            "n1ccnc(n1)": "Pyrimidine",
            "c1ncc[nH]1": "Imidazole",
            "c1cc[nH]c1": "Pyrrole",
            "o1cccc1": "Furan",
            "s1cccc1": "Thiophene",
            "c1ccc2[nH]cc2c1": "Indole",
            "c1ccc2ncccc2c1": "Quinoline",
            "c1ccc2cccnc2c1": "Isoquinoline",
            "c1ccc2[nH]nc2c1": "Benzimidazole",
        }

    def _load_rdkit(self):
        if self._rdkit is None:
            try:
                from rdkit import Chem
                from rdkit import RDLogger
                from rdkit.Chem import AllChem
            except Exception:
                self.last_error = "RDKit is not available in this environment."
                return None, None
            RDLogger.DisableLog("rdApp.*")
            self._rdkit = (Chem, AllChem)
        return self._rdkit

    def is_loaded(self) -> bool:
        return self._rdkit not in (None, (None, None))

    def is_unavailable(self) -> bool:
        return self._rdkit == (None, None)

    def preload(self) -> bool:
        rdkit = self._load_rdkit()
        return rdkit != (None, None)

    def smiles_to_2d(self, smiles: str, scale: float = 40.0) -> Optional[MoleculeModel]:
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            return None
        Chem, AllChem = rdkit
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            self.last_error = (
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
                for i, (x1, y1) in enumerate(positions):
                    min_dist = None
                    for j, (x2, y2) in enumerate(positions):
                        if i == j:
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

    def model_to_rdkit_with_map(self, model: MoleculeModel):
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            return None, None
        Chem, _ = rdkit
        rw = Chem.RWMol()
        atom_map = {}
        for atom_id, atom in model.atoms.items():
            try:
                rd_atom = Chem.Atom(atom.element)
            except Exception:
                rd_atom = Chem.Atom("C")
            atom_map[atom_id] = rw.AddAtom(rd_atom)
        valid_atoms = set(atom_map.keys())
        seen_bonds: set[tuple[int, int]] = set()
        for bond in model.bonds:
            if bond is None:
                continue
            if bond.a == bond.b:
                continue
            if bond.a not in valid_atoms or bond.b not in valid_atoms:
                continue
            key = (bond.a, bond.b) if bond.a <= bond.b else (bond.b, bond.a)
            if key in seen_bonds:
                continue
            seen_bonds.add(key)
            order_map = {
                1: Chem.BondType.SINGLE,
                2: Chem.BondType.DOUBLE,
                3: Chem.BondType.TRIPLE,
            }
            btype = order_map.get(bond.order, Chem.BondType.SINGLE)
            rw.AddBond(atom_map[bond.a], atom_map[bond.b], btype)
        mol = rw.GetMol()
        try:
            Chem.SanitizeMol(mol)
        except Exception:
            pass
        return mol, atom_map

    def model_to_rdkit(self, model: MoleculeModel):
        mol, _ = self.model_to_rdkit_with_map(model)
        return mol

    def compute_props(self, model: MoleculeModel) -> tuple[str | None, float | None, str | None]:
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            return None, None, None
        Chem, _ = rdkit
        mol = self.model_to_rdkit(model)
        if mol is None:
            return None, None, None
        try:
            mol_h = Chem.AddHs(mol)
            from rdkit.Chem import Descriptors, rdMolDescriptors

            formula = rdMolDescriptors.CalcMolFormula(mol_h)
            mw = Descriptors.MolWt(mol_h)
            smiles = Chem.MolToSmiles(mol, canonical=True)
            return formula, mw, smiles
        except Exception:
            return None, None, None

    def model_to_3d_coords(self, model: MoleculeModel):
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            self.last_error = "RDKit is not available in this environment."
            return None
        Chem, AllChem = rdkit
        mol, atom_map = self.model_to_rdkit_with_map(model)
        if mol is None or atom_map is None:
            self.last_error = "Failed to build RDKit molecule."
            return None
        try:
            mol_h = Chem.AddHs(mol)
            params = AllChem.ETKDGv3()
            params.randomSeed = 0xC0FFEE
            status = AllChem.EmbedMolecule(mol_h, params)
            if status != 0:
                params.useRandomCoords = True
                status = AllChem.EmbedMolecule(mol_h, params)
            if status != 0:
                self.last_error = "3D embedding failed."
                return None
            try:
                AllChem.UFFOptimizeMolecule(mol_h, maxIters=50)
            except Exception:
                pass
        except Exception as exc:
            self.last_error = f"3D coordinate generation failed: {exc}"
            return None
        if mol_h.GetNumConformers() == 0:
            self.last_error = "3D coordinate generation failed: no conformer."
            return None
        conf = mol_h.GetConformer()
        coords = {}
        for atom_id, rd_idx in atom_map.items():
            pos = conf.GetAtomPosition(rd_idx)
            coords[atom_id] = (pos.x, pos.y, pos.z)
        return coords

    def get_name_from_smiles(self, smiles: str) -> str | None:
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            return None
        Chem, _ = rdkit
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            canonical = Chem.MolToSmiles(mol, canonical=True)
            return self._name_map.get(canonical)
        except Exception:
            return None

    def model_to_3d(self, model: MoleculeModel):
        # Backward-compatible wrapper kept in sync with model_to_3d_coords().
        return self.model_to_3d_coords(model)
