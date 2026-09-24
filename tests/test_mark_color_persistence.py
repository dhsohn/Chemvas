import json
from copy import deepcopy
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QGraphicsTextItem

from chemvas.core.document_io import create_document, read_document, write_document
from chemvas.core.svg_roundtrip import extract_chemvas_document_from_svg
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    CLIPBOARD_SELECTION_VERSION,
    selection_payload_to_canvas_state,
    validate_clipboard_selection_payload,
)
from chemvas.ui.annotations.state import mark_state_dict_for
from chemvas.ui.canvas.canvas_scene_items_state import (
    mark_items_for,
    require_scene_record_id,
)
from chemvas.ui.history.history_commands import UpdateSceneItemCommand
from chemvas.ui.scene.scene_decoration_access import add_mark_for, add_mark_for_atom_for
from chemvas.ui.selection.select_all_access import select_all_scene_items_for
from tests.calculation_plan_support import _document_state
from tests.canvas_factory import build_canvas_view

KINDS = ("plus", "minus", "radical", "circled_plus", "circled_minus")


def _mark(kind="plus", *, bound=False):
    return dict(
        kind=kind,
        text=None,
        atom_id=0 if bound else None,
        dx=4.0 if bound else None,
        dy=-4.0 if bound else None,
        x=4.0,
        y=-4.0,
    )


def _clipboard(mark):
    return dict(
        format="chemvas-selection",
        version=CLIPBOARD_SELECTION_VERSION,
        atoms=[],
        bonds=[],
        rings=[],
        marks=[dict(mark, kind="mark", mark_kind=mark["kind"])],
        scene_items=[],
    )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("color", ["#f08", "#Ff0088", "#000000"])
def test_native_clipboard_and_selection_state_accept_explicit_mark_color(kind, color):
    mark = dict(_mark(kind), color=color)
    state = _document_state()
    state["marks"] = [mark]
    before = deepcopy(state)
    assert create_document(state, CANVAS_FILE_VERSION).state["marks"] == [mark]
    clip = _clipboard(mark)
    assert validate_clipboard_selection_payload(clip)
    assert selection_payload_to_canvas_state(clip, state["settings"])["marks"] == [mark]
    assert state == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("color", None),
        ("color", ""),
        ("color", "red"),
        ("color", "#ff000080"),
        ("color", "#gg0000"),
        ("color", 3),
        ("colour", "#ff0000"),
        ("color", ["#ff0000"]),
        ("color", {"value": "#ff0000"}),
    ],
)
def test_invalid_mark_colors_and_unknown_keys_are_rejected(key, value):
    mark = dict(_mark(), **{key: value})
    state = _document_state()
    state["marks"] = [mark]
    with pytest.raises(ValueError):
        create_document(state, CANVAS_FILE_VERSION)
    assert not validate_clipboard_selection_payload(_clipboard(mark))


@pytest.fixture
def drawing():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = build_canvas_view()
    atom_id = canvas.services.canvas_atom_mutation_service.add_atom("N", 10.0, 20.0)
    yield canvas, atom_id
    canvas.services.canvas_scene_reset_service.clear_scene()
    canvas.close()
    app.processEvents()


def _paint_color(item, kind):
    if isinstance(item, QGraphicsTextItem):
        return item.defaultTextColor().name()
    return (item.brush() if kind == "radical" else item.pen()).color().name()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("bound", [False, True])
