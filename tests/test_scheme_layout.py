from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal
from typing import Any

import pytest

from chemvas.domain.document import CANVAS_FILE_VERSION, build_document_payload
from chemvas.features.document_composition import compose_document_state
from chemvas.features.scheme_layout import (
    merged_layout_groups,
    service,
    validate_layout_request,
    wrap_layout_row,
)

_HASH = "a" * 64


def _align_request() -> dict[str, Any]:
    request = _request()
    request["mode"] = "align-y"
    for block in request["rows"][0]["blocks"]:
        block.pop("anchor_atom", None)
    return request


def test_align_y_explicit_parts_and_references_preserve_native_groups() -> None:
    state, request = _state(), _align_request()
    request["rows"][0]["blocks"][0].update(atoms=[0, 1, 4, 5], parts=[[0, 1], [4, 5]])
    request["rows"][0]["reference_blocks"] = [1]
    state["groups"] = [{"atoms": [0, 1, 4, 5], "items": [["notes", 0]]}]
    original = deepcopy(state)
    result = _validate(state, request)
    assert result.mode == "align-y"
    assert result.rows[0].reference_blocks == (1,)
    assert result.rows[0].blocks[0].parts == ((0, 1), (4, 5))
    assert result.rows[0].blocks[1].parts == ()
    groups = merged_layout_groups(state, result)
    assert groups == state["groups"]
    groups[0]["items"].clear()
    assert state == original


@pytest.mark.parametrize(
    ("parts", "error"),
    [
        ([], "non-empty"),
        ([[]], "non-empty"),
        ([[0]], "every block atom"),
        ([[0, 1], [0]], "duplicate"),
        ([[0, 0, 1]], "duplicate"),
        ([[0, 99]], "belong"),
        ([[True, 1]], "integer indices"),
        ([[0], [1]], "must not cut bonds"),
    ],
)
def test_align_y_rejects_invalid_atom_partitions(parts, error) -> None:
    request = _align_request()
    request["rows"][0]["blocks"][0]["parts"] = parts
    with pytest.raises(ValueError, match=error):
        _validate(_state(), request)


def test_align_y_must_not_cut_dotted_contacts_or_assign_ambiguous_decorations() -> None:
    state, request = _state(), _align_request()
    state["model"]["bonds"][0]["style"] = "dotted"
    request["rows"][0]["blocks"][0]["parts"] = [[0], [1]]
    with pytest.raises(ValueError, match="must not cut bonds"):
        _validate(state, request)
    request = _align_request()
    request["rows"][0]["blocks"][1].update(atoms=[2, 3, 4, 5], parts=[[2, 3], [4, 5]])
    with pytest.raises(ValueError, match="cannot move brackets"):
        _validate(_state(), request)


@pytest.mark.parametrize("references", [[], [0, 0], [2], [-1], [True], [0.0], None])
def test_align_y_rejects_invalid_reference_blocks(references) -> None:
    request = _align_request()
    request["rows"][0]["reference_blocks"] = references
    with pytest.raises(ValueError):
        _validate(_state(), request)


@pytest.mark.parametrize(
    "field", ["gap", "row_gap", "caption_gap", "line_gap", "max_row_width"]
)
def test_align_y_rejects_inapplicable_reflow_options(field) -> None:
    request = _align_request()
    request[field] = 20
    with pytest.raises(ValueError, match="omit gaps"):
        _validate(_state(), request)


def test_align_y_rejects_atom_anchor_and_arrange_rejects_alignment_fields() -> None:
    request = _align_request()
    request["rows"][0]["blocks"][0]["anchor_atom"] = 0
    with pytest.raises(ValueError, match="omit anchor_atom"):
        _validate(_state(), request)
    request = _request()
    request["rows"][0]["blocks"][0]["parts"] = [[0, 1]]
    with pytest.raises(ValueError, match="parts requires"):
        _validate(_state(), request)
    request = _request()
    request["rows"][0]["reference_blocks"] = [0]
    with pytest.raises(ValueError, match="reference_blocks requires"):
        _validate(_state(), request)


