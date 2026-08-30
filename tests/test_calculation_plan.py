from __future__ import annotations

from copy import deepcopy

import pytest

from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    CalculationAtomCorrespondence,
    CalculationPlan,
    CalculationState,
    CalculationStateMember,
    MoleculeModel,
    build_document_payload,
    calculation_plan_from_state,
    calculation_plan_to_state,
    extract_document_state,
    included_atom_ids,
    model_bond_pairs,
    serialize_model_state,
    serialize_settings,
)
from chemvas.features.calculation_bundle import (
    calculate_bond_changes,
    calculation_plan_report,
    calculation_step_by_id,
    correspondence_readiness,
    fill_correspondence_gaps,
    path_precheck,
    precomplex_basis_sha256,
    require_step_ready,
    select_calculation_state,
    validate_calculation_plan,
)
from chemvas.features.calculation_bundle import (
    included_atom_ids as feature_included_atom_ids,
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
        "shapes": [],
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
        "version": 2,
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
                    "precomplex": {"kind": "none"},
                },
                "product": {
                    "state_id": "P01",
                    "roles": [
                        {"component_atom_ids": [2, 3], "role": "product"},
                        {"component_atom_ids": [4], "role": "catalyst"},
                        {"component_atom_ids": [5], "role": "spectator"},
                    ],
                    "precomplex": {"kind": "none"},
                },
                "atom_correspondence": correspondence,
            }
        ],
    }


def test_feature_reexports_the_domain_included_atom_id_policy() -> None:
    state = CalculationState(
        "R01",
        0,
        1,
        (
            CalculationStateMember((7, 2), "included"),
            CalculationStateMember((9,), "context_only"),
        ),
    )

    assert feature_included_atom_ids is included_atom_ids
    assert included_atom_ids(state) == {2, 7}


def test_precomplex_basis_plain_bonds_ignore_order_and_orientation() -> None:
    state = _document_state()
    state["calculation_plan"] = _plan()
    plan = validate_calculation_plan(state, state["calculation_plan"])
    original = precomplex_basis_sha256(
        state,
        plan,
        step_id="S01",
        side="reactant",
        environment={"kind": "gas_phase"},
    )

    reordered = deepcopy(state)
    raw_model = reordered["model"]
    assert isinstance(raw_model, dict)
    raw_bonds = raw_model["bonds"]
    assert isinstance(raw_bonds, list)
    raw_bonds.reverse()
    for raw_bond in raw_bonds:
        assert isinstance(raw_bond, dict)
        raw_bond["a"], raw_bond["b"] = raw_bond["b"], raw_bond["a"]
    reordered_plan = validate_calculation_plan(reordered, reordered["calculation_plan"])

    assert (
        precomplex_basis_sha256(
            reordered,
            reordered_plan,
            step_id="S01",
            side="reactant",
            environment={"kind": "gas_phase"},
        )
        == original
    )


@pytest.mark.parametrize("style", ("wedge", "hash"))
def test_precomplex_basis_preserves_directional_bond_orientation(style: str) -> None:
    state = _document_state()
    raw_model = state["model"]
    assert isinstance(raw_model, dict)
    raw_bonds = raw_model["bonds"]
    assert isinstance(raw_bonds, list)
    directional_bond = raw_bonds[1]
    assert isinstance(directional_bond, dict)
    directional_bond["style"] = style
    state["calculation_plan"] = _plan()
    plan = validate_calculation_plan(state, state["calculation_plan"])
    original = precomplex_basis_sha256(
        state,
        plan,
        step_id="S01",
        side="product",
        environment={"kind": "gas_phase"},
    )

    reversed_state = deepcopy(state)
    reversed_model = reversed_state["model"]
    assert isinstance(reversed_model, dict)
    reversed_bonds = reversed_model["bonds"]
    assert isinstance(reversed_bonds, list)
    reversed_bond = reversed_bonds[1]
    assert isinstance(reversed_bond, dict)
    reversed_bond["a"], reversed_bond["b"] = reversed_bond["b"], reversed_bond["a"]
    reversed_plan = validate_calculation_plan(
        reversed_state, reversed_state["calculation_plan"]
    )

    assert (
        precomplex_basis_sha256(
            reversed_state,
            reversed_plan,
            step_id="S01",
            side="product",
            environment={"kind": "gas_phase"},
        )
        != original
    )


def test_correspondence_gap_fill_preserves_all_mapping_safety_policies() -> None:
    original = {0: None, 1: 11, 99: 10}
    atom_elements = {
        0: "C",
        1: "O",
        2: "N",
        3: "C",
        10: "C",
        11: "O",
        12: "C",
        13: "N",
        90: "C",
    }

    filled, applied = fill_correspondence_gaps(
        original,
        (
            (0, 10),  # an inactive stashed mapping must not reserve product 10
            (1, 12),  # never overwrite an existing mapping
            (2, 10),  # never reuse the product accepted for reactant 0
            (2, 12),  # never map different elements
            (2, 13),
            (3, 90),  # ignore candidates outside the active product endpoint
        ),
        active_reactant_ids={0, 1, 2, 3},
        active_product_ids={10, 11, 12, 13},
        replaceable_reactant_ids={0, 1, 2, 3},
        atom_elements=atom_elements,
    )

    assert original == {0: None, 1: 11, 99: 10}
    assert filled == {0: 10, 1: 11, 2: 13, 99: 10}
    assert applied == 2


