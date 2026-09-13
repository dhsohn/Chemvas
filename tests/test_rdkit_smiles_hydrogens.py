from __future__ import annotations

import importlib.util
from copy import deepcopy
from itertools import pairwise

import pytest

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import MoleculeModel

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="optional RDKit dependency is not installed",
)

if importlib.util.find_spec("rdkit") is not None:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors


def _chain(elements):
    model = MoleculeModel()
    ids = [
        model.add_atom(element, index * 20.0, 0.0)
        for index, element in enumerate(elements)
    ]
    for left, right in pairwise(ids):
        model.add_bond(left, right)
    return model


def _parse_with_hydrogens(smiles):
    params = Chem.SmilesParserParams()
    params.removeHs = False
    mol = Chem.MolFromSmiles(smiles, params)
    assert mol is not None
    return mol


def _assert_identifiers(model, expected_smiles, monkeypatch, *, backend_mol=None):
    adapter = RDKitAdapter()
    original_model = deepcopy(model)
    mol = backend_mol
    if mol is None:
        mol = adapter._build_conversion_rdkit_mol(model)
        assert mol is not None, adapter.last_error
    original_mol = mol.ToBinary()
    original_with_h = Chem.AddHs(mol)
    expected_formula = rdMolDescriptors.CalcMolFormula(original_with_h)
    expected_weight = Descriptors.MolWt(original_with_h)
    original_for_inchi = Chem.Mol(mol)
    original_for_inchi.RemoveAllConformers()
    expected_inchi = Chem.MolToInchi(original_for_inchi)
    expected_key = Chem.MolToInchiKey(original_for_inchi)
    # Keep the actual conversion output observable: normalization must not
    # mutate the assigned graph subsequently used for InChI or calculation.
    monkeypatch.setattr(adapter, "_build_conversion_rdkit_mol", lambda _model: mol)

    result = adapter.compute_identifiers(model)

    assert result.smiles == expected_smiles
    assert result.formula == expected_formula
    assert result.mw == pytest.approx(expected_weight, rel=0.0, abs=1e-12)
    assert result.inchi == expected_inchi
    assert result.inchikey == expected_key
    assert model == original_model
    assert mol.ToBinary() == original_mol
    return result


@pytest.mark.parametrize(
    ("elements", "expected"),
    [
        (("C", "C", "O", "H"), "CCO"),
        (("C", "N", "H"), "CN"),
        (("C", "S", "H"), "CS"),
        (("O", "H"), "O"),
        (("N", "H"), "N"),
        (("C", "C", "O"), "CCO"),
        (("C", "OH"), "CO"),
        (("C", "NH2"), "CN"),
        (("C", "SH"), "CS"),
    ],
)
def test_native_ordinary_hydrogens_have_compact_display_only(
    elements, expected, monkeypatch
):
    _assert_identifiers(_chain(elements), expected, monkeypatch)


@pytest.mark.parametrize(
    ("style", "expected"),
    [("wedge", "CC[C@H](C)O"), ("hash", "CC[C@@H](C)O")],
)
def test_native_wedged_hydrogen_keeps_opposite_tetrahedral_identity(
    style, expected, monkeypatch
):
    model = MoleculeModel()
    for element, x, y in (
        ("C", 0, 0),
        ("H", 20, 0),
        ("C", -20, 20),
        ("O", -20, -20),
        ("C", 0, 30),
        ("C", 20, 45),
    ):
        model.add_atom(element, x, y)
    for other in range(1, 5):
        model.add_bond(0, other)
    model.add_bond(4, 5)
    model.bonds[0].style = style

    result = _assert_identifiers(model, expected, monkeypatch)

    assert result.inchikey == Chem.MolToInchiKey(Chem.MolFromSmiles(expected))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("[H][C@]12CCCC[C@@]1([H])CCCC2", "C1CC[C@H]2CCCC[C@H]2C1"),
        ("[H][C@]12CCCC[C@]1([H])CCCC2", "C1CC[C@H]2CCCC[C@@H]2C1"),
    ],
)
def test_native_explicit_ring_junction_hydrogens_keep_two_centre_stereo(
    source, expected, monkeypatch
):
    mol = _parse_with_hydrogens(source)
    AllChem.Compute2DCoords(mol)
    Chem.WedgeMolBonds(mol, mol.GetConformer())
    model = MoleculeModel()
    for atom in mol.GetAtoms():
        position = mol.GetConformer().GetAtomPosition(atom.GetIdx())
        model.add_atom(atom.GetSymbol(), position.x * 20, position.y * 20)
    for bond in mol.GetBonds():
        index = model.add_bond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
        model.bonds[index].style = {
            Chem.BondDir.BEGINWEDGE: "wedge",
            Chem.BondDir.BEGINDASH: "hash",
        }.get(bond.GetBondDir(), "single")
    assert sum(atom.element == "H" for atom in model.atoms.values()) == 2

    result = _assert_identifiers(model, expected, monkeypatch)

    assert result.inchikey == Chem.MolToInchiKey(Chem.MolFromSmiles(expected))


