from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import pytest

import chemvas.domain.document.inspection as document_inspection
from chemvas.bootstrap import calculation_bundle as cli
from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
)
from chemvas.features.calculation_bundle import (
    calculate_bond_changes,
    calculation_plan_for_document,
    calculation_state_by_id,
    calculation_step_by_id,
    path_precheck,
    prepare_calculation_step,
    require_step_ready,
    select_calculation_state,
    select_components,
)
from tests.calculation_artifact_support import _StateFakeAdapter
from tests.calculation_plan_support import _document_state, _plan
from tests.calculation_workflow_support import (
    _legacy_reviewed_precomplex_payload,
    _path_ready_state,
)


def _state():
    state = _document_state()
    state["calculation_plan"] = _plan()
    return state


def _separate_preparation(state, step_id="S01"):
    """The former pack sequence, through unchanged independent public APIs."""
    plan = calculation_plan_for_document(state)
    step = calculation_step_by_id(plan, step_id)
    require_step_ready(plan, step)
    precheck = path_precheck(plan, step)
    selections = tuple(
        select_calculation_state(
            state, calculation_state_by_id(plan, endpoint.state_id)
        )
        for endpoint in (step.reactant, step.product)
    )
    return plan, step, precheck, selections


def _separate_component_selections(state, plan, step):
    return tuple(
        tuple(
            select_components(state, [member.component_atom_ids])
            for member in calculation_state_by_id(plan, endpoint.state_id).members
            if member.inclusion == "included"
        )
        for endpoint in (step.reactant, step.product)
    )


@pytest.mark.parametrize("single_component", [False, True])
@pytest.mark.parametrize("reverse_members", [False, True])
def test_preparation_matches_independent_apis_without_mutation(
    single_component, reverse_members
):
    state = _path_ready_state() if single_component else _state()
    if reverse_members:
        for calculation_state in state["calculation_plan"]["states"]:
            calculation_state["members"].reverse()
    before = deepcopy(state)
    expected_plan, expected_step, expected_precheck, expected_selections = (
        _separate_preparation(state)
    )
    expected_changes = calculate_bond_changes(state, expected_plan, expected_step)
    expected_components = _separate_component_selections(
        state, expected_plan, expected_step
    )
    with patch.object(
        document_inspection,
        "deserialize_model_state",
        wraps=document_inspection.deserialize_model_state,
    ) as deserialize:
        prepared = prepare_calculation_step(state, "S01")
        assert prepared.plan == expected_plan
        assert prepared.step == expected_step
        assert prepared.precheck == expected_precheck
        assert (
            prepared.reactant_selection,
            prepared.product_selection,
        ) == expected_selections
        assert (
            prepared.reactant_component_selections,
            prepared.product_component_selections,
        ) == expected_components
        assert prepared.bond_changes() == expected_changes
    assert deserialize.call_count == 1
    assert state == before
    expected_count = 1 if single_component else 2
    for side_selections in expected_components:
        assert len(side_selections) == expected_count
        assert all(len(item.component_indices) == 1 for item in side_selections)
    prepared.reactant_selection.model.atoms[0].x += 1
    prepared.reactant_component_selections[0].model.atoms[
        prepared.reactant_component_selections[0].atom_ids[0]
    ].x += 1
    assert prepared.bond_changes() == expected_changes
    assert state == before


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("missing-plan", "The Chemvas document does not contain a calculation plan."),
        ("structural-plan", "Invalid Chemvas calculation plan."),
        ("marks", "Invalid Chemvas document state: marks are invalid."),
        ("charge", "State R01 declares charge 7"),
        ("missing-step", "Calculation step 'missing' does not exist; available: S01."),
        (
            "incomplete-mapping",
            "Step S01 does not have a complete one-to-one correspondence",
        ),
    ],
)
def test_preparation_retains_error_priority_and_exact_public_error(defect, message):
    state = _state()
    step_id = "S01"
    if defect == "missing-plan":
        del state["calculation_plan"]
        state["model"] = None
    elif defect == "structural-plan":
        state["calculation_plan"] = {}
        state["marks"] = "invalid"
    elif defect == "marks":
        state["marks"] = "invalid"
        state["calculation_plan"]["states"][0]["charge"] = 7
    elif defect == "charge":
        state["calculation_plan"]["states"][0]["charge"] = 7
        step_id = "missing"
    elif defect == "missing-step":
        step_id = "missing"
    else:
        state["calculation_plan"] = _plan(complete_mapping=False)
    before = deepcopy(state)
    with pytest.raises(ValueError) as separate:
        _separate_preparation(state, step_id)
    with pytest.raises(ValueError) as prepared:
        prepare_calculation_step(state, step_id)
    assert str(prepared.value) == str(separate.value)
    assert str(prepared.value).startswith(message)
    assert state == before


def test_new_request_observes_changes_to_the_same_source_object():
    state = _state()
    first = prepare_calculation_step(state, "S01")
    state["model"]["atoms"][0]["x"] += 7
    state["marks"] = [{"atom_id": 0, "kind": "plus"}]
    state["calculation_plan"]["states"][0]["charge"] = 1
    second = prepare_calculation_step(state, "S01")
    assert first.reactant_selection.formal_charge == 0
    assert second.reactant_selection.formal_charge == 1
    assert (
        first.reactant_selection.model.atoms[0].x + 7
        == second.reactant_selection.model.atoms[0].x
    )
    assert first.precheck.charge_matches
    assert not second.precheck.charge_matches


