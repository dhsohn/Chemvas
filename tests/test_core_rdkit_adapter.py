import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import Bond, MoleculeModel
from core.rdkit_adapter import RDKitAdapter

try:
    from rdkit import Chem as _RealChem
except ModuleNotFoundError:
    _RealChem = None


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


def _find_xyz_export_method(adapter: RDKitAdapter):
    priority = [
        "model_to_xyz_block",
        "export_xyz_block",
        "to_xyz_block",
        "model_to_xyz",
        "export_xyz",
        "write_xyz_file",
        "export_xyz_file",
        "model_to_xyz_file",
        "save_xyz",
        "save_as_xyz",
    ]
    seen: set[str] = set()
    names = [name for name in priority if hasattr(adapter, name)]
    names.extend(
        name
        for name in sorted(dir(adapter))
        if name not in names
        and "xyz" in name.lower()
        and any(token in name.lower() for token in ("export", "save", "write", "block", "model"))
    )
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        method = getattr(adapter, name, None)
        if callable(method):
            return method
    raise AssertionError("Expected RDKitAdapter to expose an XYZ export helper.")


def _invoke_xyz_export(method, *, model: MoleculeModel, path: Path | None = None):
    model_names = {"model", "molecule", "mol", "structure", "document_model"}
    path_names = {
        "path",
        "file_path",
        "filepath",
        "filename",
        "output_path",
        "output_file",
        "destination",
        "target",
    }
    positional = []
    keyword = {}
    for parameter in inspect.signature(method).parameters.values():
        lower = parameter.name.lower()
        value = _MISSING
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if lower in model_names:
            value = model
        elif lower in path_names:
            if path is None:
                if parameter.default is inspect._empty:
                    raise AssertionError(
                        f"XYZ exporter {method.__name__} requires a path but none was supplied.",
                    )
                continue
            value = str(path)
        elif lower == "comment":
            value = "LiteDraw XYZ export"
        elif parameter.default is not inspect._empty:
            continue
        else:
            raise AssertionError(
                f"Unsupported required XYZ export parameter {parameter.name!r} on {method.__name__}.",
            )
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            keyword[parameter.name] = value
        else:
            positional.append(value)
    return method(*positional, **keyword)


def _read_xyz_text(result, *, path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    if isinstance(result, Path):
        return result.read_text(encoding="utf-8")
    if isinstance(result, str):
        possible_path = Path(result)
        if possible_path.exists():
            return possible_path.read_text(encoding="utf-8")
        return result
    raise AssertionError("XYZ exporter must either return text or write to the requested path.")


def _parse_xyz_block(xyz_text: str) -> tuple[int, str, list[tuple[str, tuple[float, float, float]]]]:
    lines = xyz_text.splitlines()
    if len(lines) < 2:
        raise AssertionError("XYZ output must include an atom-count header and a comment line.")
    atom_count = int(lines[0].strip())
    records = []
    for line in lines[2:]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4:
            raise AssertionError(f"Malformed XYZ coordinate line: {line!r}")
        records.append(
            (
                parts[0],
                (float(parts[1]), float(parts[2]), float(parts[3])),
            ),
        )
    return atom_count, lines[1], records


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
        atom_symbols: list[str] | None = None,
        bonds: list[tuple[int, int, float]] | None = None,
        conformer_count: int = 1,
    ) -> None:
        if atom_symbols is None:
            atom_symbols = ["C"] * len(positions)
        self._atoms = [_FakeAtom(idx, symbol) for idx, symbol in enumerate(atom_symbols)]
        self._bonds = [_FakeBond(a, b, order) for a, b, order in (bonds or [])]
        self._conformer = _FakeConformer(positions)
        self._conformer_count = conformer_count

    def GetAtoms(self):
        return list(self._atoms)

    def GetBonds(self):
        return list(self._bonds)

    def GetNumConformers(self) -> int:
        return self._conformer_count

    def GetConformer(self) -> _FakeConformer:
        return self._conformer


class _FakeRDAtom:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.no_implicit = False
        self.formal_charge = 0
        self.radical_electrons = 0

    def SetNoImplicit(self, value: bool) -> None:
        self.no_implicit = bool(value)

    def SetFormalCharge(self, value: int) -> None:
        self.formal_charge = value

    def SetNumRadicalElectrons(self, value: int) -> None:
        self.radical_electrons = value


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
        if symbol in {"Xx", "Me", "Et", "Ph", "OMe", "Boc"}:
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


class _FakeAliasAtom:
    def __init__(self, idx: int, symbol: str, atomic_num: int) -> None:
        self._idx = idx
        self.symbol = symbol
        self._atomic_num = atomic_num
        self._neighbors: list["_FakeAliasAtom"] = []

    def GetIdx(self) -> int:
        return self._idx

    def GetAtomicNum(self) -> int:
        return self._atomic_num

    def GetNeighbors(self):
        return list(self._neighbors)

    def add_neighbor(self, atom: "_FakeAliasAtom") -> None:
        self._neighbors.append(atom)


class _FakeAliasBond:
    def __init__(self, begin_idx: int, end_idx: int, bond_type: str = "single") -> None:
        self._begin_idx = begin_idx
        self._end_idx = end_idx
        self._bond_type = bond_type

    def GetBeginAtomIdx(self) -> int:
        return self._begin_idx

    def GetEndAtomIdx(self) -> int:
        return self._end_idx

    def GetBondType(self) -> str:
        return self._bond_type


