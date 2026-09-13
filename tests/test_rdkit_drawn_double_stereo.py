from __future__ import annotations

import importlib.util
import math
from copy import deepcopy

import pytest

from chemvas.core.molfile import parse_molfile, write_molfile
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import (
    MoleculeModel,
    deserialize_model_state,
    serialize_model_state,
)

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="optional RDKit dependency is not installed",
)

if importlib.util.find_spec("rdkit") is not None:
    from rdkit import Chem


def _drawing(*, same_side=False, imine=False, alias=False):
    model = MoleculeModel()
    for element, x, y in (
        ("Ph" if alias else "C", 0.0, 30.0),
        ("C", 30.0, 0.0),
        ("N" if imine else "C", 60.0, 0.0),
        ("C", 90.0, 30.0 if same_side else -30.0),
    ):
        model.add_atom(element, x, y)
    for a, b, order in ((0, 1, 1), (1, 2, 2), (2, 3, 1)):
        model.add_bond(a, b, order)
    return model


def _expected(*, same_side=False, imine=False, alias=False):
    left = "c1ccccc1" if alias else "C"
    middle = "N" if imine else "C"
    right_direction = "\\" if same_side else "/"
    return Chem.MolFromSmiles(f"{left}/C={middle}{right_direction}C")


def _assert_identifiers(model, expected):
    before = deepcopy(model)
    adapter = RDKitAdapter()
    identifiers = adapter.compute_identifiers(model)
    assert identifiers.smiles == Chem.MolToSmiles(expected), adapter.last_error
    assert identifiers.inchi == Chem.MolToInchi(expected)
    assert identifiers.inchikey == Chem.MolToInchiKey(expected)
    assert model == before


@pytest.mark.parametrize("same_side", [False, True])
@pytest.mark.parametrize("imine,alias", [(False, False), (True, False), (False, True)])
@pytest.mark.parametrize("transform", ["original", "rotate", "mirror_reverse"])
def test_drawn_geometry_assigns_identifiers_without_mutating_source(
    same_side, imine, alias, transform
):
    model = _drawing(same_side=same_side, imine=imine, alias=alias)
    if transform == "rotate":
        angle = math.radians(73.0)
        for atom in model.atoms.values():
            atom.x, atom.y = (
                500.0 + atom.x * math.cos(angle) - atom.y * math.sin(angle),
                -200.0 + atom.x * math.sin(angle) + atom.y * math.cos(angle),
            )
    elif transform == "mirror_reverse":
        for atom in model.atoms.values():
            atom.x = -atom.x
        model.bonds.reverse()
        for bond in model.bonds:
            bond.a, bond.b = bond.b, bond.a
    expected = _expected(same_side=same_side, imine=imine, alias=alias)
    if alias:
        # General alias identifiers are deliberately unavailable. Their common
        # conversion graph/MOL export must still honor the drawn arrangement.
        before = deepcopy(model)
        adapter = RDKitAdapter()
        mol = adapter._build_conversion_rdkit_mol(model)
        assert mol is not None, adapter.last_error
        assert Chem.MolToSmiles(mol) == Chem.MolToSmiles(expected)
        exported = adapter.model_to_mol_block(model)
        assert exported is not None, adapter.last_error
        assert Chem.MolToSmiles(Chem.MolFromMolBlock(exported)) == Chem.MolToSmiles(
            expected
        )
        assert adapter.compute_identifiers(model).smiles is None
        assert model == before
    else:
        _assert_identifiers(model, expected)


@pytest.mark.parametrize("same_side", [False, True])
@pytest.mark.parametrize("imine", [False, True])
def test_native_mol_and_calculation_roundtrips_share_drawn_stereo(same_side, imine):
    model = _drawing(same_side=same_side, imine=imine)
    before = deepcopy(model)
    expected = _expected(same_side=same_side, imine=imine)
    adapter = RDKitAdapter()
    _assert_identifiers(deserialize_model_state(serialize_model_state(model)), expected)
    _assert_identifiers(parse_molfile(write_molfile(model)), expected)
    artifacts = adapter.model_to_calculation_artifacts(model)
    assert artifacts is not None, adapter.last_error
    for block in (adapter.model_to_mol_block(model), artifacts.mol_block):
        assert block is not None, adapter.last_error
        assert Chem.MolToSmiles(Chem.MolFromMolBlock(block)) == Chem.MolToSmiles(
            expected
        )
        _assert_identifiers(parse_molfile(block), expected)
    assert model == before


@pytest.mark.parametrize("same_side", [False, True])
@pytest.mark.parametrize("imine", [False, True])
def test_embedded_geometry_obeys_the_drawn_side_relation(same_side, imine):
    model = _drawing(same_side=same_side, imine=imine)
    before = deepcopy(model)
    adapter = RDKitAdapter()
    mol = adapter._build_conversion_rdkit_mol(model)
    assert mol is not None, adapter.last_error
    chem, all_chem = adapter._load_rdkit()
    embedded = adapter._embed_3d_molecule(mol, chem, all_chem)
    assert embedded is not None, adapter.last_error
    from rdkit.Chem import rdMolTransforms

    angle = abs(rdMolTransforms.GetDihedralDeg(embedded.GetConformer(), 0, 1, 2, 3))
    assert (angle < 30.0) if same_side else (angle > 150.0)
    scene = adapter.model_to_3d_scene(model)
    assert scene is not None, adapter.last_error
    xyz = adapter.model_to_xyz_block(model)
    assert xyz is not None, adapter.last_error
    # Public XYZ/preview output uses the same atom order for this one component.
    for positions in (
        [(atom.x, atom.y, atom.z) for atom in scene.atoms],
        [tuple(map(float, line.split()[1:])) for line in xyz.splitlines()[2:]],
    ):
        conformer = Chem.Conformer(len(positions))
        for index, position in enumerate(positions):
            conformer.SetAtomPosition(index, position)
        angle = abs(rdMolTransforms.GetDihedralDeg(conformer, 0, 1, 2, 3))
        assert (angle < 30.0) if same_side else (angle > 150.0)
    assert model == before