def test_explicit_color_roundtrip_and_absent_color_undo_are_independent_of_atom(
    drawing, tmp_path, kind, bound
):
    canvas, atom_id = drawing
    item = (
        add_mark_for_atom_for(canvas, atom_id, QPointF(18, 12), kind=kind)
        if bound
        else add_mark_for(canvas, QPointF(70, 80), kind=kind)
    )
    before = mark_state_dict_for(canvas, item)
    before_document = canvas.services.canvas_document_session_service.snapshot_state()
    assert "color" not in before
    after = dict(before, color="#a20F99")
    canvas.services.scene_item_controller.apply_scene_item_state(item, after)
    assert _paint_color(item, kind) == "#a20f99"
    assert mark_state_dict_for(canvas, item)["color"] == "#a20F99"
    assert (
        canvas.services.canvas_document_session_service.snapshot_state()["model"]
        == before_document["model"]
    )
    history = canvas.services.history_service
    history.push(UpdateSceneItemCommand(require_scene_record_id(item), before, after))
    colored = canvas.services.canvas_document_session_service.snapshot_state()
    history.undo()
    assert (
        canvas.services.canvas_document_session_service.snapshot_state()
        == before_document
    )
    assert _paint_color(item, kind) == QColor(canvas.renderer.style.atom_color).name()
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == colored
    assert _paint_color(item, kind) == "#a20f99"
    path = tmp_path / "colored.chemvas"
    write_document(path, colored, CANVAS_FILE_VERSION)
    restored = read_document(path).state
    canvas.services.canvas_document_session_service.restore_state(restored)
    assert canvas.services.canvas_document_session_service.snapshot_state() == colored
    assert _paint_color(mark_items_for(canvas)[0], kind) == "#a20f99"


@pytest.mark.parametrize("kind", KINDS)
def test_uncolored_document_bytes_stay_unchanged(drawing, tmp_path, kind):
    canvas, _ = drawing
    add_mark_for(canvas, QPointF(30, 40), kind=kind)
    state = canvas.services.canvas_document_session_service.snapshot_state()
    before = create_document(state, CANVAS_FILE_VERSION).payload
    before_path = tmp_path / "before.chemvas"
    write_document(before_path, state, CANVAS_FILE_VERSION)
    canvas.services.canvas_document_session_service.restore_state(state)
    assert (
        create_document(
            canvas.services.canvas_document_session_service.snapshot_state(),
            CANVAS_FILE_VERSION,
        ).payload
        == before
    )
    after_path = tmp_path / "after.chemvas"
    write_document(
        after_path,
        canvas.services.canvas_document_session_service.snapshot_state(),
        CANVAS_FILE_VERSION,
    )
    assert before_path.read_bytes() == after_path.read_bytes()
    assert "color" not in state["marks"][0]


@pytest.mark.parametrize("kind", KINDS)
def test_color_survives_bond_length_history_and_failed_publication(drawing, kind):
    canvas, atom_id = drawing
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(18, 12), kind=kind)
    canvas.services.scene_item_controller.apply_scene_item_state(
        item, dict(mark_state_dict_for(canvas, item), color="#1582ba")
    )
    before = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service
    canvas.services.geometry_controller.set_bond_length(60.0)
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert after["marks"][0]["color"] == "#1582ba"
    assert _paint_color(item, kind) == "#1582ba"
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert _paint_color(item, kind) == "#1582ba"
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    stacks = history.capture_stack_snapshot()
    with patch.object(history, "push", return_value=False), pytest.raises(RuntimeError):
        canvas.services.geometry_controller.set_bond_length(35.0)
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    assert history.capture_stack_snapshot() == stacks
    assert _paint_color(item, kind) == "#1582ba"


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("bound", [False, True])
def test_colored_copy_paste_and_selection_svg_preserve_color(
    drawing, tmp_path, kind, bound
):
    canvas, atom_id = drawing
    item = (
        add_mark_for_atom_for(canvas, atom_id, QPointF(18, 12), kind=kind)
        if bound
        else add_mark_for(canvas, QPointF(70, 80), kind=kind)
    )
    canvas.services.scene_item_controller.apply_scene_item_state(
        item, dict(mark_state_dict_for(canvas, item), color="#1582ba")
    )
    select_all_scene_items_for(canvas)
    clip = canvas.services.scene_clipboard_controller
    payload = clip.selection_payload_for_clipboard()
    assert payload["marks"][0]["color"] == "#1582ba"
    before = canvas.services.canvas_document_session_service.snapshot_state()
    stacks = canvas.services.history_service.capture_stack_snapshot()
    output = tmp_path / "selected.svg"
    canvas.services.canvas_document_session_service.export_figure(
        str(output), fmt="svg", scope="selection", editable_svg=True
    )
    assert (
        extract_chemvas_document_from_svg(output).state["marks"][0]["color"]
        == "#1582ba"
    )
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert canvas.services.history_service.capture_stack_snapshot() == stacks
    assert clip.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, json.dumps(payload))
    )
    pasted = canvas.services.canvas_document_session_service.snapshot_state()
    assert [state["color"] for state in pasted["marks"]] == ["#1582ba", "#1582ba"]
    assert all(_paint_color(mark, kind) == "#1582ba" for mark in mark_items_for(canvas))
    canvas.services.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    canvas.services.history_service.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == pasted
    assert all(_paint_color(mark, kind) == "#1582ba" for mark in mark_items_for(canvas))