def test_native_bonded_positive_hydrogen_does_not_lose_charge(monkeypatch):
    model = _chain(("C", "H"))
    model.atom_annotations[1] = {"formal_charge": 1}

    result = _assert_identifiers(model, "[H+]C", monkeypatch)

    assert result.formula == "CH4+"


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        ({"formal_charge": 1}, "[H+].[H]OCC"),
        ({"radical_electrons": 1}, "[H].[H]OCC"),
    ],
)
def test_special_hydrogen_keeps_whole_molecule_display_spelling(
    annotation, expected, monkeypatch
):
    model = _chain(("C", "C", "O", "H"))
    special = model.add_atom("H", 100.0, 50.0)
    model.atom_annotations[special] = annotation

    _assert_identifiers(model, expected, monkeypatch)


def test_identifier_normalization_preserves_calculation_drawn_hydrogen_origin():
    model = _chain(("C", "C", "O", "H"))
    before_model = deepcopy(model)
    adapter = RDKitAdapter()
    before = adapter.model_to_calculation_artifacts(model)
    assert before is not None, adapter.last_error

    assert adapter.compute_identifiers(model).smiles == "CCO"
    after = adapter.model_to_calculation_artifacts(model)

    assert after is not None, adapter.last_error
    assert after.atom_map == before.atom_map
    assert after.mol_block == before.mol_block
    assert after.rdkit_formal_charge == before.rdkit_formal_charge
    assert after.rdkit_radical_electrons == before.rdkit_radical_electrons
    assert after.electron_count == before.electron_count
    assert any(
        entry.symbol == "H"
        and entry.origin == "chemvas_atom"
        and entry.chemvas_atom_id == 3
        for entry in after.atom_map
    )
    assert model == before_model


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("[1H]OCC", "[1H]OCC"),
        ("[2H]OCC", "[2H]OCC"),
        ("[3H]OCC", "[3H]OCC"),
        ("[H:7]OCC", "CCO[H:7]"),
        ("[H]", "[H]"),
        ("[H+]", "[H+]"),
        ("[H-]", "[H-]"),
        ("[H][H]", "[H][H]"),
        ("C[H-]C", "C[H-]C"),
        ("C[H-]", "[H-]C"),
        ("[H]/[C-]=C(/F)Cl", "[H]/[C-]=C(/F)Cl"),
        ("[H]/N=C(/F)Cl", "[H]/N=C(/F)Cl"),
    ],
)
def test_backend_special_hydrogens_are_not_ordinary_display_hydrogens(
    source, expected, monkeypatch
):
    # These exercise the real RDKit boundary, not native isotope, atom-map,
    # coordination, or specified E/Z support. Do not invent native fields.
    mol = _parse_with_hydrogens(source)
    _assert_identifiers(MoleculeModel(), expected, monkeypatch, backend_mol=mol)


@pytest.mark.parametrize("source", ["[1H]OCC", "[2H]OCC", "[3H]OCC"])
def test_isotope_backend_controls_do_not_expand_native_import_support(source):
    adapter = RDKitAdapter()

    assert adapter.smiles_to_2d(source) is None
    assert "isotope" in adapter.last_error


@pytest.mark.parametrize("source", ["[H]/[C-]=C(/F)Cl", "[H]/N=C(/F)Cl"])
def test_double_stereo_backend_controls_do_not_expand_native_import_support(source):
    adapter = RDKitAdapter()

    assert adapter.smiles_to_2d(source) is None
    assert "stereochemistry" in adapter.last_error


def test_general_alias_identifier_unavailability_is_unchanged():
    model = _chain(("C", "Me"))
    before = deepcopy(model)

    result = RDKitAdapter().compute_identifiers(model)

    assert result.smiles is None
    assert result.inchi is None
    assert model == before