@pytest.mark.parametrize("same_side", [False, True])
def test_explicit_either_remains_unknown_despite_drawn_sides(same_side):
    model = _drawing(same_side=same_side)
    model.bonds[1].style = "double_either"
    before = deepcopy(model)
    adapter = RDKitAdapter()
    mol = adapter._build_conversion_rdkit_mol(model)
    assert mol is not None
    bond = mol.GetBondBetweenAtoms(1, 2)
    assert bond.GetStereo() == Chem.BondStereo.STEREOANY
    assert bond.GetBondDir() == Chem.BondDir.EITHERDOUBLE
    _assert_identifiers(model, Chem.MolFromSmiles("CC=CC"))
    assert model == before


def test_explicit_either_authorizes_unknown_geometry_even_for_degenerate_layout():
    model = _drawing()
    model.bonds[1].style = "double_either"
    for atom in model.atoms.values():
        atom.x = atom.y = 0.0
    _assert_identifiers(model, Chem.MolFromSmiles("CC=CC"))
    assert RDKitAdapter().model_to_xyz_block(model) is not None


@pytest.mark.parametrize("same_side", [False, True])
def test_explicit_hydrogen_display_compaction_preserves_drawn_double_stereo(same_side):
    model = _drawing(same_side=same_side)
    hydrogen = model.add_atom("H", 0.0, -30.0)
    model.add_bond(1, hydrogen)
    _assert_identifiers(model, _expected(same_side=same_side))


@pytest.mark.parametrize(
    "method",
    [
        "compute_identifiers",
        "model_to_3d_scene",
        "model_to_xyz_block",
        "model_to_mol_block",
        "model_to_calculation_artifacts",
    ],
)
@pytest.mark.parametrize(
    "ambiguity", ["collinear", "coincident", "overlap", "near_linear"]
)
def test_ambiguous_potential_double_depictions_refuse_conversion(ambiguity, method):
    model = _drawing()
    if ambiguity == "coincident":
        model.atoms[3].x, model.atoms[3].y = 60.0, 0.0
    elif ambiguity == "overlap":
        atom_id = model.add_atom("F", 0.0, 40.0)
        model.add_bond(1, atom_id)
    else:
        model.atoms[3].y = 0.0 if ambiguity == "collinear" else 0.01
    before = deepcopy(model)
    adapter = RDKitAdapter()
    result = getattr(adapter, method)(model)
    if method == "compute_identifiers":
        assert result.smiles is None and result.inchi is None
    else:
        assert result is None
    assert "bond 1 (atoms 1-2)" in adapter.last_error
    assert "double_either" in adapter.last_error
    assert "Correct" in adapter.last_error
    assert model == before


@pytest.mark.parametrize(
    "smiles,unknown_count",
    [
        ("CC=CC", 1),
        ("CN=CC", 1),
        ("C[C@H](O)C=CC", 1),
        ("CC=CC=CC", 2),
        ("C=C", 0),
        ("CC=O", 0),
        ("CC(C)=CC", 0),
        ("c1ccccc1", 0),
        ("C1=CCCCC1", 0),
    ],
)
def test_unspecified_smiles_does_not_gain_stereo_from_automatic_layout(
    smiles, unknown_count
):
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d(smiles)
    assert model is not None, adapter.last_error
    assert sum(bond.style == "double_either" for bond in model.bonds) == unknown_count
    _assert_identifiers(model, Chem.MolFromSmiles(smiles))


@pytest.mark.parametrize("smiles", ["C/C=C/C", "C/C=N/C", "C/C=C\\C"])
def test_specified_double_smiles_insertion_is_still_refused(smiles):
    adapter = RDKitAdapter()
    assert adapter.smiles_to_2d(smiles) is None
    assert "Double-bond" in adapter.last_error


@pytest.mark.parametrize(
    "smiles",
    [
        "C[C@H](O)/C=C/C",
        "C[C@H](O)/C=C\\C",
        "CO/N=C(/C)c1ccccc1",
        "CO/N=C(\\C)c1ccccc1",
        "C/[N+]([O-])=C/C",
        "C/[N+]([O-])=C\\C",
        "C/C=C/C=C/C",
    ],
)
def test_mol_depictions_keep_wedges_charged_imines_and_conjugated_stereo(smiles):
    from rdkit.Chem import AllChem

    expected = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(expected)
    model = parse_molfile(Chem.MolToMolBlock(expected))
    _assert_identifiers(model, expected)


@pytest.mark.parametrize("same_side", [False, True])
def test_non_carbon_double_endpoints_are_not_newly_assigned(same_side):
    model = _drawing(same_side=same_side, imine=True)
    model.atoms[1].element = "N"
    _assert_identifiers(model, Chem.MolFromSmiles("CN=NC"))


def test_drawn_double_perception_failure_is_not_silently_exported(monkeypatch):
    model = _drawing()
    before = deepcopy(model)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic double stereo failure")

    monkeypatch.setattr(Chem, "SetDoubleBondNeighborDirections", fail)
    adapter = RDKitAdapter()
    assert adapter._build_conversion_rdkit_mol(model) is None
    assert "double-bond stereochemistry" in adapter.last_error
    assert model == before