@pytest.mark.parametrize("operation", ["move", "flip-h", "flip-v", "rotate"])
@pytest.mark.parametrize("kind", KINDS)
def test_colored_bound_and_free_marks_survive_geometry_undo(drawing, kind, operation):
    canvas, atom_id = drawing
    bound = add_mark_for_atom_for(canvas, atom_id, QPointF(18, 12), kind=kind)
    free = add_mark_for(canvas, QPointF(70, 80), kind=kind)
    for item, color in [(bound, "#aa0077"), (free, "#337799")]:
        canvas.services.scene_item_controller.apply_scene_item_state(
            item, dict(mark_state_dict_for(canvas, item), color=color)
        )
    select_all_scene_items_for(canvas)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    transform = canvas.services.scene_transform_controller
    if operation == "move":
        transform.translate_selected_items(10.25, -5.5)
    elif operation.startswith("flip"):
        transform.flip_selected_items(operation == "flip-h")
    else:
        transform.rotate_selected_items(37.0)
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert after != before
    assert [mark["color"] for mark in after["marks"]] == ["#aa0077", "#337799"]
    assert [_paint_color(item, kind) for item in (bound, free)] == [
        "#aa0077",
        "#337799",
    ]
    history = canvas.services.history_service
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert [_paint_color(item, kind) for item in (bound, free)] == [
        "#aa0077",
        "#337799",
    ]
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    assert [_paint_color(item, kind) for item in (bound, free)] == [
        "#aa0077",
        "#337799",
    ]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("phase", ["undo", "redo"])
def test_color_history_failure_restores_ink_and_metadata(drawing, kind, phase):
    canvas, atom_id = drawing
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(18, 12), kind=kind)
    before = mark_state_dict_for(canvas, item)
    after = dict(before, color="#f08")
    canvas.services.scene_item_controller.apply_scene_item_state(item, after)
    history = canvas.services.history_service
    history.push(UpdateSceneItemCommand(require_scene_record_id(item), before, after))
    if phase == "redo":
        history.undo()
    original = canvas.services.canvas_document_session_service.snapshot_state()
    original_ink = _paint_color(item, kind)
    builder = canvas.services.scene_decoration_build_service
    real_setter = builder.apply_mark_color
    calls = 0

    def fail_once(mark, color):
        nonlocal calls
        calls += 1
        real_setter(mark, color)
        if calls == 1:
            raise RuntimeError("Synthetic paint failure")

    with patch.object(builder, "apply_mark_color", side_effect=fail_once):
        with pytest.raises(RuntimeError, match="Synthetic paint failure"):
            getattr(history, phase)()
    assert canvas.services.canvas_document_session_service.snapshot_state() == original
    assert _paint_color(item, kind) == original_ink


@pytest.mark.parametrize("bad", ["", "red", "#abcd", "#aabbccdd", 12, [], {}])
def test_invalid_color_primitive_does_not_change_mark_or_document(drawing, bad):
    canvas, atom_id = drawing
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(18, 12), kind="plus")
    before = canvas.services.canvas_document_session_service.snapshot_state()
    with pytest.raises(ValueError, match="hex color"):
        canvas.services.scene_decoration_build_service.apply_mark_color(item, bad)
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