@pytest.mark.parametrize("mode", [None, False, [], {}, "automatic", "align-x"])
def test_unknown_alignment_modes_fail_closed(mode) -> None:
    request = _request()
    request["mode"] = mode
    with pytest.raises(ValueError, match="layout mode"):
        _validate(_state(), request)


def _state() -> dict[str, Any]:
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": index, "element": "C", "x": index * 20, "y": 0}
                for index in range(6)
            ],
            "bonds": [{"a": first, "b": first + 1, "order": 1} for first in (0, 2, 4)],
            "notes": [
                {"text": f"Label {index}", "x": index * 20, "y": 40}
                for index in range(4)
            ],
            "arrows": [
                {"kind": "arrow", "start": [0, 20], "end": [40, 20]},
                {"kind": "equilibrium", "start": [60, 20], "end": [100, 20]},
            ],
            "ts_brackets": [
                {
                    "bracket_kind": "square_pair",
                    "left": 30,
                    "top": -20,
                    "right": 70,
                    "bottom": 20,
                }
            ],
        }
    )


def _request() -> dict[str, Any]:
    return {
        "format": "chemvas-scheme-layout",
        "version": 1,
        "source_sha256": _HASH,
        "rows": [
            {
                "blocks": [
                    {"atoms": [0, 1], "captions": [0], "anchor_atom": 0},
                    {
                        "atoms": [2, 3],
                        "captions": [1],
                        "items": [["ts_brackets", 0]],
                    },
                ],
                "arrows": [0],
            }
        ],
    }


def _validate(state: dict[str, Any], request: dict[str, Any]):
    return validate_layout_request(state, request, source_sha256=_HASH)


def test_request_is_immutable_and_validation_preserves_source() -> None:
    state, request = _state(), _request()
    before_state, before_request = deepcopy(state), deepcopy(request)
    result = _validate(state, request)

    assert (result.gap, result.row_gap, result.caption_gap, result.line_gap) == (
        40,
        30,
        10,
        4,
    )
    assert result.source_sha256 == _HASH
    assert result.rows[0].blocks[0].anchor_atom == 0
    assert result.rows[0].blocks[1].items == (("ts_brackets", 0),)
    assert result.rows[0].arrows == (0,)
    with pytest.raises(FrozenInstanceError):
        result.gap = 5  # type: ignore[misc]
    request["rows"][0]["blocks"][0]["atoms"].append(5)
    assert result.rows[0].blocks[0].atoms == (0, 1)
    assert state == before_state
    assert before_request["rows"][0]["blocks"][0]["atoms"] == [0, 1]


def test_groups_replace_wholly_contained_and_preserve_untouched() -> None:
    state = _state()
    state["groups"] = [
        {"atoms": [4, 5], "items": [["notes", 2]]},
        {"atoms": [0, 1], "items": [["notes", 0]]},
        {"atoms": [], "items": [["arrows", 0]]},
    ]
    original = deepcopy(state)
    result = _validate(state, _request())
    groups = merged_layout_groups(state, result)

    assert groups == [
        {"atoms": [4, 5], "items": [["notes", 2]]},
        {"atoms": [], "items": [["arrows", 0]]},
        {"atoms": [0, 1], "items": [["notes", 0]]},
        {"atoms": [2, 3], "items": [["ts_brackets", 0], ["notes", 1]]},
    ]
    build_document_payload({**state, "groups": groups}, CANVAS_FILE_VERSION)
    groups[0]["atoms"].append(0)
    assert state == original


