import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import MoleculeModel
from core.rdkit_adapter import RDKitAdapter


class _FakePosition:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


class _FakeAtom:
    def __init__(self, idx: int, symbol: str) -> None:
        self._idx = idx
        self._symbol = symbol

    def GetIdx(self) -> int:
        return self._idx

    def GetSymbol(self) -> str:
        return self._symbol


class _FakeBond:
    def __init__(self, begin_idx: int, end_idx: int, order: float) -> None:
        self._begin_idx = begin_idx
        self._end_idx = end_idx
        self._order = order

    def GetBeginAtomIdx(self) -> int:
        return self._begin_idx

    def GetEndAtomIdx(self) -> int:
        return self._end_idx

    def GetBondTypeAsDouble(self) -> float:
        return self._order


class _FakeConformer:
    def __init__(self, positions: dict[int, tuple[float, float, float]]) -> None:
        self._positions = positions

    def GetAtomPosition(self, idx: int) -> _FakePosition:
        x, y, z = self._positions[idx]
        return _FakePosition(x, y, z)


class _FakeMol:
    def __init__(
        self,
        atom_symbols: list[str],
        bonds: list[tuple[int, int, float]],
        positions: dict[int, tuple[float, float, float]],
        canonical_smiles: str | None = None,
    ) -> None:
        self._atoms = [_FakeAtom(idx, symbol) for idx, symbol in enumerate(atom_symbols)]
        self._bonds = [_FakeBond(a, b, order) for a, b, order in bonds]
        self._conformer = _FakeConformer(positions)
        self.canonical_smiles = canonical_smiles

    def GetAtoms(self):
        return list(self._atoms)

    def GetBonds(self):
        return list(self._bonds)

    def GetConformer(self) -> _FakeConformer:
        return self._conformer


class _FakeRDAtom:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol


class _FakeRWMol:
    def __init__(self) -> None:
        self.atoms: list[_FakeRDAtom] = []
        self.bonds: list[tuple[int, int, str]] = []

    def AddAtom(self, atom: _FakeRDAtom) -> int:
        self.atoms.append(atom)
        return len(self.atoms) - 1

    def AddBond(self, a: int, b: int, btype: str) -> None:
        self.bonds.append((a, b, btype))

    def GetMol(self):
        return SimpleNamespace(atoms=self.atoms, bonds=self.bonds)


class _FakeChem:
    class BondType:
        SINGLE = "single"
        DOUBLE = "double"
        TRIPLE = "triple"

    def __init__(self, mols_by_smiles: dict[str, _FakeMol | None]) -> None:
        self._mols_by_smiles = mols_by_smiles
        self.sanitized_molecules = []

    def MolFromSmiles(self, smiles: str):
        return self._mols_by_smiles.get(smiles)

    def MolToSmiles(self, mol, canonical: bool = True) -> str:
        return getattr(mol, "canonical_smiles", "unknown")

    def Atom(self, symbol: str) -> _FakeRDAtom:
        if symbol == "Xx":
            raise ValueError("invalid atom")
        return _FakeRDAtom(symbol)

    def RWMol(self) -> _FakeRWMol:
        return _FakeRWMol()

    def SanitizeMol(self, mol) -> None:
        self.sanitized_molecules.append(mol)


class _FakeAllChem:
    def Compute2DCoords(self, mol) -> None:
        return None


class RDKitAdapterTest(unittest.TestCase):
    def test_smiles_to_2d_scales_coordinates_and_bond_order(self) -> None:
        fake_mol = _FakeMol(
            atom_symbols=["C", "O"],
            bonds=[(0, 1, 2.0)],
            positions={0: (0.0, 0.0, 0.0), 1: (1.0, 0.5, 0.0)},
        )
        chem = _FakeChem({"CO": fake_mol})
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem())

        model = adapter.smiles_to_2d("CO", scale=20.0)

        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(len(model.atoms), 2)
        self.assertAlmostEqual(model.atoms[0].x, 0.0)
        self.assertAlmostEqual(model.atoms[1].x, 17.88854381999832)
        self.assertAlmostEqual(model.atoms[1].y, -8.94427190999916)
        self.assertEqual(len(model.bonds), 1)
        self.assertEqual(model.bonds[0].order, 2)

    def test_smiles_to_2d_invalid_smiles_sets_error(self) -> None:
        chem = _FakeChem({"bad": None})
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem())

        model = adapter.smiles_to_2d("bad")

        self.assertIsNone(model)
        self.assertIn("Invalid SMILES string", adapter.last_error or "")

    def test_model_to_rdkit_with_map_deduplicates_and_falls_back_to_carbon(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({})
        adapter._rdkit = (chem, _FakeAllChem())
        model = MoleculeModel()
        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("Xx", 1.0, 0.0)
        model.add_bond(a0, a1, 1)
        model.add_bond(a1, a0, 2)
        model.add_bond(a0, a0, 3)

        mol, atom_map = adapter.model_to_rdkit_with_map(model)

        self.assertEqual(atom_map, {0: 0, 1: 1})
        self.assertEqual([atom.symbol for atom in mol.atoms], ["C", "C"])
        self.assertEqual(mol.bonds, [(0, 1, "single")])
        self.assertEqual(len(chem.sanitized_molecules), 1)

    def test_get_name_from_smiles_uses_canonical_map(self) -> None:
        fake_mol = _FakeMol(
            atom_symbols=["C"] * 6,
            bonds=[],
            positions={i: (float(i), 0.0, 0.0) for i in range(6)},
            canonical_smiles="c1ccccc1",
        )
        chem = _FakeChem({"benzene-ish": fake_mol})
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem())

        name = adapter.get_name_from_smiles("benzene-ish")

        self.assertEqual(name, "Benzene")

    def test_state_helpers_reflect_loaded_and_unavailable_flags(self) -> None:
        adapter = RDKitAdapter()
        self.assertFalse(adapter.is_loaded())
        self.assertFalse(adapter.is_unavailable())

        adapter._rdkit = ("Chem", "AllChem")
        self.assertTrue(adapter.is_loaded())
        self.assertFalse(adapter.is_unavailable())

        adapter._rdkit = (None, None)
        self.assertFalse(adapter.is_loaded())
        self.assertTrue(adapter.is_unavailable())


if __name__ == "__main__":
    unittest.main()
