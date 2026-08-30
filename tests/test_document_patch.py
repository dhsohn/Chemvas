from __future__ import annotations

from copy import deepcopy

import pytest

from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    build_document_payload,
    serialize_model_state,
    serialize_settings,
)
from chemvas.features.calculation_bundle import service as calculation_bundle_service
from chemvas.features.document_patch import (
    MAX_PATCH_OPERATIONS,
    apply_document_patch,
    inspect_document_graph,
)

SOURCE_HASH = "a" * 64


def _state(model: MoleculeModel | None = None) -> dict[str, object]:
    return {
        "model": serialize_model_state(model or MoleculeModel()),
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


def _patch(*operations: dict[str, object]) -> dict[str, object]:
    return {
        "format": "chemvas-graph-patch",
        "version": 1,
        "source_sha256": SOURCE_HASH,
        "operations": list(operations),
    }


def test_inspection_is_sorted_and_exposes_agent_patch_contract() -> None:
    model = MoleculeModel(
        atoms={7: Atom("O", 2.0, 0.0), 2: Atom("C", 1.0, 0.0)},
        bonds=[Bond(7, 2, order=2, style="double")],
        atom_annotations={7: {"formal_charge": -1}},
    )
    state = _state(model)
    state["marks"] = [
        {
            "kind": "minus",
            "text": "-",
            "atom_id": 7,
            "dx": None,
            "dy": None,
            "x": 3.0,
            "y": -1.0,
        }
    ]

    report = inspect_document_graph(state)

    assert [atom["id"] for atom in report["atoms"]] == [2, 7]
    assert report["atoms"][1]["annotation"] == {"formal_charge": -1}
    assert report["atoms"][1]["attached_mark_kinds"] == ["minus"]
    assert report["bonds"] == [
        {"a": 7, "b": 2, "order": 2, "style": "double", "color": "#000000"}
    ]
    assert report["patch_contract"]["supported_operations"] == [
        "add_atom",
        "update_atom",
        "move_atom",
        "add_bond",
        "update_bond",
        "remove_bond",
    ]


def test_inspection_deserializes_once_for_many_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(
        MoleculeModel(
            atoms={atom_id: Atom("C", float(atom_id), 0.0) for atom_id in range(64)}
        )
    )
    original = calculation_bundle_service.deserialize_model_state
    calls = 0

    def counted_deserialize(model_state: dict[str, object]) -> MoleculeModel:
        nonlocal calls
        calls += 1
        return original(model_state)

    monkeypatch.setattr(
        calculation_bundle_service,
        "deserialize_model_state",
        counted_deserialize,
    )

    report = inspect_document_graph(state)

    assert report["atom_count"] == 64
    assert len(report["components"]) == 64
    assert calls == 1


def test_patch_applies_ordered_graph_operations_without_mutating_source() -> None:
    state = _state(MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)}))
    original = deepcopy(state)

    result = apply_document_patch(
        state,
        _patch(
            {
                "op": "add_atom",
                "atom_id": 1,
                "element": "O",
                "x": 18.0,
                "y": 0.0,
                "color": "#123456",
                "explicit_label": True,
            },
            {
                "op": "add_bond",
                "a": 0,
                "b": 1,
                "order": 1,
                "style": "single",
                "color": "#000000",
            },
            {"op": "update_atom", "atom_id": 0, "changes": {"element": "N"}},
            {"op": "move_atom", "atom_id": 1, "x": 20.0, "y": 3.0},
            {
                "op": "update_bond",
                "a": 1,
                "b": 0,
                "changes": {"order": 2, "style": "double"},
            },
        ),
        source_sha256=SOURCE_HASH,
        document_version=CANVAS_FILE_VERSION,
    )

    assert state == original
    assert result.before == {"atoms": 1, "bonds": 0, "components": 1}
    assert result.after == {"atoms": 2, "bonds": 1, "components": 1}
    assert result.state["model"]["atoms"][0]["element"] == "N"
    assert result.state["model"]["atoms"][1]["x"] == 20.0
    assert result.state["model"]["bonds"][0] == {
        "a": 0,
        "b": 1,
        "order": 2,
        "style": "double",
        "color": "#000000",
    }
    build_document_payload(result.state, CANVAS_FILE_VERSION)