@pytest.mark.parametrize(
    "group",
    [
        {"atoms": [0, 1], "items": [["notes", 2]]},
        {"atoms": [0, 1, 2, 3], "items": []},
        {"atoms": [], "items": [["notes", 0], ["notes", 1]]},
    ],
)
def test_existing_group_cannot_be_partly_moved_or_split(group) -> None:
    state = _state()
    state["groups"] = [group]
    with pytest.raises(ValueError, match="split an existing group"):
        _validate(state, _request())


def test_row_arrow_cannot_escape_mixed_group() -> None:
    state = _state()
    state["groups"] = [{"atoms": [], "items": [["arrows", 0], ["notes", 2]]}]
    with pytest.raises(ValueError, match="row arrow belongs to a mixed group"):
        _validate(state, _request())


def test_explicit_block_can_include_several_complete_components() -> None:
    request = _request()
    request["rows"][0]["blocks"][0]["atoms"] = [0, 1, 4, 5]
    assert _validate(_state(), request).rows[0].blocks[0].atoms == (0, 1, 4, 5)


@pytest.mark.parametrize("atoms", [[0], [0, 1, 4]])
def test_blocks_cannot_cut_connected_structure(atoms) -> None:
    request = _request()
    request["rows"][0]["blocks"][0]["atoms"] = atoms
    with pytest.raises(ValueError, match="whole connected structures"):
        _validate(_state(), request)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("atoms", [0, 0, 1], "duplicate atom"),
        ("atoms", [0, 1, 2, 3], "duplicate atom"),
        ("atoms", [0, 1, 99], "unknown atom"),
        ("atoms", [True, 1], "integer indices"),
        ("atoms", [], "non-empty"),
        ("captions", [0, 0], "duplicate scene item"),
        ("captions", [1], "duplicate scene item"),
        ("captions", [99], "unknown scene item"),
        ("items", [["notes", 0]], "duplicate scene item"),
        ("items", [["arrows", 0]], "item kind"),
        ("items", [["ts_brackets", 99]], "unknown scene item"),
        ("items", [["notes", True]], "non-negative integer"),
        ("items", [["notes"]], "references"),
        ("anchor_atom", 2, "anchor_atom"),
        ("anchor_atom", True, "anchor_atom"),
        ("anchor_atom", None, "anchor_atom"),
        ("inferred_role", "reactant", "unknown keys"),
    ],
)
def test_invalid_block_fields_fail_closed(field, value, error) -> None:
    request = _request()
    request["rows"][0]["blocks"][0][field] = value
    with pytest.raises(ValueError, match=error):
        _validate(_state(), request)


@pytest.mark.parametrize("field", ["gap", "row_gap", "caption_gap", "line_gap"])
@pytest.mark.parametrize(
    "value", [True, None, "2", -1, 10001, float("nan"), float("inf"), 10**400]
)
def test_invalid_gap_values_are_rejected(field, value) -> None:
    request = _request()
    request[field] = value
    with pytest.raises(ValueError, match=f"{field} must be finite"):
        _validate(_state(), request)


def test_gap_lower_bounds_and_upper_boundary() -> None:
    request = _request()
    request.update(gap=10000, row_gap=0, caption_gap=0, line_gap=0)
    assert _validate(_state(), request).row_gap == 0
    request["gap"] = 0
    with pytest.raises(ValueError, match="greater than 0"):
        _validate(_state(), request)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("version", True, "version must be 1"),
        ("version", 2, "version must be 1"),
        ("format", "other", "layout format"),
        ("source_sha256", "A" * 64, "lowercase hexadecimal"),
        ("source_sha256", "b" * 64, "exact input document bytes"),
        ("rows", [], "non-empty"),
        ("rows", {}, "JSON array"),
        ("invented", True, "unknown keys"),
    ],
)
def test_invalid_root_request_rejected(field, value, error) -> None:
    request = _request()
    request[field] = value
    with pytest.raises(ValueError, match=error):
        _validate(_state(), request)


