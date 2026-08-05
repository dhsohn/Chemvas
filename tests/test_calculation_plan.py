from __future__ import annotations

from copy import deepcopy

import pytest
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    CalculationAtomCorrespondence,
    CalculationState,
    CalculationStateMember,
    MoleculeModel,
    build_document_payload,
    calculation_plan_from_state,
    extract_document_state,
    model_bond_pairs,
    serialize_model_state,
    serialize_settings,
)
from chemvas.features.calculation_bundle import (
    calculate_bond_changes,
    calculation_plan_report,
    calculation_step_by_id,
    correspondence_readiness,
    require_step_ready,
    validate_calculation_plan,
)


def _document_state() -> dict[str, object]:
    model = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("O", 1.0, 0.0),
            2: Atom("C", 4.0, 0.0),
            3: Atom("O", 5.0, 0.0),
            4: Atom("Pt", 2.5, 3.0),
            5: Atom("Cl", 2.5, -3.0),
        },
        bonds=[Bond(0, 1, order=2), Bond(2, 3, order=1)],
    )
    return {
        "model": serialize_model_state(model),
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=18.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=600,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }


def _plan(*, complete_mapping: bool = True) -> dict[str, object]:
    correspondence = [
        {"reactant_atom_id": 0, "product_atom_id": 2},
        {"reactant_atom_id": 1, "product_atom_id": 3},
        {"reactant_atom_id": 4, "product_atom_id": 4},
    ]
    if not complete_mapping:
        correspondence.pop()
    return {
        "format": "chemvas-calculation-plan",
        "version": 1,
        "states": [
            {
                "id": "R01",
                "charge": 0,
                "multiplicity": 1,
                "members": [
                    {"component_atom_ids": [0, 1], "inclusion": "included"},
                    {"component_atom_ids": [4], "inclusion": "included"},
                    {"component_atom_ids": [5], "inclusion": "context_only"},
                ],
            },
            {
                "id": "P01",
                "charge": 0,
                "multiplicity": 1,
                "members": [
                    {"component_atom_ids": [2, 3], "inclusion": "included"},
                    {"component_atom_ids": [4], "inclusion": "included"},
                    {"component_atom_ids": [5], "inclusion": "context_only"},
                ],
            },
        ],
        "steps": [
            {
                "id": "S01",
                "reactant": {
                    "state_id": "R01",
                    "roles": [
                        {"component_atom_ids": [0, 1], "role": "reactant"},
                        {"component_atom_ids": [4], "role": "catalyst"},
                        {"component_atom_ids": [5], "role": "spectator"},
                    ],
                },
                "product": {
                    "state_id": "P01",
                    "roles": [
                        {"component_atom_ids": [2, 3], "role": "product"},
                        {"component_atom_ids": [4], "role": "catalyst"},
                        {"component_atom_ids": [5], "role": "spectator"},
                    ],
                },
                "atom_correspondence": correspondence,
            }
        ],
    }


def test_v5_document_round_trips_calculation_plan_and_v4_rejects_it() -> None:
    state = _document_state()
    state["calculation_plan"] = _plan()

    payload = build_document_payload(state, CANVAS_FILE_VERSION)

    assert extract_document_state(payload)["calculation_plan"] == _plan()
    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        build_document_payload(state, 4)


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
    with pytest.raises(ValueError, match="complete connected component"):
        calculation_plan_from_state(
            partial,
            atom_ids=set(model.atoms),
            bond_pairs=model_bond_pairs(model),
        )

    bad_role = _plan()
    bad_role["steps"][0]["reactant"]["roles"][2]["role"] = "reactant"  # type: ignore[index]
    with pytest.raises(ValueError, match="context-only"):
        calculation_plan_from_state(
            bad_role,
            atom_ids=set(model.atoms),
            bond_pairs=model_bond_pairs(model),
        )


def test_partial_mapping_is_storable_but_not_step_pack_ready() -> None:
    state = _document_state()
    state["calculation_plan"] = _plan(complete_mapping=False)

    report = calculation_plan_report(state)
    plan = validate_calculation_plan(state, state["calculation_plan"])
    step = calculation_step_by_id(plan, "S01")

    assert report["steps"][0]["readiness"]["mapping_complete"] is False  # type: ignore[index]
    with pytest.raises(ValueError, match="complete one-to-one"):
        require_step_ready(plan, step)


def test_bond_change_uses_explicit_atom_correspondence() -> None:
    state = _document_state()
    plan = validate_calculation_plan(state, _plan())
    step = calculation_step_by_id(plan, "S01")

    changes = calculate_bond_changes(state, plan, step)

    assert changes == (
        {
            "kind": "order_changed",
            "reactant_atom_ids": [0, 1],
            "product_atom_ids": [2, 3],
            "reactant_order": 2,
            "product_order": 1,
        },
    )


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


def test_correspondence_readiness_rejects_empty_and_duplicate_drafts() -> None:
    empty_reactant = CalculationState("R", 0, 1, ())
    empty_product = CalculationState("P", 0, 1, ())
    empty = correspondence_readiness(empty_reactant, empty_product, ())
    one_atom_reactant = CalculationState(
        "R",
        0,
        1,
        (CalculationStateMember((0,), "included"),),
    )
    one_atom_product = CalculationState(
        "P",
        0,
        1,
        (CalculationStateMember((1,), "included"),),
    )
    duplicate = correspondence_readiness(
        one_atom_reactant,
        one_atom_product,
        (
            CalculationAtomCorrespondence(0, 1),
            CalculationAtomCorrespondence(0, 1),
        ),
    )

    assert empty.mapping_complete is False
    assert empty.ready_for_step_pack is False
    assert duplicate.mapping_complete is False
    assert duplicate.ready_for_step_pack is False