def test_correspondence_gap_fill_only_changes_explicitly_replaceable_gaps() -> None:
    preserved, preserved_count = fill_correspondence_gaps(
        {0: None},
        ((0, 0),),
        active_reactant_ids={0},
        active_product_ids={0},
        replaceable_reactant_ids=set(),
    )
    replaced, replaced_count = fill_correspondence_gaps(
        {0: None},
        ((0, 0),),
        active_reactant_ids={0},
        active_product_ids={0},
        replaceable_reactant_ids={0},
    )

    assert preserved == {0: None}
    assert preserved_count == 0
    assert replaced == {0: 0}
    assert replaced_count == 1


def test_v7_document_round_trips_calculation_plan_v2_and_v6_rejects_it() -> None:
    state = _document_state()
    state["calculation_plan"] = _plan()

    payload = build_document_payload(state, CANVAS_FILE_VERSION)

    assert extract_document_state(payload)["calculation_plan"] == _plan()
    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        build_document_payload(state, CANVAS_FILE_VERSION - 1)


@pytest.mark.parametrize("version", [1, 2.0, True])
def test_non_current_calculation_plan_versions_are_rejected(version: object) -> None:
    state = _document_state()
    plan = _plan()
    plan["version"] = version

    with pytest.raises(ValueError, match="Invalid Chemvas calculation plan"):
        validate_calculation_plan(state, plan)


def test_calculation_plan_serializer_rejects_non_integer_v2() -> None:
    plan = CalculationPlan(states=(), steps=(), version=2.0)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid Chemvas calculation plan version"):
        calculation_plan_to_state(plan)


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
    assert report["steps"][0]["path_precheck"]["blocking_reasons"] == (  # type: ignore[index]
        "source_atom_mapping_incomplete",
        "multicomponent_precomplex_geometry_not_provided",
    )
    with pytest.raises(ValueError, match="complete one-to-one"):
        require_step_ready(plan, step)


def test_path_precheck_reports_multicomponent_geometry_gap() -> None:
    state = _document_state()
    plan = validate_calculation_plan(state, _plan())
    step = calculation_step_by_id(plan, "S01")

    readiness = path_precheck(plan, step, document_state=state)

    assert readiness.source_mapping_complete is True
    assert readiness.reactant_component_count == 2
    assert readiness.product_component_count == 2
    assert readiness.ready_for_path_endpoints is False
    assert readiness.blocking_reasons == (
        "multicomponent_precomplex_geometry_not_provided",
    )


def test_path_precheck_preserves_the_original_two_argument_call_shape() -> None:
    state = _document_state()
    plan = validate_calculation_plan(state, _plan())
    step = calculation_step_by_id(plan, "S01")

    readiness = path_precheck(plan, step)

    assert readiness.ready_for_path_endpoints is False
    assert readiness.blocking_reasons == (
        "multicomponent_precomplex_geometry_not_provided",
    )


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


def test_pph3_intrinsic_charge_is_used_across_calculation_state_selection() -> None:
    state = _document_state()
    model = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("PPh3", 1.0, 0.0),
            2: Atom("C", 4.0, 0.0),
            3: Atom("PPh3", 5.0, 0.0),
        },
        bonds=[Bond(0, 1), Bond(2, 3)],
    )
    state["model"] = serialize_model_state(model)
    plan_state = {
        "format": "chemvas-calculation-plan",
        "version": 2,
        "states": [
            {
                "id": "R01",
                "charge": 1,
                "multiplicity": 1,
                "members": [{"component_atom_ids": [0, 1], "inclusion": "included"}],
            },
            {
                "id": "P01",
                "charge": 1,
                "multiplicity": 1,
                "members": [{"component_atom_ids": [2, 3], "inclusion": "included"}],
            },
        ],
        "steps": [
            {
                "id": "S01",
                "reactant": {
                    "state_id": "R01",
                    "roles": [{"component_atom_ids": [0, 1], "role": "reactant"}],
                    "precomplex": {"kind": "none"},
                },
                "product": {
                    "state_id": "P01",
                    "roles": [{"component_atom_ids": [2, 3], "role": "product"}],
                    "precomplex": {"kind": "none"},
                },
                "atom_correspondence": [
                    {"reactant_atom_id": 0, "product_atom_id": 2},
                    {"reactant_atom_id": 1, "product_atom_id": 3},
                ],
            }
        ],
    }

    plan = validate_calculation_plan(state, plan_state)
    selection = select_calculation_state(state, plan.states[0])

    assert selection.formal_charge == 1


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
