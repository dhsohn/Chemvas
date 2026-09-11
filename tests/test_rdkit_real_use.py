from __future__ import annotations

import importlib.util
from copy import deepcopy

import pytest

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import Atom, Bond, MoleculeModel

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="optional RDKit dependency is not installed",
)

if importlib.util.find_spec("rdkit") is not None:
    from rdkit import Chem

TROGERS = "Cc1ccc2c(c1)C[N@]1Cc3cc(C)ccc3[N@](C2)C1"
QUININE = "COc1ccc2nccc([C@@H](O)[C@@H]3C[C@@H]4CCN3C[C@@H]4C=C)c2c1"
ARTEMISININ = "C[C@@H]1CC[C@H]2[C@H](C(=O)O[C@H]3[C@@]24[C@H]1CC[C@](O3)(OO4)C)C"


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    "conversion",
    ["compute_identifiers", "model_to_calculation_artifacts", "model_to_3d_scene"],
)
def test_conflicting_wedges_are_refused_in_any_bond_order(reverse, conversion):
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d("C[C@@H](O)CC")
    assert model is not None
    assert [(bond.a, bond.b) for bond in model.bonds[:3]] == [(1, 0), (1, 2), (1, 3)]
    model.bonds[1].style = "wedge"
    model.bonds[2].style = "hash"
    if reverse:
        model.bonds.reverse()
    before = deepcopy(model)
    result = getattr(adapter, conversion)(model)
    if conversion == "compute_identifiers":
        assert result.smiles is None
        assert result.inchi is None
        assert result.inchikey is None
    else:
        assert result is None
    assert "Conflicting wedge/hash" in adapter.last_error
    assert "atom 1" in adapter.last_error
    assert "bonds" in adapter.last_error
    assert model == before


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_consistent_multiple_wedges_keep_identifiers(reverse, style):
    adapter = RDKitAdapter()
    source = "C[C@@H](O)CC" if style == "wedge" else "C[C@H](O)CC"
    model = adapter.smiles_to_2d(source)
    assert model is not None
    for bond in model.bonds:
        if bond.a == 1:
            bond.style = style
    if reverse:
        model.bonds.reverse()
    before = deepcopy(model)
    identifiers = adapter.compute_identifiers(model)
    expected = Chem.MolFromSmiles(source)
    assert identifiers.smiles == Chem.MolToSmiles(expected), adapter.last_error
    assert identifiers.inchikey == Chem.MolToInchiKey(expected)
    assert model == before


@pytest.mark.parametrize("reverse", [False, True])
def test_consistent_mixed_wedge_hash_at_four_ligand_centre_is_supported(reverse):
    adapter = RDKitAdapter()
    source = "F[C@](Cl)(Br)I"
    model = adapter.smiles_to_2d(source)
    assert model is not None
    assert [(bond.a, bond.b) for bond in model.bonds] == [
        (1, 0),
        (1, 2),
        (1, 3),
        (1, 4),
    ]
    model.bonds[0].style = "hash"
    model.bonds[2].style = "wedge"
    if reverse:
        model.bonds.reverse()
    before = deepcopy(model)
    identifiers = adapter.compute_identifiers(model)
    expected = Chem.MolFromSmiles(source)
    assert identifiers.smiles == Chem.MolToSmiles(expected), adapter.last_error
    assert identifiers.inchikey == Chem.MolToInchiKey(expected)
    assert model == before


@pytest.mark.parametrize("smiles", [TROGERS, QUININE, "C[C@@H](O)c1ccccc1"])
def test_inserted_tetrahedral_structure_keeps_identifiers(smiles: str) -> None:
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d(smiles)
    assert model is not None, adapter.last_error
    before = deepcopy(model)
    identifiers = adapter.compute_identifiers(model)
    expected = Chem.MolFromSmiles(smiles)
    assert identifiers.smiles == Chem.MolToSmiles(expected)
    assert identifiers.inchikey == Chem.MolToInchiKey(expected)
    assert model == before


def test_insertion_refuses_depiction_that_loses_specified_tetrahedral_stereo() -> None:
    adapter = RDKitAdapter()
    assert adapter.smiles_to_2d(ARTEMISININ) is None
    assert "stereochemistry" in adapter.last_error
    assert "depiction" in adapter.last_error


def test_non_kekulizable_smiles_names_aromaticity_instead_of_syntax() -> None:
    adapter = RDKitAdapter()
    assert adapter.smiles_to_2d("c1cccc1") is None
    assert "Kekul" in adapter.last_error
    assert adapter.smiles_to_2d("not-a-smiles(") is None
    assert "Invalid SMILES" in adapter.last_error
    assert adapter.smiles_to_2d("c1ccccc1") is not None