class _FakeAliasFragment:
    def __init__(
        self,
        atoms: list[_FakeAliasAtom],
        bonds: list[_FakeAliasBond],
        *,
        positions: dict[int, tuple[float, float, float]] | None = None,
        conformer_count: int = 1,
    ) -> None:
        self._atoms = atoms
        self._bonds = bonds
        self._conformer_count = conformer_count
        atom_map = {atom.GetIdx(): atom for atom in atoms}
        for bond in bonds:
            begin = atom_map.get(bond.GetBeginAtomIdx())
            end = atom_map.get(bond.GetEndAtomIdx())
            if begin is None or end is None:
                continue
            begin.add_neighbor(end)
            end.add_neighbor(begin)
        if positions is None:
            positions = {atom.GetIdx(): (float(atom.GetIdx()), 0.0, 0.0) for atom in atoms}
        self._conformer = _FakeConformer(positions)

    def GetAtoms(self):
        return list(self._atoms)

    def GetBonds(self):
        return list(self._bonds)

    def GetNumConformers(self) -> int:
        return self._conformer_count

    def GetConformer(self) -> _FakeConformer:
        return self._conformer


class _FakeSettableConformer:
    def __init__(self, num_atoms: int) -> None:
        self.num_atoms = num_atoms
        self.positions: dict[int, tuple[float, float, float]] = {}

    def SetAtomPosition(self, atom_idx: int, pos) -> None:
        self.positions[atom_idx] = pos


class _FakeWritableBond:
    def __init__(self, begin_idx: int, end_idx: int, bond_type: str) -> None:
        self.begin_idx = begin_idx
        self.end_idx = end_idx
        self.bond_type = bond_type
        self.direction = None

    def SetBondDir(self, direction) -> None:
        self.direction = direction


class _FakeWritableMol:
    def __init__(self, atoms: list[_FakeRDAtom], bonds: list[_FakeWritableBond], *, add_conformer_error: Exception | None = None) -> None:
        self.atoms = atoms
        self.bonds = bonds
        self._add_conformer_error = add_conformer_error
        self.conformers: list[_FakeSettableConformer] = []

    def GetNumAtoms(self) -> int:
        return len(self.atoms)

    def AddConformer(self, conformer: _FakeSettableConformer, assignId: bool = True) -> None:
        if self._add_conformer_error is not None:
            raise self._add_conformer_error
        self.conformers.append(conformer)


class _FakeDirectionalRWMol:
    def __init__(self, *, add_conformer_error: Exception | None = None) -> None:
        self.atoms: list[_FakeRDAtom] = []
        self.bonds: list[_FakeWritableBond] = []
        self._mol = _FakeWritableMol(self.atoms, self.bonds, add_conformer_error=add_conformer_error)

    def AddAtom(self, atom: _FakeRDAtom) -> int:
        self.atoms.append(atom)
        return len(self.atoms) - 1

    def AddBond(self, a: int, b: int, btype: str) -> None:
        self.bonds.append(_FakeWritableBond(a, b, btype))

    def GetBondBetweenAtoms(self, a: int, b: int):
        for bond in self.bonds:
            if {bond.begin_idx, bond.end_idx} == {a, b}:
                return bond
        return None

    def GetMol(self):
        return self._mol


class _FakeDirectionalChem(_FakeChem):
    class BondDir:
        BEGINWEDGE = "beginwedge"
        BEGINDASH = "begindash"

    def __init__(
        self,
        mols_by_smiles: dict[str, _FakeMol | _FakeAliasFragment | None],
        *,
        add_conformer_error: Exception | None = None,
        stereo_error_method: str | None = None,
        sanitize_error: Exception | None = None,
    ) -> None:
        super().__init__(mols_by_smiles, sanitize_error=sanitize_error)
        self._add_conformer_error = add_conformer_error
        self._stereo_error_method = stereo_error_method
        self.stereo_calls: list[str] = []

    def Atom(self, symbol) -> _FakeRDAtom:
        if isinstance(symbol, _FakeAliasAtom):
            return _FakeRDAtom(symbol.symbol)
        return super().Atom(symbol)

    def RWMol(self) -> _FakeDirectionalRWMol:
        return _FakeDirectionalRWMol(add_conformer_error=self._add_conformer_error)

    def Conformer(self, num_atoms: int) -> _FakeSettableConformer:
        return _FakeSettableConformer(num_atoms)

    def AssignChiralTypesFromBondDirs(self, mol) -> None:
        self.stereo_calls.append("AssignChiralTypesFromBondDirs")
        if self._stereo_error_method == "AssignChiralTypesFromBondDirs":
            raise RuntimeError("stereo failure")

    def SetBondStereoFromDirections(self, mol) -> None:
        self.stereo_calls.append("SetBondStereoFromDirections")
        if self._stereo_error_method == "SetBondStereoFromDirections":
            raise RuntimeError("stereo failure")

    def AssignStereochemistry(self, mol, force: bool = True, cleanIt: bool = True) -> None:
        self.stereo_calls.append("AssignStereochemistry")
        if self._stereo_error_method == "AssignStereochemistry":
            raise RuntimeError("stereo failure")