@pytest.mark.parametrize("field", ["calculation_plan", "perspective"])
def test_unsupported_scientific_state_is_not_silently_removed(field) -> None:
    state = _state()
    state[field] = {"preserved": "source data"}
    original = deepcopy(state)
    with pytest.raises(ValueError, match="adjust this document manually.*No"):
        _validate(state, _request())
    assert state == original


@pytest.mark.parametrize("arrows", [[], [0, 1], [99]])
def test_invalid_row_arrow_references(arrows) -> None:
    request = _request()
    request["rows"][0]["arrows"] = arrows
    with pytest.raises(ValueError, match="minus one|unknown scene item"):
        _validate(_state(), request)


def test_row_arrows_are_optional_and_labeled_equilibrium_is_supported() -> None:
    state, request = _state(), _request()
    state["arrows"][1]["labels"] = {"above": "THF", "below": "298 K"}
    request["rows"][0]["arrows"] = [1]
    assert _validate(state, request).rows[0].arrows == (1,)
    del request["rows"][0]["arrows"]
    assert _validate(state, request).rows[0].arrows == ()


@pytest.mark.parametrize(
    "arrow",
    [
        {"kind": "arrow", "start": [0, 0], "end": [0, 0]},
        {"kind": "arrow", "start": [40, 0], "end": [0, 0]},
        {"kind": "arrow", "start": [0, 0], "end": [40, 1]},
        {
            "kind": "curved_single",
            "start": [0, 0],
            "end": [40, 0],
            "control": [20, 20],
            "double": False,
        },
    ],
)
def test_unsupported_arrow_orientation_is_actionable(arrow) -> None:
    state = _state()
    state["arrows"][0] = arrow
    with pytest.raises(ValueError, match="left-to-right horizontal"):
        _validate(state, _request())


def test_duplicate_arrow_across_rows_is_rejected() -> None:
    request = _request()
    request["rows"][0]["blocks"] = [{"atoms": [0, 1]}, {"atoms": [2, 3]}]
    request["rows"].append(
        {"blocks": [{"atoms": [4, 5]}, {"atoms": [0, 1]}], "arrows": [0]}
    )
    # Make four disjoint structures so the duplicate arrow is the first defect.
    state = _state()
    state["model"]["atoms"]["6"] = {
        "element": "C",
        "x": 120,
        "y": 0,
        "color": "#000000",
        "explicit_label": False,
    }
    state["model"]["next_atom_id"] = 7
    request["rows"][1]["blocks"][1]["atoms"] = [6]
    with pytest.raises(ValueError, match="duplicate scene item reference arrows"):
        _validate(state, request)


def test_resource_limits_include_totals_across_rows(monkeypatch) -> None:
    state, request = _state(), _request()
    monkeypatch.setattr(service, "MAX_LAYOUT_BLOCKS", 1)
    request["rows"] = [
        {"blocks": [{"atoms": [0, 1]}]},
        {"blocks": [{"atoms": [2, 3]}]},
    ]
    with pytest.raises(ValueError, match="at most 1 blocks"):
        _validate(state, request)
    monkeypatch.setattr(service, "MAX_LAYOUT_BLOCKS", 128)
    monkeypatch.setattr(service, "MAX_LAYOUT_ROWS", 1)
    with pytest.raises(ValueError, match="rows may contain at most 1"):
        _validate(state, request)
    monkeypatch.setattr(service, "MAX_LAYOUT_ROWS", 128)
    monkeypatch.setattr(service, "MAX_LAYOUT_REFERENCES", 3)
    with pytest.raises(ValueError, match="at most 3 atoms"):
        _validate(state, request)


def test_scene_reference_total_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(service, "MAX_LAYOUT_REFERENCES", 4)
    request = _request()
    request["rows"][0]["blocks"][0]["items"] = [["notes", 2]]
    with pytest.raises(ValueError, match="at most 4 scene items"):
        _validate(_state(), request)


