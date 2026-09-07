from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from chemvas.domain.document import (
    CalculationAtomCorrespondence,
    calculation_plan_to_state,
)
from chemvas.domain.document import state as document_state_module
from chemvas.features.calculation_bundle import (
    apply_calculation_step_edit,
    calculation_plan_for_document,
    calculation_plan_report,
    prepare_calculation_step_editor,
    validate_calculation_plan,
)
from tests.test_calculation_plan import _document_state, _plan
from tests.test_precomplex_cli import _generate_candidate_fixture

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def reviewed_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict:
    _source, _candidates, payload = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    state = payload["state"]
    for side in ("reactant", "product"):
        precomplex = state["calculation_plan"]["steps"][0][side]["precomplex"]
        candidate = precomplex["candidates"][0]
        precomplex["selection"] = {
            "candidate_id": candidate["id"],
            "candidate_xyz_sha256": candidate["xyz_sha256"],
            "reviewer": "test-reviewer",
            "reviewed_at": "2026-09-07T00:00:00Z",
            "acceptance_statement": "accepted_for_path_endpoint_review",
        }
    return state


def test_editor_preparation_keeps_a_charge_draft_open_but_acceptance_rejects_it() -> (
    None
):
    state = _document_state()
    state["calculation_plan"] = _plan()
    state["calculation_plan"]["states"][0]["charge"] = 7

    inventory, plan = prepare_calculation_step_editor(state)

    assert len(inventory.model.atoms) == 6
    assert plan is not None
    assert plan.states[0].charge == 7
    with pytest.raises(ValueError, match="declares charge 7"):
        apply_calculation_step_edit(
            state,
            current_plan=plan,
            selected_step_id="S01",
            reactant_state=plan.states[0],
            product_state=plan.states[1],
            step=plan.steps[0],
        )


def test_editor_preparation_keeps_mark_errors_before_invalid_plan_errors() -> None:
    state = _document_state()
    state["calculation_plan"] = {}
    state["marks"] = "invalid"

    with pytest.raises(ValueError) as error:
        prepare_calculation_step_editor(state)

    assert str(error.value) == "Invalid Chemvas document state: marks are invalid."


def test_new_step_accepts_partial_correspondence() -> None:
    state = _document_state()
    raw_plan = _plan(complete_mapping=False)
    draft = validate_calculation_plan(state, raw_plan)

    accepted = apply_calculation_step_edit(
        state,
        current_plan=None,
        selected_step_id=None,
        reactant_state=draft.states[0],
        product_state=draft.states[1],
        step=draft.steps[0],
    )

    assert calculation_plan_to_state(accepted) == raw_plan


def test_new_step_collision_precedes_invalid_draft_semantics() -> None:
    state = _document_state()
    plan = validate_calculation_plan(state, _plan())
    with pytest.raises(
        ValueError, match=r"Step S01 already exists\. Select Edit S01 instead\."
    ):
        apply_calculation_step_edit(
            state,
            current_plan=plan,
            selected_step_id=None,
            reactant_state=replace(plan.states[0], charge=7),
            product_state=plan.states[1],
            step=plan.steps[0],
        )


def test_edit_keeps_shared_state_protection() -> None:
    state = _document_state()
    raw_plan = _plan()
    second_step = deepcopy(raw_plan["steps"][0])
    second_step["id"] = "S02"
    raw_plan["steps"].append(second_step)
    plan = validate_calculation_plan(state, raw_plan)

    with pytest.raises(ValueError, match="State R01 is used by another step"):
        apply_calculation_step_edit(
            state,
            current_plan=plan,
            selected_step_id="S01",
            reactant_state=replace(plan.states[0], multiplicity=3),
            product_state=plan.states[1],
            step=plan.steps[0],
        )


def test_noop_edit_preserves_both_reviewed_endpoints_without_mutating_input(
    reviewed_state: dict,
) -> None:
    before = deepcopy(reviewed_state)
    plan = calculation_plan_for_document(reviewed_state)
    accepted = apply_calculation_step_edit(
        reviewed_state,
        current_plan=plan,
        selected_step_id="S01",
        reactant_state=plan.states[0],
        product_state=plan.states[1],
        step=plan.steps[0],
    )

    assert calculation_plan_to_state(accepted) == before["calculation_plan"]
    assert reviewed_state == before


@pytest.mark.parametrize("changed", ["role", "multiplicity", "mapping", "state_id"])
def test_dependency_edit_discards_the_review_pair_including_carried_draft_payloads(
    reviewed_state: dict, changed: str
) -> None:
    before = deepcopy(reviewed_state)
    plan = calculation_plan_for_document(reviewed_state)
    reactant = plan.states[0]
    step = plan.steps[0]
    if changed == "role":
        roles = tuple(
            replace(role, role="spectator") if role.role == "catalyst" else role
            for role in step.reactant.roles
        )
        step = replace(step, reactant=replace(step.reactant, roles=roles))
    elif changed == "multiplicity":
        reactant = replace(reactant, multiplicity=3)
    elif changed == "mapping":
        step = replace(step, atom_correspondence=step.atom_correspondence[:-1])
    else:
        reactant = replace(reactant, id="R02")
        step = replace(step, reactant=replace(step.reactant, state_id="R02"))

    accepted = apply_calculation_step_edit(
        reviewed_state,
        current_plan=plan,
        selected_step_id="S01",
        reactant_state=reactant,
        product_state=plan.states[1],
        step=step,
    )

    for endpoint in (accepted.steps[0].reactant, accepted.steps[0].product):
        assert endpoint.precomplex.kind == "none"
    assert reviewed_state == before


def test_editor_acceptance_still_runs_mapping_validation() -> None:
    state = _document_state()
    plan = validate_calculation_plan(state, _plan())
    invalid = replace(
        plan.steps[0],
        atom_correspondence=(
            CalculationAtomCorrespondence(0, 2),
            CalculationAtomCorrespondence(1, 2),
        ),
    )
    with pytest.raises(ValueError, match="correspondence"):
        apply_calculation_step_edit(
            state,
            current_plan=plan,
            selected_step_id="S01",
            reactant_state=plan.states[0],
            product_state=plan.states[1],
            step=invalid,
        )


def test_reviewed_report_reuses_inventory_for_both_endpoint_basis_checks(
    reviewed_state: dict,
) -> None:
    with patch.object(
        document_state_module,
        "MoleculeModel",
        wraps=document_state_module.MoleculeModel,
    ) as model_construction:
        report = calculation_plan_report(reviewed_state)

    assert report["steps"][0]["path_precheck"]["ready_for_path_endpoints"] is True
    assert model_construction.call_count == 1
