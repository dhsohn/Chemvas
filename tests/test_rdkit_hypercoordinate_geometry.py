from __future__ import annotations

import importlib.util
from copy import deepcopy

import pytest

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
    from rdkit.Chem import AllChem

_THREE_DIMENSIONAL_RESULTS = (
    "model_to_3d_scene_result",
    "model_to_xyz_block_result",
    "model_to_calculation_artifacts_result",
)


@pytest.mark.parametrize("conversion", _THREE_DIMENSIONAL_RESULTS)
@pytest.mark.parametrize("smiles", ["F[P-](F)(F)(F)(F)F", "[P-](F)(F)(F)(F)(F)F"])
def test_six_coordinate_phosphorus_is_refused_before_geometry_generation(
    smiles, conversion, monkeypatch
):
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d(smiles)
    assert model is not None, adapter.last_error
    before = deepcopy(model)
    # This is not the already-covered missing-parameters case: the real backend
    # finds UFF atom types for PF6, but its six-coordinate geometry is unreliable.
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert not AllChem.MMFFHasAllMoleculeParams(mol)
    assert AllChem.UFFHasAllMoleculeParams(mol)
    original_embed = AllChem.EmbedMolecule
    embedded = []

    def record_embed(*args, **kwargs):
        embedded.append(True)
        return original_embed(*args, **kwargs)

    monkeypatch.setattr(AllChem, "EmbedMolecule", record_embed)
    result = getattr(adapter, conversion)(model)

    assert result.value is None
    assert result.error is not None
    assert "six-coordinate phosphorus" in result.error.lower()
    assert not embedded
    assert model == before


@pytest.mark.parametrize("conversion", _THREE_DIMENSIONAL_RESULTS)
@pytest.mark.parametrize(
    "smiles",
    [
        "CCO",
        "CP(C)C",
        "OP(=O)(O)O",
        "FP(F)(F)(F)F",
        "Cl[Zn-2](Cl)(Cl)Cl",
        "C[Al](C)C",
    ],
)
def test_other_supported_structures_keep_previous_generation(smiles, conversion):
    # Five-coordinate P is an unchanged-scope control, not a claim that its
    # generated geometry has been scientifically validated.
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d(smiles)
    assert model is not None, adapter.last_error
    before = deepcopy(model)

    first = getattr(adapter, conversion)(model)
    second = getattr(adapter, conversion)(model)

    assert first.error is None
    assert first.value is not None
    assert second == first
    assert model == before


@pytest.mark.parametrize("conversion", _THREE_DIMENSIONAL_RESULTS)
def test_mixed_document_does_not_return_partial_geometry(conversion):
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d("CCO.F[P-](F)(F)(F)(F)F")
    assert model is not None, adapter.last_error
    before = deepcopy(model)

    result = getattr(adapter, conversion)(model)

    assert result.value is None
    assert "six-coordinate phosphorus" in result.error.lower()
    assert model == before


@pytest.mark.parametrize(
    "smiles", ["FS(F)(F)(F)(F)F", "C[P+](C)(C)[Pd-2](Cl)(Cl)[P+](C)(C)C"]
)
def test_existing_missing_force_field_parameters_remain_a_distinct_refusal(smiles):
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d(smiles)
    assert model is not None, adapter.last_error
    before = deepcopy(model)

    result = adapter.model_to_calculation_artifacts_result(model)

    assert result.value is None
    assert "neither MMFF nor UFF" in result.error
    assert model == before


@pytest.mark.parametrize("conversion", _THREE_DIMENSIONAL_RESULTS)
def test_drawn_hydrogen_counts_as_one_of_six_phosphorus_neighbors(conversion):
    model = MoleculeModel()
    phosphorus = model.add_atom("P", 0.0, 0.0)
    for index, element in enumerate(("F", "F", "F", "F", "F", "H"), 1):
        neighbor = model.add_atom(element, float(index), 20.0)
        model.add_bond(phosphorus, neighbor)
    model.atom_annotations[phosphorus] = {"formal_charge": -1}
    before = deepcopy(model)

    result = getattr(RDKitAdapter(), conversion)(model)

    assert result.value is None
    assert "six-coordinate phosphorus" in result.error.lower()
    assert model == before


def test_generated_hydrogen_is_counted_after_add_hydrogens():
    adapter = RDKitAdapter()
    mol = Chem.MolFromSmiles("[PH-](F)(F)(F)(F)F")
    assert mol is not None
    assert mol.GetAtomWithIdx(0).GetDegree() == 5
    assert Chem.AddHs(mol).GetAtomWithIdx(0).GetDegree() == 6
    before = mol.ToBinary()

    result = adapter._embed_3d_molecule(mol, Chem, AllChem)

    assert result is None
    assert "six-coordinate phosphorus" in adapter.last_error.lower()
    assert mol.ToBinary() == before


def test_phosphorus_refusal_keeps_native_mol_and_identifier_paths_and_allows_retry():
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d("F[P-](F)(F)(F)(F)F")
    assert model is not None, adapter.last_error
    before = deepcopy(model)
    state = serialize_model_state(model)
    identifiers = adapter.compute_identifiers(model)
    mol_before = adapter.model_to_mol_block_result(model)
    assert mol_before.error is None
    assert mol_before.value is not None
    assert identifiers.formula == "F6P-"
    assert identifiers.smiles is not None

    rejected = adapter.model_to_xyz_block_result(model)

    assert rejected.value is None
    assert "six-coordinate phosphorus" in rejected.error.lower()
    assert adapter.model_to_mol_block_result(model) == mol_before
    assert adapter.compute_identifiers(model) == identifiers
    assert serialize_model_state(model) == state
    assert deserialize_model_state(state) == before
    assert model == before
    control = adapter.smiles_to_2d("CCO")
    assert control is not None, adapter.last_error
    retry = adapter.model_to_xyz_block_result(control)
    assert retry.value is not None
    assert retry.error is None
