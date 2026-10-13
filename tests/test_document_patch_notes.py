from __future__ import annotations

from copy import deepcopy

import pytest

from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state
from chemvas.features.document_patch import apply_document_patch, inspect_document_graph

SOURCE_HASH = "a" * 64


def _state(notes=None):
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 2,
            "atoms": [{"id": 0, "element": "O", "x": 0, "y": 0}],
            "bonds": [],
            "notes": notes or [{"x": 10, "y": 20, "text": "existing", "rotation": 15}],
        }
    )
    state["groups"] = [{"atoms": [0], "items": [["notes", 0]]}]
    return state


def _apply(state, *operations, source_hash=SOURCE_HASH):
    return apply_document_patch(
        state,
        {
            "format": "chemvas-graph-patch",
            "version": 1,
            "source_sha256": source_hash,
            "operations": list(operations),
        },
        source_sha256=SOURCE_HASH,
        document_version=CANVAS_FILE_VERSION,
    )


def test_note_inspection_uses_source_scoped_order_without_exposing_mutable_state():
    state = _state()
    report = inspect_document_graph(state)
    assert report["note_count"] == report["next_note_index"] == 1
    assert report["notes"] == [{"note_index": 0, **state["notes"][0]}]
    assert report["patch_contract"]["note_locator"] == "zero_based_document_note_index"
    assert report["patch_contract"]["note_indices_require_source_sha256"] is True
    report["notes"][0]["text"] = "not the document"
    assert state["notes"][0]["text"] == "existing"


def test_create_move_and_replace_styled_note_reuses_composition_and_keeps_groups():
    state = _state()
    original = deepcopy(state)
    content = {
        "runs": [
            {"text": "한글 H"},
            {"text": "2", "style": {"vertical_align": "sub"}},
            {"text": "O\n<caption>", "style": {"italic": True}},
        ],
        "style": {"font_size": 16, "font_weight": 700, "color": "#123456"},
    }
    result = _apply(
        state,
        {"op": "add_note", "note_index": 1, "note": {"x": 30, "y": 40, "text": "+"}},
        {"op": "move_note", "note_index": 0, "x": 12.5, "y": -3},
        {"op": "update_note", "note_index": 0, "content": content},
        {"op": "update_note", "note_index": 1, "content": {"text": "conditions"}},
    )
    candidate = result.payload["state"]
    expected = _state([{"x": 12.5, "y": -3, "rotation": 15, **content}])["notes"][0]
    assert candidate["notes"][0] == expected
    assert candidate["notes"][1] == {"x": 30, "y": 40, "text": "conditions"}
    assert candidate["groups"] == state["groups"]
    assert candidate["model"] == state["model"]
    assert result.before["notes"] == 1 and result.after["notes"] == 2
    assert [item["note_index"] for item in result.operations] == [1, 0, 0, 1]
    assert state == original