def test_update_bond_uses_unordered_locator_but_preserves_stereo_orientation() -> None:
    state = _state(
        MoleculeModel(
            atoms={0: Atom("C", 0, 0), 1: Atom("C", 1, 0)},
            bonds=[Bond(1, 0, order=1, style="wedge")],
        )
    )

    result = apply_document_patch(
        state,
        _patch(
            {
                "op": "update_bond",
                "a": 0,
                "b": 1,
                "changes": {"style": "hash"},
            }
        ),
        source_sha256=SOURCE_HASH,
        document_version=CANVAS_FILE_VERSION,
    )

    assert result.state["model"]["bonds"][0]["a"] == 1
    assert result.state["model"]["bonds"][0]["b"] == 0
    assert result.state["model"]["bonds"][0]["style"] == "hash"


def test_move_atom_cascades_ring_mark_and_perspective_coordinates() -> None:
    model = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("C", 10.0, 0.0),
            2: Atom("C", 5.0, 8.0),
        },
        bonds=[Bond(0, 1), Bond(1, 2), Bond(2, 0)],
    )
    state = _state(model)
    state["ring_fills"] = [
        {
            "points": [[0.0, 0.0], [10.0, 0.0], [5.0, 8.0]],
            "atom_ids": [0, 1, 2],
            "color": "#ffffff",
            "alpha": 0.2,
        }
    ]
    state["marks"] = [
        {
            "kind": "plus",
            "text": "+",
            "atom_id": 0,
            "dx": 1.0,
            "dy": -1.0,
            "x": 1.0,
            "y": -1.0,
        }
    ]
    state["perspective"] = {
        "atom_coords_3d": {"0": [0.0, 0.0, 4.0]},
        "projection_center_3d": None,
        "projection_anchor_2d": None,
    }

    result = apply_document_patch(
        state,
        _patch({"op": "move_atom", "atom_id": 0, "x": 2.0, "y": 3.0}),
        source_sha256=SOURCE_HASH,
        document_version=CANVAS_FILE_VERSION,
    )

    assert result.state["ring_fills"][0]["points"][0] == [2.0, 3.0]
    assert (result.state["marks"][0]["x"], result.state["marks"][0]["y"]) == (
        3.0,
        2.0,
    )
    assert result.state["perspective"]["atom_coords_3d"]["0"] == [2.0, 3.0, 4.0]
    build_document_payload(result.state, CANVAS_FILE_VERSION)


def test_remove_ring_bond_fails_closed_without_changing_source() -> None:
    model = MoleculeModel(
        atoms={0: Atom("C", 0, 0), 1: Atom("C", 1, 0), 2: Atom("C", 0, 1)},
        bonds=[Bond(0, 1), Bond(1, 2), Bond(2, 0)],
    )
    state = _state(model)
    state["ring_fills"] = [
        {
            "points": [[0, 0], [1, 0], [0, 1]],
            "atom_ids": [0, 1, 2],
            "color": None,
            "alpha": 0.2,
        }
    ]
    original = deepcopy(state)

    with pytest.raises(ValueError, match="document or Calculation Plan invariant"):
        apply_document_patch(
            state,
            _patch({"op": "remove_bond", "a": 0, "b": 1}),
            source_sha256=SOURCE_HASH,
            document_version=CANVAS_FILE_VERSION,
        )
    assert state == original