def test_standalone_selection_does_not_validate_unselected_aliases():
    model = MoleculeModel(
        atoms={0: Atom("C", 0, 0), 1: Atom("C", 1, 0), 2: Atom("PPh3", 3, 0)},
        bonds=[Bond(0, 1)],
    )
    state = {"model": serialize_model_state(model), "marks": []}
    selected = select_components(state, [[0, 1]])
    assert selected.atom_ids == (0, 1)
    with pytest.raises(ValueError, match="PPh3"):
        select_components(state, [[2]])


@pytest.mark.parametrize("electronic_mark", [None, "plus", "radical"])
def test_preparation_preserves_intrinsic_alias_charge_and_electronic_marks(
    electronic_mark,
):
    state = _state()
    for atom_id in (1, 3):
        state["model"]["atoms"][atom_id]["element"] = "PPh3"
    for bond in state["model"]["bonds"]:
        bond.update(order=1, style="single")
    if electronic_mark:
        state["marks"] = [
            {"atom_id": atom_id, "kind": electronic_mark} for atom_id in (0, 2)
        ]
    charge = 2 if electronic_mark == "plus" else 1
    radicals = 1 if electronic_mark == "radical" else 0
    for calculation_state in state["calculation_plan"]["states"]:
        calculation_state["charge"] = charge
    before = deepcopy(state)
    _plan_result, _step, _precheck, expected = _separate_preparation(state)
    prepared = prepare_calculation_step(state, "S01")
    for actual, selected in zip(
        (prepared.reactant_selection, prepared.product_selection), expected, strict=True
    ):
        assert actual == selected
        assert actual.formal_charge == charge
        assert actual.radical_electrons == radicals
    assert state == before


def test_legacy_reviewed_precomplex_does_not_change_step_preparation():
    legacy = _legacy_reviewed_precomplex_payload()["state"]
    cleared = deepcopy(legacy)
    for side in ("reactant", "product"):
        cleared["calculation_plan"]["steps"][0][side]["precomplex"] = {"kind": "none"}
    before = deepcopy(legacy)

    prepared = prepare_calculation_step(legacy, "S01")
    baseline = prepare_calculation_step(cleared, "S01")

    assert prepared.step.reactant.precomplex.kind == "candidate_ensemble"
    assert prepared.precheck == baseline.precheck
    assert prepared.precheck.ready_for_path_endpoints is True
    assert prepared.reactant_component_selections == (
        baseline.reactant_component_selections
    )
    assert prepared.product_component_selections == (
        baseline.product_component_selections
    )
    assert prepared.bond_changes() == baseline.bond_changes()
    assert legacy == before


def test_pack_step_prepares_the_source_model_once(tmp_path, monkeypatch):
    state = _state()
    source = tmp_path / "source.chemvas"
    write_document(source, state, CANVAS_FILE_VERSION)
    original = source.read_bytes()
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)
    with patch.object(
        document_inspection,
        "deserialize_model_state",
        wraps=document_inspection.deserialize_model_state,
    ) as deserialize:
        result = cli._pack_step(source, step_id="S01", output=tmp_path / "machine.json")
    assert result["handoff"]["status"] == "ready"
    assert source.read_bytes() == original
    assert deserialize.call_count == 1


def test_pack_step_retry_has_identical_artifacts_and_source(tmp_path, monkeypatch):
    source = tmp_path / "source.chemvas"
    state = _state()
    before = deepcopy(state)
    write_document(source, state, CANVAS_FILE_VERSION)
    original = source.read_bytes()
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)
    outputs = [tmp_path / name / "machine.json" for name in ("first", "second")]
    for path in outputs:
        path.parent.mkdir()
    results = [cli._pack_step(source, step_id="S01", output=path) for path in outputs]
    assert results[0] == results[1]
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert source.read_bytes() == original
    assert state == before


@pytest.mark.parametrize("failure", ["raise", "unavailable"])
def test_pack_step_backend_failure_publishes_nothing_and_retry_succeeds(
    tmp_path, monkeypatch, failure
):
    class BrokenAdapter(_StateFakeAdapter):
        def model_to_calculation_artifacts(self, model, atom_annotations=None):
            if failure == "raise":
                raise ValueError("backend failure")
            self.last_error = "backend unavailable"
            return None

    source = tmp_path / "source.chemvas"
    write_document(source, _state(), CANVAS_FILE_VERSION)
    original = source.read_bytes()
    output = tmp_path / "machine.json"
    monkeypatch.setattr(cli, "RDKitAdapter", BrokenAdapter)
    expected = (
        "backend failure" if failure == "raise" else "State R01: backend unavailable"
    )
    with pytest.raises(ValueError) as caught:
        cli._pack_step(source, step_id="S01", output=output)
    assert str(caught.value) == expected
    assert not output.exists()
    assert source.read_bytes() == original
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)
    cli._pack_step(source, step_id="S01", output=output)
    assert output.exists()