@pytest.mark.parametrize(
    "operation",
    [
        {
            "op": "add_note",
            "note_index": 0,
            "note": {"x": 0, "y": 0, "text": "wrong index"},
        },
        {"op": "add_note", "note_index": 3, "note": {"x": 0, "y": 0, "text": "gap"}},
        {"op": "move_note", "note_index": True, "x": 3, "y": 4},
        {"op": "move_note", "note_index": -1, "x": 3, "y": 4},
        {"op": "move_note", "note_index": 2, "x": 3, "y": 4},
        {"op": "move_note", "note_index": 0, "x": float("nan"), "y": 4},
        {"op": "move_note", "note_index": 0, "x": 3, "y": float("inf")},
        {"op": "move_note", "note_index": 0, "x": True, "y": 4},
        {"op": "move_note", "note_index": 0, "x": 10, "y": 20},
        {"op": "move_note", "note_index": 0, "x": 3, "y": 4, "rotation": 0},
        {"op": "update_note", "note_index": 0, "content": {"text": "existing"}},
        {
            "op": "update_note",
            "note_index": 0,
            "content": {"html": "<script>bad</script>"},
        },
        {
            "op": "update_note",
            "note_index": 0,
            "content": {"text": "both", "runs": [{"text": "both"}]},
        },
        {"op": "update_note", "note_index": 0, "content": {"text": "bad", "x": 0}},
        {
            "op": "update_note",
            "note_index": 0,
            "content": {"text": "bad", "style": {"font_size": 97}},
        },
        {
            "op": "update_note",
            "note_index": 0,
            "content": {"text": "bad", "style": {"font_size": 5}},
        },
        {
            "op": "update_note",
            "note_index": 0,
            "content": {"text": "bad", "style": {"font_weight": 450}},
        },
        {
            "op": "update_note",
            "note_index": 0,
            "content": {"text": "bad", "style": {"color": "red"}},
        },
        {
            "op": "update_note",
            "note_index": 0,
            "content": {"text": "bad", "style": {"italic": 1}},
        },
        {
            "op": "update_note",
            "note_index": 0,
            "content": {"text": "bad", "style": {"vertical_align": "top"}},
        },
        {
            "op": "add_note",
            "note_index": 1,
            "note": {"x": 0, "y": 0, "text": "bad", "rotation": float("inf")},
        },
    ],
)
def test_note_failures_are_transactional_even_after_successful_creation(operation):
    state = _state()
    original = deepcopy(state)
    # Invalid append IDs above are checked against a source with one note;
    # earlier success is a graph edit so it cannot change their expected indices.
    with pytest.raises(ValueError):
        _apply(state, {"op": "move_atom", "atom_id": 0, "x": 99, "y": 99}, operation)
    assert state == original


def test_stale_source_cannot_retarget_note_indices():
    state = _state()
    with pytest.raises(ValueError, match="exact input document bytes"):
        _apply(
            state,
            {"op": "move_note", "note_index": 0, "x": 1, "y": 2},
            source_hash="b" * 64,
        )


def test_move_preserves_arbitrary_stored_html_and_rotation_without_reinterpreting():
    state = _state()
    state["notes"][0]["html"] = (
        '<p><span style="font-family:custom">A</span><unsupported> B</unsupported></p>'
    )
    original = deepcopy(state)
    result = _apply(state, {"op": "move_note", "note_index": 0, "x": 1, "y": 2})
    assert result.payload["state"]["notes"][0] == {
        **original["notes"][0],
        "x": 1,
        "y": 2,
    }
    assert (
        inspect_document_graph(state)["notes"][0]["html"]
        == original["notes"][0]["html"]
    )
    assert state == original


@pytest.mark.parametrize(
    "content",
    [
        {"text": "\ud800"},
        {"runs": []},
        {"runs": [{"text": "x"}] * 257},
        {"runs": [{"text": "x", "href": "unknown"}]},
        {"text": "x", "style": {}},
        {"text": "x", "style": {"font_size": True}},
        {"text": "x", "style": {"font_size": 12.5}},
        {"style": {"color": "#123456"}},
    ],
)
def test_note_content_reuses_strict_composition_validation(content):
    state = _state()
    before = deepcopy(state)
    with pytest.raises(ValueError):
        _apply(
            state,
            {
                "op": "add_note",
                "note_index": 1,
                "note": {"text": "first", "x": 1, "y": 2},
            },
            {"op": "update_note", "note_index": 0, "content": content},
        )
    assert state == before


def test_plain_replacement_explicitly_clears_previous_rich_style():
    state = _state([{"text": "caption", "x": 0, "y": 0, "style": {"font_weight": 700}}])
    result = _apply(
        state, {"op": "update_note", "note_index": 0, "content": {"text": "caption"}}
    )
    assert "html" in state["notes"][0]
    assert result.payload["state"]["notes"][0] == {"text": "caption", "x": 0, "y": 0}
