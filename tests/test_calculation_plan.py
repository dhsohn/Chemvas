"""Reader-only validation for calculation metadata in historical documents."""

from copy import deepcopy

import pytest

from chemvas.domain.document import (
    Atom,
    Bond,
    CalculationPlanGraphMismatchError,
    MoleculeModel,
    build_document_payload,
    calculation_plan_from_state,
    extract_document_state,
    model_bond_pairs,
    validate_calculation_plan,
)
from tests.calculation_plan_support import _document_state, _plan


def test_v7_document_round_trips_calculation_plan_v2_and_v6_rejects_it() -> None:
    state = _document_state()
    state["calculation_plan"] = _plan()

    payload = build_document_payload(state, 7)

    assert extract_document_state(payload)["calculation_plan"] == _plan()
    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        build_document_payload(state, 6)


@pytest.mark.parametrize("version", [1, 2.0, True])
def test_non_current_calculation_plan_versions_are_rejected(version: object) -> None:
    state = _document_state()
    plan = _plan()
    plan["version"] = version

    with pytest.raises(ValueError, match="Invalid Chemvas calculation plan"):
        validate_calculation_plan(state, plan)


def test_plan_roles_are_endpoint_specific_when_a_state_is_reused() -> None:
    state = _document_state()
    raw_plan = _plan()
    reverse = deepcopy(raw_plan["steps"][0])  # type: ignore[index]
    reverse["id"] = "S02"
    reverse["reactant"], reverse["product"] = (
        reverse["product"],
        reverse["reactant"],
    )
    reverse["reactant"]["roles"][0]["role"] = "reactant"
    reverse["product"]["roles"][0]["role"] = "product"
    reverse["atom_correspondence"] = [
        {"reactant_atom_id": 2, "product_atom_id": 0},
        {"reactant_atom_id": 3, "product_atom_id": 1},
        {"reactant_atom_id": 4, "product_atom_id": 4},
    ]
    raw_plan["steps"].append(reverse)  # type: ignore[union-attr]

    plan = validate_calculation_plan(state, raw_plan)

    assert plan.steps[0].product.roles[0].role == "product"
    assert plan.steps[1].reactant.roles[0].role == "reactant"
    assert plan.steps[0].product.state_id == plan.steps[1].reactant.state_id


def test_plan_rejects_partial_components_and_context_only_reactant_role() -> None:
    state = _document_state()
    model_state = state["model"]
    assert isinstance(model_state, dict)
    model = MoleculeModel(
        atoms={
            int(atom_id): Atom(str(atom["element"]), float(atom["x"]), float(atom["y"]))
            for atom_id, atom in model_state["atoms"].items()
        },
        bonds=[Bond(0, 1, order=2), Bond(2, 3, order=1)],
    )
    partial = _plan()
    partial["states"][0]["members"][0]["component_atom_ids"] = [0]  # type: ignore[index]
    with pytest.raises(
        CalculationPlanGraphMismatchError, match="complete connected component"
    ):
        calculation_plan_from_state(
            partial,
            atom_ids=set(model.atoms),
            bond_pairs=model_bond_pairs(model),
        )

    bad_role = _plan()
    bad_role["steps"][0]["reactant"]["roles"][2]["role"] = "reactant"  # type: ignore[index]
    with pytest.raises(ValueError, match="context-only") as raised:
        calculation_plan_from_state(
            bad_role,
            atom_ids=set(model.atoms),
            bond_pairs=model_bond_pairs(model),
        )
    # Only references the drawing no longer resolves are a graph mismatch; a
    # plan that contradicts itself is invalid whatever the drawing looks like.
    assert not isinstance(raised.value, CalculationPlanGraphMismatchError)


def test_semantic_validation_rejects_state_charge_drift() -> None:
    state = _document_state()
    bad = _plan()
    bad["states"][0]["charge"] = 1  # type: ignore[index]

    with pytest.raises(ValueError, match="modeled formal charge 0"):
        validate_calculation_plan(state, bad)


def test_plan_rejects_duplicate_product_atom_correspondence() -> None:
    state = _document_state()
    bad = _plan()
    bad["steps"][0]["atom_correspondence"][1]["product_atom_id"] = 2  # type: ignore[index]

    with pytest.raises(ValueError, match="invalid atom correspondence"):
        validate_calculation_plan(state, bad)


def test_plan_rejects_mapped_atoms_with_different_elements() -> None:
    state = _document_state()
    bad = _plan()
    bad["steps"][0]["atom_correspondence"] = [  # type: ignore[index]
        {"reactant_atom_id": 0, "product_atom_id": 3},
        {"reactant_atom_id": 1, "product_atom_id": 2},
        {"reactant_atom_id": 4, "product_atom_id": 4},
    ]

    with pytest.raises(ValueError, match="mapped atom labels must match"):
        validate_calculation_plan(state, bad)
