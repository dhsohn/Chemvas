import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import MoleculeModel
from core.rdkit_adapter import RDKitAdapter


_REAL_IMPORT = __import__
_MISSING = object()


def _block_rdkit_imports(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "rdkit" or name.startswith("rdkit."):
        raise ImportError("blocked rdkit import")
    return _REAL_IMPORT(name, globals, locals, fromlist, level)


def _patch_descriptor_modules(
    *,
    formula: str = "CH4O",
    mw: float = 32.042,
    formula_error: Exception | None = None,
    mw_error: Exception | None = None,
):
    rdkit_module = ModuleType("rdkit")
    chem_module = ModuleType("rdkit.Chem")
    descriptors_module = ModuleType("rdkit.Chem.Descriptors")
    rd_mol_descriptors_module = ModuleType("rdkit.Chem.rdMolDescriptors")

    def calc_formula(mol) -> str:
        if formula_error is not None:
            raise formula_error
        return formula

    def calc_mw(mol) -> float:
        if mw_error is not None:
            raise mw_error
        return mw

    descriptors_module.MolWt = calc_mw
    rd_mol_descriptors_module.CalcMolFormula = calc_formula
    chem_module.Descriptors = descriptors_module
    chem_module.rdMolDescriptors = rd_mol_descriptors_module
    rdkit_module.Chem = chem_module

    return mock.patch.dict(
        sys.modules,
        {
            "rdkit": rdkit_module,
            "rdkit.Chem": chem_module,
            "rdkit.Chem.Descriptors": descriptors_module,
            "rdkit.Chem.rdMolDescriptors": rd_mol_descriptors_module,
        },
    )


def _patch_rdkit_import_modules(*, chem=None, all_chem=None):
    rdkit_module = ModuleType("rdkit")
    chem_module = chem if chem is not None else ModuleType("rdkit.Chem")
    all_chem_module = all_chem if all_chem is not None else ModuleType("rdkit.Chem.AllChem")
    rd_logger_module = ModuleType("rdkit.RDLogger")
    disabled_logs: list[str] = []

    def disable_log(pattern: str) -> None:
        disabled_logs.append(pattern)

    chem_module.AllChem = all_chem_module
    rd_logger_module.DisableLog = disable_log
    rdkit_module.Chem = chem_module
    rdkit_module.RDLogger = rd_logger_module

    patcher = mock.patch.dict(
        sys.modules,
        {
            "rdkit": rdkit_module,
            "rdkit.Chem": chem_module,
            "rdkit.Chem.AllChem": all_chem_module,
            "rdkit.RDLogger": rd_logger_module,
        },
    )
    return patcher, disabled_logs, chem_module, all_chem_module


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


class _Fake3DMol:
    def __init__(
        self,
        positions: dict[int, tuple[float, float, float]],
        *,
        conformer_count: int = 1,
    ) -> None:
        self._conformer = _FakeConformer(positions)
        self._conformer_count = conformer_count

    def GetNumConformers(self) -> int:
        return self._conformer_count

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

    def __init__(
        self,
        mols_by_smiles: dict[str, _FakeMol | None],
        *,
        add_hs_result=_MISSING,
        add_hs_error: Exception | None = None,
        mol_to_smiles_error: Exception | None = None,
        sanitize_error: Exception | None = None,
    ) -> None:
        self._mols_by_smiles = mols_by_smiles
        self._add_hs_result = add_hs_result
        self._add_hs_error = add_hs_error
        self._mol_to_smiles_error = mol_to_smiles_error
        self._sanitize_error = sanitize_error
        self.sanitized_molecules = []

    def MolFromSmiles(self, smiles: str):
        return self._mols_by_smiles.get(smiles)

    def MolToSmiles(self, mol, canonical: bool = True) -> str:
        if self._mol_to_smiles_error is not None:
            raise self._mol_to_smiles_error
        return getattr(mol, "canonical_smiles", "unknown")

    def Atom(self, symbol: str) -> _FakeRDAtom:
        if symbol == "Xx":
            raise ValueError("invalid atom")
        return _FakeRDAtom(symbol)

    def RWMol(self) -> _FakeRWMol:
        return _FakeRWMol()

    def SanitizeMol(self, mol) -> None:
        if self._sanitize_error is not None:
            raise self._sanitize_error
        self.sanitized_molecules.append(mol)

    def AddHs(self, mol):
        if self._add_hs_error is not None:
            raise self._add_hs_error
        if self._add_hs_result is not _MISSING:
            return self._add_hs_result
        return mol


class _FakeAllChem:
    def Compute2DCoords(self, mol) -> None:
        return None


class _FakeAllChem3D:
    def __init__(
        self,
        *,
        embed_statuses: list[int] | None = None,
        embed_error: Exception | None = None,
        optimize_error: Exception | None = None,
    ) -> None:
        self._embed_statuses = list(embed_statuses or [0])
        self._embed_error = embed_error
        self._optimize_error = optimize_error
        self.embed_calls: list[bool] = []
        self.optimize_calls: list[int] = []
        self.params_created = []

    def ETKDGv3(self):
        params = SimpleNamespace(randomSeed=None, useRandomCoords=False)
        self.params_created.append(params)
        return params

    def EmbedMolecule(self, mol, params) -> int:
        self.embed_calls.append(params.useRandomCoords)
        if self._embed_error is not None:
            raise self._embed_error
        if self._embed_statuses:
            return self._embed_statuses.pop(0)
        return 0

    def UFFOptimizeMolecule(self, mol, maxIters: int = 50) -> int:
        self.optimize_calls.append(maxIters)
        if self._optimize_error is not None:
            raise self._optimize_error
        return 0


class RDKitAdapterTest(unittest.TestCase):
    def _simple_model(self) -> MoleculeModel:
        model = MoleculeModel()
        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("O", 1.0, 0.0)
        model.add_bond(a0, a1, 1)
        return model

    def test_preload_returns_false_when_rdkit_import_fails(self) -> None:
        adapter = RDKitAdapter()

        with mock.patch("builtins.__import__", side_effect=_block_rdkit_imports):
            loaded = adapter.preload()

        self.assertFalse(loaded)
        self.assertEqual(adapter.last_error, "RDKit is not available in this environment.")
        self.assertFalse(adapter.is_loaded())

    def test_preload_loads_and_caches_rdkit_modules(self) -> None:
        adapter = RDKitAdapter()
        patcher, disabled_logs, chem_module, all_chem_module = _patch_rdkit_import_modules()

        with patcher:
            self.assertTrue(adapter.preload())
            self.assertEqual(adapter._rdkit, (chem_module, all_chem_module))

        self.assertTrue(adapter.preload())
        self.assertEqual(disabled_logs, ["rdApp.*"])
        self.assertTrue(adapter.is_loaded())

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

    def test_smiles_to_2d_returns_none_when_rdkit_is_unavailable(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (None, None)

        self.assertIsNone(adapter.smiles_to_2d("CO"))

    def test_smiles_to_2d_uses_nearest_neighbor_scaling_without_bonds(self) -> None:
        fake_mol = _FakeMol(
            atom_symbols=["C", "O"],
            bonds=[],
            positions={0: (0.0, 0.0, 0.0), 1: (2.0, 0.0, 0.0)},
        )
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem({"CO": fake_mol}), _FakeAllChem())

        model = adapter.smiles_to_2d("CO", scale=20.0)

        self.assertIsNotNone(model)
        assert model is not None
        self.assertAlmostEqual(model.atoms[1].x, 20.0)
        self.assertAlmostEqual(model.atoms[1].y, 0.0)

    def test_smiles_to_2d_skips_zero_distance_neighbors(self) -> None:
        fake_mol = _FakeMol(
            atom_symbols=["C", "O", "N"],
            bonds=[],
            positions={0: (0.0, 0.0, 0.0), 1: (0.0, 0.0, 0.0), 2: (2.0, 0.0, 0.0)},
        )
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem({"CON": fake_mol}), _FakeAllChem())

        model = adapter.smiles_to_2d("CON", scale=20.0)

        self.assertIsNotNone(model)
        assert model is not None
        self.assertAlmostEqual(model.atoms[2].x, 20.0)

    def test_smiles_to_2d_preserves_coords_without_reference_distance(self) -> None:
        fake_mol = _FakeMol(
            atom_symbols=["He"],
            bonds=[],
            positions={0: (3.0, 4.0, 0.0)},
        )
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem({"[He]": fake_mol}), _FakeAllChem())

        model = adapter.smiles_to_2d("[He]", scale=20.0)

        self.assertIsNotNone(model)
        assert model is not None
        self.assertAlmostEqual(model.atoms[0].x, 3.0)
        self.assertAlmostEqual(model.atoms[0].y, -4.0)

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

    def test_model_to_rdkit_with_map_returns_none_when_rdkit_is_unavailable(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (None, None)

        self.assertEqual(adapter.model_to_rdkit_with_map(self._simple_model()), (None, None))

    def test_model_to_rdkit_with_map_ignores_invalid_bonds_and_sanitize_errors(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({}, sanitize_error=RuntimeError("bad sanitize"))
        adapter._rdkit = (chem, _FakeAllChem())
        model = MoleculeModel()
        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("O", 1.0, 0.0)
        model.bonds.append(None)
        model.add_bond(a0, 99, 2)
        model.add_bond(a0, a1, 99)

        mol, atom_map = adapter.model_to_rdkit_with_map(model)

        self.assertEqual(atom_map, {0: 0, 1: 1})
        self.assertEqual(mol.bonds, [(0, 1, "single")])
        self.assertEqual(chem.sanitized_molecules, [])

    def test_model_to_rdkit_returns_molecule_from_wrapped_builder(self) -> None:
        adapter = RDKitAdapter()
        expected = SimpleNamespace(name="mol")

        with mock.patch.object(adapter, "model_to_rdkit_with_map", return_value=(expected, {0: 0})):
            self.assertIs(adapter.model_to_rdkit(self._simple_model()), expected)

    def test_compute_props_returns_none_triplet_when_rdkit_is_unavailable(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (None, None)

        self.assertEqual(adapter.compute_props(self._simple_model()), (None, None, None))

    def test_compute_props_returns_none_triplet_when_model_conversion_fails(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem({}), _FakeAllChem())

        with mock.patch.object(adapter, "model_to_rdkit", return_value=None):
            self.assertEqual(adapter.compute_props(self._simple_model()), (None, None, None))

    def test_compute_props_returns_formula_mass_and_smiles(self) -> None:
        chem = _FakeChem({}, add_hs_result=SimpleNamespace())
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem())
        model = self._simple_model()

        with mock.patch.object(
            adapter,
            "model_to_rdkit",
            return_value=SimpleNamespace(canonical_smiles="CO"),
        ):
            with _patch_descriptor_modules(formula="CH4O", mw=32.042):
                formula, mw, smiles = adapter.compute_props(model)

        self.assertEqual(formula, "CH4O")
        self.assertEqual(mw, 32.042)
        self.assertEqual(smiles, "CO")

    def test_compute_props_returns_none_triplet_on_descriptor_error(self) -> None:
        chem = _FakeChem({}, add_hs_result=SimpleNamespace())
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem())

        with mock.patch.object(
            adapter,
            "model_to_rdkit",
            return_value=SimpleNamespace(canonical_smiles="CO"),
        ):
            with _patch_descriptor_modules(mw_error=RuntimeError("descriptor failure")):
                self.assertEqual(adapter.compute_props(self._simple_model()), (None, None, None))

    def test_model_to_3d_coords_returns_none_when_rdkit_is_unavailable(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (None, None)

        coords = adapter.model_to_3d_coords(self._simple_model())

        self.assertIsNone(coords)
        self.assertEqual(adapter.last_error, "RDKit is not available in this environment.")

    def test_model_to_3d_coords_returns_none_when_model_conversion_fails(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem({}), _FakeAllChem3D())

        with mock.patch.object(adapter, "model_to_rdkit_with_map", return_value=(None, None)):
            coords = adapter.model_to_3d_coords(self._simple_model())

        self.assertIsNone(coords)
        self.assertEqual(adapter.last_error, "Failed to build RDKit molecule.")

    def test_model_to_3d_coords_retries_with_random_coords_and_returns_mapping(self) -> None:
        chem = _FakeChem(
            {},
            add_hs_result=_Fake3DMol({0: (1.0, 2.0, 3.0), 1: (4.0, 5.0, 6.0)}),
        )
        all_chem = _FakeAllChem3D(embed_statuses=[1, 0])
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, all_chem)

        with mock.patch.object(
            adapter,
            "model_to_rdkit_with_map",
            return_value=(SimpleNamespace(), {10: 0, 11: 1}),
        ):
            coords = adapter.model_to_3d_coords(self._simple_model())

        self.assertEqual(coords, {10: (1.0, 2.0, 3.0), 11: (4.0, 5.0, 6.0)})
        self.assertEqual(all_chem.embed_calls, [False, True])
        self.assertEqual(all_chem.optimize_calls, [50])
        self.assertEqual(all_chem.params_created[0].randomSeed, 0xC0FFEE)
        self.assertTrue(all_chem.params_created[0].useRandomCoords)

    def test_model_to_3d_coords_ignores_uff_optimization_errors(self) -> None:
        chem = _FakeChem({}, add_hs_result=_Fake3DMol({0: (1.0, 2.0, 3.0)}))
        all_chem = _FakeAllChem3D(optimize_error=RuntimeError("force field failed"))
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, all_chem)

        with mock.patch.object(
            adapter,
            "model_to_rdkit_with_map",
            return_value=(SimpleNamespace(), {7: 0}),
        ):
            coords = adapter.model_to_3d_coords(self._simple_model())

        self.assertEqual(coords, {7: (1.0, 2.0, 3.0)})

    def test_model_to_3d_coords_returns_none_when_embedding_fails_twice(self) -> None:
        chem = _FakeChem({}, add_hs_result=_Fake3DMol({0: (1.0, 2.0, 3.0)}))
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem3D(embed_statuses=[1, 1]))

        with mock.patch.object(
            adapter,
            "model_to_rdkit_with_map",
            return_value=(SimpleNamespace(), {0: 0}),
        ):
            coords = adapter.model_to_3d_coords(self._simple_model())

        self.assertIsNone(coords)
        self.assertEqual(adapter.last_error, "3D embedding failed.")

    def test_model_to_3d_coords_returns_none_on_generation_exception(self) -> None:
        chem = _FakeChem({}, add_hs_error=RuntimeError("bad hydrogens"))
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem3D())

        with mock.patch.object(
            adapter,
            "model_to_rdkit_with_map",
            return_value=(SimpleNamespace(), {0: 0}),
        ):
            coords = adapter.model_to_3d_coords(self._simple_model())

        self.assertIsNone(coords)
        self.assertEqual(
            adapter.last_error,
            "3D coordinate generation failed: bad hydrogens",
        )

    def test_model_to_3d_coords_returns_none_without_conformer(self) -> None:
        chem = _FakeChem(
            {},
            add_hs_result=_Fake3DMol({0: (1.0, 2.0, 3.0)}, conformer_count=0),
        )
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem3D())

        with mock.patch.object(
            adapter,
            "model_to_rdkit_with_map",
            return_value=(SimpleNamespace(), {0: 0}),
        ):
            coords = adapter.model_to_3d_coords(self._simple_model())

        self.assertIsNone(coords)
        self.assertEqual(adapter.last_error, "3D coordinate generation failed: no conformer.")

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

    def test_get_name_from_smiles_returns_none_when_rdkit_is_unavailable(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (None, None)

        self.assertIsNone(adapter.get_name_from_smiles("benzene-ish"))

    def test_get_name_from_smiles_returns_none_for_invalid_smiles(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem({"bad": None}), _FakeAllChem())

        self.assertIsNone(adapter.get_name_from_smiles("bad"))

    def test_get_name_from_smiles_returns_none_on_canonicalization_error(self) -> None:
        fake_mol = _FakeMol(
            atom_symbols=["C"] * 6,
            bonds=[],
            positions={i: (float(i), 0.0, 0.0) for i in range(6)},
            canonical_smiles="c1ccccc1",
        )
        adapter = RDKitAdapter()
        adapter._rdkit = (
            _FakeChem({"benzene-ish": fake_mol}, mol_to_smiles_error=RuntimeError("bad smiles")),
            _FakeAllChem(),
        )

        self.assertIsNone(adapter.get_name_from_smiles("benzene-ish"))

    def test_model_to_3d_delegates_to_model_to_3d_coords(self) -> None:
        adapter = RDKitAdapter()
        expected = {0: (1.0, 2.0, 3.0)}

        with mock.patch.object(adapter, "model_to_3d_coords", return_value=expected) as mocked:
            result = adapter.model_to_3d(self._simple_model())

        self.assertIs(result, expected)
        mocked.assert_called_once()

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