class _FakeAllChemCoords(_FakeAllChem):
    def __init__(self, compute_error: Exception | None = None) -> None:
        self._compute_error = compute_error
        self.compute_calls = 0

    def Compute2DCoords(self, mol) -> None:
        self.compute_calls += 1
        if self._compute_error is not None:
            raise self._compute_error


class RDKitAdapterTest(unittest.TestCase):
    def _simple_model(self) -> MoleculeModel:
        model = MoleculeModel()
        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("O", 1.0, 0.0)
        model.add_bond(a0, a1, 1)
        return model

    def _halogen_model(self) -> MoleculeModel:
        model = MoleculeModel()
        a0 = model.add_atom("Cl", 0.0, 0.0)
        a1 = model.add_atom("Br", 1.0, 0.0)
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

    def test_model_to_rdkit_with_map_disables_implicit_hydrogen_completion_for_explicit_hydrogen_on_hetero_atom(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({})
        adapter._rdkit = (chem, _FakeAllChem())
        model = MoleculeModel()
        oxygen = model.add_atom("O", 0.0, 0.0)
        hydrogen = model.add_atom("H", 1.0, 0.0)
        model.add_bond(oxygen, hydrogen, 1)

        mol, atom_map = adapter.model_to_rdkit_with_map(model)

        self.assertEqual(atom_map, {0: 0, 1: 1})
        self.assertTrue(mol.atoms[0].no_implicit)
        self.assertFalse(mol.atoms[1].no_implicit)

    def test_build_conversion_rdkit_mol_disables_implicit_hydrogen_completion_for_unannotated_hetero_atom(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({})
        adapter._rdkit = (chem, _FakeAllChem())
        model = MoleculeModel()
        carbon = model.add_atom("C", 0.0, 0.0)
        oxygen = model.add_atom("O", 1.0, 0.0)
        model.add_bond(carbon, oxygen, 1)

        mol = adapter._build_conversion_rdkit_mol(model)

        self.assertIsNotNone(mol)
        self.assertFalse(mol.atoms[0].no_implicit)
        self.assertTrue(mol.atoms[1].no_implicit)

    def test_build_conversion_rdkit_mol_keeps_implicit_hydrogen_completion_for_annotated_hetero_atom(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({})
        adapter._rdkit = (chem, _FakeAllChem())
        model = MoleculeModel()
        charged_nitrogen = model.add_atom("N", 0.0, 0.0)
        radical_oxygen = model.add_atom("O", 2.0, 0.0)

        mol = adapter._build_conversion_rdkit_mol(
            model,
            atom_annotations={
                charged_nitrogen: {"formal_charge": 1},
                radical_oxygen: {"radical_electrons": 1},
            },
        )

        self.assertIsNotNone(mol)
        self.assertFalse(mol.atoms[0].no_implicit)
        self.assertFalse(mol.atoms[1].no_implicit)
        self.assertEqual(mol.atoms[0].formal_charge, 1)
        self.assertEqual(mol.atoms[1].radical_electrons, 1)

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

    def test_model_to_rdkit_with_map_strict_labels_reports_invalid_labels(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({})
        adapter._rdkit = (chem, _FakeAllChem())
        model = MoleculeModel()
        for index, label in enumerate(["Xx", "Me", "Et", "Ph", "OMe", "Boc"]):
            model.add_atom(label, float(index), 0.0)

        mol, atom_map = adapter._conversion_helper._build_rdkit_mol_with_map(model, strict_labels=True)

        self.assertIsNone(mol)
        self.assertIsNone(atom_map)
        self.assertEqual(
            adapter.last_error,
            "XYZ export supports element symbols only. "
            "Unsupported atom labels: Xx (atom 0), Me (atom 1), Et (atom 2), "
            "Ph (atom 3), OMe (atom 4), ....",
        )

    def test_model_to_rdkit_with_map_rejects_unsupported_bond_styles(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({})
        adapter._rdkit = (chem, _FakeAllChem())
        model = MoleculeModel()
        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("O", 1.0, 0.0)
        a2 = model.add_atom("N", 2.0, 0.0)
        model.add_bond(a0, a1, 1)
        model.bonds[-1].style = "wedge"
        model.add_bond(a1, a2, 1)
        model.bonds[-1].style = "hash"

        mol, atom_map = adapter._conversion_helper._build_rdkit_mol_with_map(
            model,
            unsupported_bond_styles={"wedge", "hash"},
        )

        self.assertIsNone(mol)
        self.assertIsNone(atom_map)
        self.assertEqual(
            adapter.last_error,
            "XYZ export does not yet support wedge/hash stereobonds. "
            "Unsupported bond styles: wedge (bond 0), hash (bond 1).",
        )

    def test_build_conversion_rdkit_mol_reports_invalid_labels_with_supported_aliases(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({})
        adapter._rdkit = (chem, _FakeAllChem())
        model = MoleculeModel()
        invalid_labels = [f"Bad{i}" for i in range(6)]
        for index, label in enumerate(invalid_labels):
            model.add_atom(label, float(index), 0.0)

        def atom_factory(symbol: str) -> _FakeRDAtom:
            if symbol.startswith("Bad"):
                raise ValueError("invalid atom")
            return _FakeRDAtom(symbol)

        with mock.patch.object(chem, "Atom", side_effect=atom_factory):
            mol = adapter._build_conversion_rdkit_mol(model)

        self.assertIsNone(mol)
        self.assertEqual(
            adapter.last_error,
            "Unsupported atom labels for 3D conversion: "
            "Bad0 (atom 0), Bad1 (atom 1), Bad2 (atom 2), Bad3 (atom 3), Bad4 (atom 4), .... "
            "Supported aliases: Boc, CO2Me, Et, Me, OH, OMe, Ph, i-Pr, t-Bu.",
        )

    def test_build_conversion_rdkit_mol_rejects_wedge_on_non_single_bond(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({})
        adapter._rdkit = (chem, _FakeAllChem())
        model = MoleculeModel()
        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("O", 1.0, 0.0)
        model.add_bond(a0, a1, 2)
        model.bonds[-1].style = "wedge"

        mol = adapter._build_conversion_rdkit_mol(model)

        self.assertIsNone(mol)
        self.assertEqual(
            adapter.last_error,
            "Bond 0 uses style 'wedge' with order 2. "
            "Stereo export currently supports wedge/hash on single bonds only.",
        )

    def test_build_conversion_rdkit_mol_sets_invalid_structure_error_on_sanitize_failure(self) -> None:
        adapter = RDKitAdapter()
        chem = _FakeChem({}, sanitize_error=RuntimeError("bad sanitize"))
        adapter._rdkit = (chem, _FakeAllChem())

        mol = adapter._build_conversion_rdkit_mol(self._simple_model())

        self.assertIsNone(mol)
        self.assertEqual(adapter.last_error, "3D conversion produced an invalid structure: bad sanitize")

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

    def test_model_to_3d_scene_returns_none_when_rdkit_is_unavailable(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (None, None)

        scene = adapter.model_to_3d_scene(self._simple_model())

        self.assertIsNone(scene)
        self.assertEqual(adapter.last_error, "RDKit is not available in this environment.")

    def test_model_to_3d_scene_returns_none_for_empty_model(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem({}), _FakeAllChem3D())

        scene = adapter.model_to_3d_scene(MoleculeModel())

        self.assertIsNone(scene)
        self.assertEqual(adapter.last_error, "There is no chemical structure to preview.")

    def test_model_to_3d_scene_sets_fallback_error_when_component_build_fails_silently(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem({}), _FakeAllChem3D())
        adapter.last_error = None

        with mock.patch.object(adapter, "_build_conversion_rdkit_mol", return_value=None):
            scene = adapter.model_to_3d_scene(self._simple_model())

        self.assertIsNone(scene)
        self.assertEqual(adapter.last_error, "Failed to build a 3D preview structure.")

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

    def test_model_to_3d_scene_spreads_disconnected_components_apart(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = ("Chem", "AllChem")
        model = MoleculeModel()
        left_a = model.add_atom("C", -10.0, 0.0)
        left_b = model.add_atom("C", -8.0, 0.0)
        model.add_bond(left_a, left_b, 1)
        right_a = model.add_atom("O", 10.0, 0.0)
        right_b = model.add_atom("H", 11.0, 0.0)
        model.add_bond(right_a, right_b, 1)

        left_scene = _Fake3DMol(
            positions={0: (-0.5, 0.0, 0.0), 1: (0.5, 0.0, 0.0)},
            atom_symbols=["C", "C"],
            bonds=[(0, 1, 1.0)],
        )
        right_scene = _Fake3DMol(
            positions={0: (-0.5, 0.0, 0.0), 1: (0.5, 0.0, 0.0)},
            atom_symbols=["O", "H"],
            bonds=[(0, 1, 1.0)],
        )

        with (
            mock.patch.object(adapter, "_build_conversion_rdkit_mol", side_effect=[object(), object()]),
            mock.patch.object(adapter, "_embed_3d_molecule", side_effect=[left_scene, right_scene]),
        ):
            scene = adapter.model_to_3d_scene(model)

        self.assertIsNotNone(scene)
        assert scene is not None
        first_component_max_x = max(atom.x for atom in scene.atoms[:2])
        second_component_min_x = min(atom.x for atom in scene.atoms[2:])
        self.assertGreaterEqual(second_component_min_x - first_component_max_x, 2.5)
        self.assertEqual(len(scene.bonds), 2)

    def test_xyz_export_serializes_atom_count_comment_and_coordinates(self) -> None:
        chem = _FakeChem(
            {},
            add_hs_result=_Fake3DMol(
                {0: (1.0, 2.0, 3.0), 1: (-4.5, 0.0, 6.25)},
                atom_symbols=["Cl", "Br"],
            ),
        )
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem3D())
        model = self._halogen_model()
        exporter = _find_xyz_export_method(adapter)

        with tempfile.TemporaryDirectory() as temp_dir:
            xyz_path = Path(temp_dir) / "structure.xyz"
            result = _invoke_xyz_export(exporter, model=model, path=xyz_path)
            xyz_text = _read_xyz_text(result, path=xyz_path)

        atom_count, comment, records = _parse_xyz_block(xyz_text)
        coords_by_element = {element: coords for element, coords in records}

        self.assertEqual(atom_count, len(records))
        self.assertEqual(atom_count, 2)
        self.assertIsInstance(comment, str)
        self.assertIn("Cl", coords_by_element)
        self.assertIn("Br", coords_by_element)
        self.assertEqual(coords_by_element["Cl"], (1.0, 2.0, 3.0))
        self.assertEqual(coords_by_element["Br"], (-4.5, 0.0, 6.25))

    def test_xyz_export_surfaces_coordinate_generation_failure_without_writing_output(self) -> None:
        chem = _FakeChem({}, add_hs_error=RuntimeError("bad hydrogens"))
        adapter = RDKitAdapter()
        adapter._rdkit = (chem, _FakeAllChem3D())
        model = self._halogen_model()
        exporter = _find_xyz_export_method(adapter)

        with tempfile.TemporaryDirectory() as temp_dir:
            xyz_path = Path(temp_dir) / "failed.xyz"
            result = _invoke_xyz_export(exporter, model=model, path=xyz_path)

        self.assertIsNone(result)
        self.assertFalse(xyz_path.exists())
        self.assertEqual(adapter.last_error, "3D coordinate generation failed: bad hydrogens")

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for alias expansion tests")
    def test_model_to_xyz_block_expands_common_alias_labels(self) -> None:
        adapter = RDKitAdapter()
        model = MoleculeModel()
        scaffold = model.add_atom("C", -1.0, 0.0)
        alias = model.add_atom("Me", 1.0, 0.0)
        model.add_bond(scaffold, alias, 1)

        xyz_block = adapter.model_to_xyz_block(model)

        self.assertIsNotNone(xyz_block)
        assert xyz_block is not None
        atom_count, _, records = _parse_xyz_block(xyz_block)
        elements = [element for element, _ in records]
        self.assertEqual(atom_count, len(records))
        self.assertGreaterEqual(elements.count("C"), 2)
        self.assertIn("H", elements)

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for alias expansion tests")
    def test_model_to_3d_scene_supports_oh_alias_label(self) -> None:
        adapter = RDKitAdapter()
        model = MoleculeModel()
        scaffold = model.add_atom("C", -1.0, 0.0)
        hydroxyl = model.add_atom("OH", 1.0, 0.0)
        model.add_bond(scaffold, hydroxyl, 1)

        scene = adapter.model_to_3d_scene(model)

        self.assertIsNotNone(scene)
        assert scene is not None
        elements = [atom.symbol for atom in scene.atoms]
        self.assertIn("O", elements)
        self.assertIn("H", elements)

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for alias expansion tests")
    def test_model_to_xyz_block_expands_oh_alias_label(self) -> None:
        adapter = RDKitAdapter()
        model = MoleculeModel()
        scaffold = model.add_atom("C", -1.0, 0.0)
        hydroxyl = model.add_atom("OH", 1.0, 0.0)
        model.add_bond(scaffold, hydroxyl, 1)

        xyz_block = adapter.model_to_xyz_block(model)

        self.assertIsNotNone(xyz_block)
        assert xyz_block is not None
        atom_count, _, records = _parse_xyz_block(xyz_block)
        elements = [element for element, _ in records]
        self.assertEqual(atom_count, len(records))
        self.assertIn("O", elements)
        self.assertIn("H", elements)

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for stereo tests")
    def test_conversion_path_maps_wedge_and_hash_to_opposite_chirality(self) -> None:
        adapter = RDKitAdapter()
        model = MoleculeModel()
        center = model.add_atom("C", 0.0, 0.0)
        fluorine = model.add_atom("F", 1.0, 0.0)
        chlorine = model.add_atom("Cl", -1.0, 1.0)
        bromine = model.add_atom("Br", -1.0, -1.0)
        iodine = model.add_atom("I", 0.0, 1.5)
        model.add_bond(center, fluorine, 1)
        model.add_bond(center, chlorine, 1)
        model.add_bond(center, bromine, 1)
        model.add_bond(center, iodine, 1)

        wedge_model = model
        wedge_model.bonds[0].style = "wedge"
        wedge_mol = adapter._build_conversion_rdkit_mol(wedge_model)
        self.assertIsNotNone(wedge_mol)
        wedge_smiles = _RealChem.MolToSmiles(wedge_mol, isomericSmiles=True)

        hash_model = MoleculeModel()
        center = hash_model.add_atom("C", 0.0, 0.0)
        fluorine = hash_model.add_atom("F", 1.0, 0.0)
        chlorine = hash_model.add_atom("Cl", -1.0, 1.0)
        bromine = hash_model.add_atom("Br", -1.0, -1.0)
        iodine = hash_model.add_atom("I", 0.0, 1.5)
        hash_model.add_bond(center, fluorine, 1)
        hash_model.add_bond(center, chlorine, 1)
        hash_model.add_bond(center, bromine, 1)
        hash_model.add_bond(center, iodine, 1)
        hash_model.bonds[0].style = "hash"
        hash_mol = adapter._build_conversion_rdkit_mol(hash_model)
        self.assertIsNotNone(hash_mol)
        hash_smiles = _RealChem.MolToSmiles(hash_mol, isomericSmiles=True)

        self.assertIn("@", wedge_smiles)
        self.assertIn("@", hash_smiles)
        self.assertNotEqual(wedge_smiles, hash_smiles)

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for charge/radical tests")
    def test_model_to_3d_scene_applies_charge_and_radical_annotations(self) -> None:
        adapter = RDKitAdapter()
        charged = MoleculeModel()
        charged.add_atom("N", 0.0, 0.0)
        charged_scene = adapter.model_to_3d_scene(
            charged,
            atom_annotations={0: {"formal_charge": 1}},
        )
        radical = MoleculeModel()
        radical.add_atom("C", 0.0, 0.0)
        radical_scene = adapter.model_to_3d_scene(
            radical,
            atom_annotations={0: {"radical_electrons": 1}},
        )

        self.assertIsNotNone(charged_scene)
        self.assertIsNotNone(radical_scene)
        assert charged_scene is not None
        assert radical_scene is not None
        self.assertGreaterEqual(len(charged_scene.atoms), 5)
        self.assertGreaterEqual(len(radical_scene.atoms), 4)

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for explicit-hydrogen tests")
    def test_model_to_3d_scene_keeps_explicit_hydrogen_fragment_uncompleted(self) -> None:
        adapter = RDKitAdapter()
        model = MoleculeModel()
        oxygen = model.add_atom("O", 0.0, 0.0)
        hydrogen = model.add_atom("H", 1.0, 0.0)
        model.add_bond(oxygen, hydrogen, 1)

        scene = adapter.model_to_3d_scene(model)

        self.assertIsNotNone(scene)
        assert scene is not None
        self.assertEqual(sorted(atom.symbol for atom in scene.atoms), ["H", "O"])

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for implicit-hydrogen tests")
    def test_model_to_3d_scene_does_not_complete_unannotated_terminal_hetero_atom(self) -> None:
        adapter = RDKitAdapter()
        model = MoleculeModel()
        carbon = model.add_atom("C", 0.0, 0.0)
        oxygen = model.add_atom("O", 1.0, 0.0)
        model.add_bond(carbon, oxygen, 1)

        scene = adapter.model_to_3d_scene(model)

        self.assertIsNotNone(scene)
        assert scene is not None
        elements = [atom.symbol for atom in scene.atoms]
        self.assertEqual(elements.count("C"), 1)
        self.assertEqual(elements.count("O"), 1)
        self.assertEqual(elements.count("H"), 3)

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for implicit-hydrogen tests")
    def test_model_to_xyz_block_does_not_complete_unannotated_terminal_hetero_atom(self) -> None:
        adapter = RDKitAdapter()
        model = MoleculeModel()
        carbon = model.add_atom("C", 0.0, 0.0)
        oxygen = model.add_atom("O", 1.0, 0.0)
        model.add_bond(carbon, oxygen, 1)

        xyz_block = adapter.model_to_xyz_block(model)

        self.assertIsNotNone(xyz_block)
        assert xyz_block is not None
        atom_count, _, records = _parse_xyz_block(xyz_block)
        elements = [element for element, _ in records]
        self.assertEqual(atom_count, len(records))
        self.assertEqual(elements.count("C"), 1)
        self.assertEqual(elements.count("O"), 1)
        self.assertEqual(elements.count("H"), 3)

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


class RDKitConversionEdgeTest(unittest.TestCase):
    def test_helper_branches_cover_short_error_details_component_filtering_and_empty_layout(self) -> None:
        adapter = RDKitAdapter()
        helper = adapter._conversion_helper
        adapter._rdkit = (_FakeChem({}), _FakeAllChem())

        invalid_model = MoleculeModel()
        invalid_model.add_atom("Xx", 0.0, 0.0)
        invalid_model.add_atom("Me", 1.0, 0.0)
        mol, atom_map = helper._build_rdkit_mol_with_map(invalid_model, strict_labels=True)
        self.assertIsNone(mol)
        self.assertIsNone(atom_map)
        self.assertEqual(
            adapter.last_error,
            "XYZ export supports element symbols only. Unsupported atom labels: Xx (atom 0), Me (atom 1).",
        )

        style_model = MoleculeModel()
        a0 = style_model.add_atom("C", 0.0, 0.0)
        a1 = style_model.add_atom("O", 1.0, 0.0)
        style_model.add_bond(a0, a1, 1)
        style_model.bonds[-1].style = "wedge"
        mol, atom_map = helper._build_rdkit_mol_with_map(
            style_model,
            unsupported_bond_styles={"wedge"},
        )
        self.assertIsNone(mol)
        self.assertIsNone(atom_map)
        self.assertEqual(
            adapter.last_error,
            "XYZ export does not yet support wedge/hash stereobonds. Unsupported bond styles: wedge (bond 0).",
        )

        model = MoleculeModel()
        atom_id = model.add_atom("C", 0.0, 0.0)
        model.bonds.append(None)
        component_model, annotations = helper._build_component_model(
            model,
            {atom_id, 99},
            atom_annotations={atom_id: {}},
        )
        self.assertEqual(sorted(component_model.atoms), [0])
        self.assertEqual(component_model.bonds, [])
        self.assertEqual(annotations, {})
        self.assertEqual(helper._format_atom_refs(["a (atom 1)", "b (atom 2)"]), "a (atom 1), b (atom 2)")
        self.assertEqual(helper._layout_component_scenes([]).atoms, ())

    def test_build_alias_fragment_covers_failure_matrix_and_success_paths(self) -> None:
        adapter = RDKitAdapter()
        helper = adapter._conversion_helper
        model = MoleculeModel()
        anchor_id = model.add_atom("C", 3.0, 4.0)
        alias_id = model.add_atom("Alias", 5.0, 5.0)
        model.add_bond(anchor_id, alias_id, 1)
        alias_atom = model.atoms[alias_id]

        self.assertEqual(
            helper._build_alias_fragment(
                "Unknown",
                atom_id=alias_id,
                atom=alias_atom,
                neighbors=[anchor_id],
                model=model,
                formal_charge=0,
                radical_electrons=0,
                rw=_FakeRWMol(),
                Chem=_FakeDirectionalChem({}),
                AllChem=_FakeAllChemCoords(),
            ),
            (None, None),
        )

        adapter._alias_smiles = {"Alias": "[*:1]C"}
        chem = _FakeDirectionalChem({})
        all_chem = _FakeAllChemCoords()
        rw = _FakeRWMol()
        self.assertEqual(
            helper._build_alias_fragment(
                "Alias",
                atom_id=alias_id,
                atom=alias_atom,
                neighbors=[],
                model=model,
                formal_charge=0,
                radical_electrons=0,
                rw=rw,
                Chem=chem,
                AllChem=all_chem,
            ),
            (None, None),
        )
        self.assertEqual(
            adapter.last_error,
            "Alias label 'Alias' on atom 1 requires exactly one attachment bond for 3D conversion, but found 0.",
        )

        adapter.last_error = None
        chem = _FakeDirectionalChem({"[*:1]C": None})
        self.assertEqual(
            helper._build_alias_fragment(
                "Alias",
                atom_id=alias_id,
                atom=alias_atom,
                neighbors=[anchor_id],
                model=model,
                formal_charge=0,
                radical_electrons=0,
                rw=_FakeRWMol(),
                Chem=chem,
                AllChem=all_chem,
            ),
            (None, None),
        )
        self.assertEqual(adapter.last_error, "Failed to expand alias label 'Alias' for 3D conversion.")

        no_dummy_fragment = _FakeAliasFragment(
            [_FakeAliasAtom(0, "C", 6)],
            [],
        )
        adapter.last_error = None
        chem = _FakeDirectionalChem({"[*:1]C": no_dummy_fragment})
        self.assertEqual(
            helper._build_alias_fragment(
                "Alias",
                atom_id=alias_id,
                atom=alias_atom,
                neighbors=[anchor_id],
                model=model,
                formal_charge=0,
                radical_electrons=0,
                rw=_FakeRWMol(),
                Chem=chem,
                AllChem=all_chem,
            ),
            (None, None),
        )
        self.assertEqual(adapter.last_error, "Alias label 'Alias' has an invalid attachment definition.")

        dummy = _FakeAliasAtom(0, "*", 0)
        topology_fragment = _FakeAliasFragment([dummy], [])
        adapter.last_error = None
        chem = _FakeDirectionalChem({"[*:1]C": topology_fragment})
        self.assertEqual(
            helper._build_alias_fragment(
                "Alias",
                atom_id=alias_id,
                atom=alias_atom,
                neighbors=[anchor_id],
                model=model,
                formal_charge=0,
                radical_electrons=0,
                rw=_FakeRWMol(),
                Chem=chem,
                AllChem=all_chem,
            ),
            (None, None),
        )
        self.assertEqual(adapter.last_error, "Alias label 'Alias' has an invalid attachment topology.")

        dummy = _FakeAliasAtom(0, "*", 0)
        ghost = _FakeAliasAtom(7, "C", 6)
        dummy.add_neighbor(ghost)
        unattached_fragment = _FakeAliasFragment([dummy], [])
        adapter.last_error = None
        chem = _FakeDirectionalChem({"[*:1]C": unattached_fragment})
        self.assertEqual(
            helper._build_alias_fragment(
                "Alias",
                atom_id=alias_id,
                atom=alias_atom,
                neighbors=[anchor_id],
                model=model,
                formal_charge=0,
                radical_electrons=0,
                rw=_FakeRWMol(),
                Chem=chem,
                AllChem=all_chem,
            ),
            (None, None),
        )
        self.assertEqual(adapter.last_error, "Alias label 'Alias' could not be attached.")

        dummy = _FakeAliasAtom(0, "*", 0)
        attach = _FakeAliasAtom(1, "O", 8)
        no_conf_fragment = _FakeAliasFragment([dummy, attach], [_FakeAliasBond(0, 1)], conformer_count=0)
        adapter.last_error = None
        attachment_idx, coord_map = helper._build_alias_fragment(
            "Alias",
            atom_id=alias_id,
            atom=alias_atom,
            neighbors=[anchor_id],
            model=model,
            formal_charge=1,
            radical_electrons=0,
            rw=_FakeRWMol(),
            Chem=_FakeDirectionalChem({"[*:1]C": no_conf_fragment}),
            AllChem=all_chem,
        )
        self.assertEqual(coord_map, {attachment_idx: (5.0, 5.0)})

        dummy = _FakeAliasAtom(0, "*", 0)
        attach = _FakeAliasAtom(1, "O", 8)
        missing_neighbor_fragment = _FakeAliasFragment([dummy, attach], [_FakeAliasBond(0, 1)])
        adapter.last_error = None
        self.assertEqual(
            helper._build_alias_fragment(
                "Alias",
                atom_id=alias_id,
                atom=alias_atom,
                neighbors=[99],
                model=model,
                formal_charge=0,
                radical_electrons=0,
                rw=_FakeRWMol(),
                Chem=_FakeDirectionalChem({"[*:1]C": missing_neighbor_fragment}),
                AllChem=all_chem,
            ),
            (None, None),
        )
        self.assertEqual(adapter.last_error, "Alias label 'Alias' is attached to a missing atom.")

        dummy = _FakeAliasAtom(0, "*", 0)
        attach = _FakeAliasAtom(1, "O", 8)
        extra = _FakeAliasAtom(2, "C", 6)
        success_fragment = _FakeAliasFragment(
            [dummy, attach, extra],
            [_FakeAliasBond(0, 1), _FakeAliasBond(1, 2)],
            positions={
                0: (0.0, 0.0, 0.0),
                1: (1.0, 0.0, 0.0),
                2: (2.0, 0.0, 0.0),
            },
        )
        rw = _FakeRWMol()
        adapter.last_error = None
        attachment_idx, coord_map = helper._build_alias_fragment(
            "Alias",
            atom_id=alias_id,
            atom=alias_atom,
            neighbors=[anchor_id],
            model=model,
            formal_charge=1,
            radical_electrons=1,
            rw=rw,
            Chem=_FakeDirectionalChem({"[*:1]C": success_fragment}),
            AllChem=_FakeAllChemCoords(RuntimeError("coords failed")),
        )
        self.assertIsNotNone(attachment_idx)
        assert attachment_idx is not None
        self.assertEqual(coord_map[attachment_idx], (5.0, 5.0))
        self.assertEqual(len(rw.bonds), 1)
        self.assertEqual(rw.bonds[0], (0, 1, "single"))
        self.assertEqual(rw.atoms[attachment_idx].formal_charge, 1)
        self.assertEqual(rw.atoms[attachment_idx].radical_electrons, 1)

    def test_build_conversion_rdkit_mol_covers_unavailable_alias_failure_and_directional_branches(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (None, None)
        self.assertIsNone(adapter._build_conversion_rdkit_mol(MoleculeModel()))
        self.assertEqual(adapter.last_error, "RDKit is not available in this environment.")

        adapter = RDKitAdapter()
        alias_model = MoleculeModel()
        scaffold = alias_model.add_atom("C", 0.0, 0.0)
        alias = alias_model.add_atom("Me", 1.0, 0.0)
        alias_model.add_bond(scaffold, alias, 1)
        adapter._rdkit = (_FakeDirectionalChem({}), _FakeAllChemCoords())
        with mock.patch.object(adapter._conversion_helper, "_build_alias_fragment", return_value=(None, None)):
            self.assertIsNone(adapter._build_conversion_rdkit_mol(alias_model))

        adapter = RDKitAdapter()
        chem = _FakeDirectionalChem({}, add_conformer_error=RuntimeError("conformer failed"))
        adapter._rdkit = (chem, _FakeAllChemCoords())
        model = MoleculeModel()
        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("O", 1.0, 0.0)
        model.bonds.append(None)
        model.bonds.append(Bond(a0, a0, 1))
        model.bonds.append(Bond(a0, 99, 1))
        model.add_bond(a0, a1, 1)
        model.bonds[-1].style = "wedge"
        model.add_bond(a1, a0, 1)

        mol = adapter._build_conversion_rdkit_mol(model)

        self.assertIsNotNone(mol)
        assert mol is not None
        self.assertEqual(len(mol.bonds), 1)
        self.assertEqual(mol.bonds[0].direction, chem.BondDir.BEGINWEDGE)
        self.assertEqual(len(mol.conformers), 0)

        adapter = RDKitAdapter()
        chem = _FakeDirectionalChem({}, stereo_error_method="AssignStereochemistry")
        adapter._rdkit = (chem, _FakeAllChemCoords())
        model = MoleculeModel()
        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("O", 1.0, 0.0)
        model.add_bond(a0, a1, 1)
        model.bonds[-1].style = "hash"

        mol = adapter._build_conversion_rdkit_mol(model)

        self.assertIsNotNone(mol)
        assert mol is not None
        self.assertEqual(mol.bonds[0].direction, chem.BondDir.BEGINDASH)
        self.assertEqual(
            chem.stereo_calls,
            [
                "AssignChiralTypesFromBondDirs",
                "SetBondStereoFromDirections",
                "AssignStereochemistry",
            ],
        )

    def test_model_to_3d_scene_preserves_specific_component_build_errors(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeDirectionalChem({}), _FakeAllChem3D())
        adapter.last_error = "Alias expansion failed."

        with mock.patch.object(adapter, "_build_conversion_rdkit_mol", return_value=None):
            self.assertIsNone(adapter.model_to_3d_scene(RDKitAdapterTest()._simple_model()))

        self.assertEqual(adapter.last_error, "Alias expansion failed.")


if __name__ == "__main__":
    unittest.main()