@pytest.mark.parametrize(
    "value", [None, True, "200", 0, -1, 100001, float("nan"), float("inf"), 10**400]
)
def test_max_row_width_requires_positive_bounded_canvas_distance(value) -> None:
    request = _request()
    request["max_row_width"] = value
    with pytest.raises(ValueError, match="max_row_width must be finite"):
        _validate(_state(), request)


def test_max_row_width_is_optional_without_changing_defaults() -> None:
    request = _request()
    assert _validate(_state(), request).max_row_width is None
    request["max_row_width"] = 100000
    assert _validate(_state(), request).max_row_width == 100000


@pytest.mark.parametrize(
    "field", ["gap", "row_gap", "caption_gap", "line_gap", "max_row_width"]
)
def test_decimal_json_distances_use_canonical_numeric_contract(field) -> None:
    request = _request()
    request[field] = Decimal("229.39")
    assert getattr(_validate(_state(), request), field) == pytest.approx(229.39)


@pytest.mark.parametrize(
    "value",
    [
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal(-1),
        Decimal("1E100000000"),
    ],
)
def test_invalid_decimal_distances_fail_closed(value) -> None:
    request = _request()
    request["max_row_width"] = value
    with pytest.raises(ValueError, match="max_row_width must be finite"):
        _validate(_state(), request)


def test_decimal_numbers_do_not_relax_identity_fields() -> None:
    request = _request()
    request["version"] = Decimal(1)
    with pytest.raises(ValueError, match="version must be 1"):
        _validate(_state(), request)
    request["version"] = 1
    request["rows"][0]["blocks"][0]["atoms"] = [Decimal(0), 1]
    with pytest.raises(ValueError, match="integer indices"):
        _validate(_state(), request)


def test_wrap_exact_fit_and_just_below_keep_incoming_arrow_with_target() -> None:
    assert wrap_layout_row([40, 50], [20], gap=5, max_row_width=120) == ((0, 2),)
    assert wrap_layout_row([40, 50], [20], gap=5, max_row_width=119.999) == (
        (0, 1),
        (1, 2),
    )
    # The second line needs only arrow + gap + target, not another leading gap.
    assert wrap_layout_row([40, 50], [20], gap=5, max_row_width=75) == ((0, 1), (1, 2))


def test_wrap_repeated_continuations_preserve_every_source_index() -> None:
    slices = wrap_layout_row(
        [40, 50, 60, 40, 35], [20, 15, 25, 20], gap=5, max_row_width=130
    )
    assert slices == ((0, 2), (2, 3), (3, 4), (4, 5))
    assert [index for start, stop in slices for index in range(start, stop)] == list(
        range(5)
    )
    arrows = [
        index for start, stop in slices for index in range(max(0, start - 1), stop - 1)
    ]
    assert arrows == list(range(4))
    assert all(start < stop for start, stop in slices)


def test_wrap_gallery_without_arrows_and_single_block() -> None:
    assert wrap_layout_row([40, 50, 60], [], gap=5, max_row_width=95) == (
        (0, 2),
        (2, 3),
    )
    assert wrap_layout_row([40], [], gap=5, max_row_width=40) == ((0, 1),)


@pytest.mark.parametrize(
    ("blocks", "arrows", "width", "error"),
    [
        ([120, 50], [20], 100, "block 0 requires width"),
        ([40, 80], [20], 100, "incoming arrow 0 and block 1 require width"),
        ([40, 101], [], 100, "block 1 require width"),
        ([], [], 100, "1 to 128"),
        ([40, 50, 60], [20], 100, "blocks minus one"),
        ([40, float("nan")], [], 100, "finite and positive"),
        ([40, 50], [0], 100, "finite and positive"),
    ],
)
def test_wrap_rejects_indivisible_or_invalid_units(
    blocks, arrows, width, error
) -> None:
    with pytest.raises(ValueError, match=error):
        wrap_layout_row(blocks, arrows, gap=5, max_row_width=width)