def test_semantic_calculation_plan_drift_rejects_entire_patch() -> None:
    state = _state(MoleculeModel(atoms={0: Atom("C", 0, 0), 1: Atom("C", 5, 0)}))
    state["calculation_plan"] = {
        "format": "chemvas-calculation-plan",
        "version": 2,
        "states": [
            {
                "id": "R",
                "charge": 0,
                "multiplicity": 1,
                "members": [{"component_atom_ids": [0], "inclusion": "included"}],
            },
            {
                "id": "P",
                "charge": 0,
                "multiplicity": 1,
                "members": [{"component_atom_ids": [1], "inclusion": "included"}],
            },
        ],
        "steps": [
            {
                "id": "S",
                "reactant": {
                    "state_id": "R",
                    "roles": [{"component_atom_ids": [0], "role": "reactant"}],
                    "precomplex": {"kind": "none"},
                },
                "product": {
                    "state_id": "P",
                    "roles": [{"component_atom_ids": [1], "role": "product"}],
                    "precomplex": {"kind": "none"},
                },
                "atom_correspondence": [{"reactant_atom_id": 0, "product_atom_id": 1}],
            }
        ],
    }

    with pytest.raises(ValueError, match="Calculation Plan invariant"):
        apply_document_patch(
            state,
            _patch({"op": "update_atom", "atom_id": 0, "changes": {"element": "N"}}),
            source_sha256=SOURCE_HASH,
            document_version=CANVAS_FILE_VERSION,
        )

    moved = apply_document_patch(
        state,
        _patch({"op": "move_atom", "atom_id": 0, "x": 1.0, "y": 2.0}),
        source_sha256=SOURCE_HASH,
        document_version=CANVAS_FILE_VERSION,
    )
    assert moved.state["calculation_plan"] == state["calculation_plan"]
    assert moved.calculation_plan_present is True

    with pytest.raises(ValueError, match="Calculation Plan invariant"):
        apply_document_patch(
            state,
            _patch(
                {
                    "op": "add_bond",
                    "a": 0,
                    "b": 1,
                    "order": 1,
                    "style": "single",
                    "color": "#000000",
                }
            ),
            source_sha256=SOURCE_HASH,
            document_version=CANVAS_FILE_VERSION,
        )


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        (
            {"format": "chemvas-graph-patch", "version": 1, "operations": []},
            "exactly",
        ),
        (_patch(), "non-empty"),
        (
            _patch({"op": "move_atom", "atom_id": True, "x": 1, "y": 2}),
            "nonnegative integer",
        ),
        (
            _patch({"op": "move_atom", "atom_id": 0, "x": 0, "y": 0}),
            "must change",
        ),
        (
            _patch({"op": "unknown"}),
            "unsupported",
        ),
    ],
)
def test_patch_schema_and_operations_fail_closed(
    patch: dict[str, object], message: str
) -> None:
    state = _state(MoleculeModel(atoms={0: Atom("C", 0, 0)}))
    with pytest.raises(ValueError, match=message):
        apply_document_patch(
            state,
            patch,
            source_sha256=SOURCE_HASH,
            document_version=CANVAS_FILE_VERSION,
        )


def test_patch_rejects_stale_hash_wrong_next_id_and_operation_budget() -> None:
    state = _state()
    stale = _patch(
        {
            "op": "add_atom",
            "atom_id": 0,
            "element": "C",
            "x": 0,
            "y": 0,
            "color": "#000",
            "explicit_label": False,
        }
    )
    stale["source_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="exact input"):
        apply_document_patch(
            state,
            stale,
            source_sha256=SOURCE_HASH,
            document_version=CANVAS_FILE_VERSION,
        )

    too_many = _patch(
        *(
            {"op": "remove_bond", "a": 0, "b": 1}
            for _ in range(MAX_PATCH_OPERATIONS + 1)
        )
    )
    with pytest.raises(ValueError, match="at most"):
        apply_document_patch(
            state,
            too_many,
            source_sha256=SOURCE_HASH,
            document_version=CANVAS_FILE_VERSION,
        )