@pytest.mark.parametrize(
    "conversion", ["model_to_calculation_artifacts", "model_to_3d_scene"]
)
@pytest.mark.parametrize("with_alias", [False, True])
def test_valence_error_names_stable_chemvas_atom_id(conversion, with_alias) -> None:
    model = MoleculeModel(
        atoms={i: Atom("C", float(i), 0.0) for i in (40, 41, 42, 47, 52)},
        bonds=[Bond(47, other) for other in (40, 41, 42, 52)],
        atom_annotations={47: {"formal_charge": 1}},
    )
    if with_alias:
        model.atoms[40].element = "Ph"
    adapter = RDKitAdapter()
    before = deepcopy(model)
    assert getattr(adapter, conversion)(model) is None
    assert "Chemvas atom 47" in adapter.last_error
    assert "C" in adapter.last_error
    assert model == before


@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_unconsumed_backwards_wedge_is_refused_without_mutating_drawing(style) -> None:
    model = MoleculeModel(
        atoms={
            4: Atom("C", 0.0, 0.0),
            7: Atom("O", 0.0, -20.0),
            10: Atom("C", -20.0, 15.0),
            12: Atom("C", 20.0, 15.0),
            16: Atom("C", 40.0, 15.0),
        },
        bonds=[Bond(7, 4, style=style), Bond(4, 10), Bond(4, 12), Bond(12, 16)],
    )
    adapter = RDKitAdapter()
    before = deepcopy(model)
    assert adapter.model_to_3d_scene(model) is None
    assert "Bond 0" in adapter.last_error
    assert "atom 7" in adapter.last_error
    assert "tetrahedral" in adapter.last_error
    assert model == before


@pytest.mark.parametrize(
    "smiles", ["C[P+](C)(C)[Pd-2](Cl)(Cl)[P+](C)(C)C", "FS(F)(F)(F)(F)F"]
)
def test_geometry_without_force_field_parameters_is_refused(smiles, monkeypatch):
    from rdkit.Chem import AllChem

    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d(smiles)
    assert model is not None
    before = deepcopy(model)

    def should_not_optimize(*args, **kwargs):
        pytest.fail("must not optimize with missing UFF parameters")

    monkeypatch.setattr(AllChem, "UFFOptimizeMolecule", should_not_optimize)
    assert adapter.model_to_calculation_artifacts(model) is None
    assert "parameters" in adapter.last_error
    assert model == before


def test_parameterized_zinc_geometry_remains_supported():
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d("Cl[Zn-2](Cl)(Cl)Cl")
    assert model is not None
    assert adapter.model_to_calculation_artifacts(model) is not None, adapter.last_error


def test_failed_mmff_does_not_fall_back_to_unparameterized_uff(monkeypatch):
    from rdkit.Chem import AllChem

    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d("CO")
    assert model is not None

    def fail_mmff(*args, **kwargs):
        raise ValueError("synthetic optimization failure")

    def unexpected_uff(*args, **kwargs):
        pytest.fail("fallback must retain the UFF parameter gate")

    monkeypatch.setattr(AllChem, "MMFFOptimizeMolecule", fail_mmff)
    monkeypatch.setattr(AllChem, "UFFHasAllMoleculeParams", lambda _mol: False)
    monkeypatch.setattr(AllChem, "UFFOptimizeMolecule", unexpected_uff)
    assert adapter.model_to_3d_scene(model) is None
    assert "fallback parameters" in adapter.last_error


@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_axial_wedge_on_binol_is_not_silently_treated_as_plain(style):
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d("Oc1ccc2ccccc2c1-c1c(O)ccc2ccccc12")
    assert model is not None
    # The connecting biaryl bond joins two sp2 axis atoms. The adjacent ring
    # wedge starts at an axis atom, the drawn atropisomer convention of #267.
    axis = next(bond for bond in model.bonds if {bond.a, bond.b} == {10, 11})
    ring_bond = next(
        bond
        for bond in model.bonds
        if bond is not axis and 11 in {bond.a, bond.b} and bond.order == 1
    )
    if ring_bond.a != 11:
        ring_bond.a, ring_bond.b = ring_bond.b, ring_bond.a
    ring_bond.style = style
    before = deepcopy(model)
    assert adapter.model_to_calculation_artifacts(model) is None
    assert "axial" in adapter.last_error
    assert "atom 11" in adapter.last_error
    assert model == before
