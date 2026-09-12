from copy import deepcopy

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QTimer
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_service_ports import mark_scene_service_for_access
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.mark_item_access import apply_mark_color_for, mark_center_for
from chemvas.ui.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.selection_outline_state import selection_outlines_for
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.structure_mutation_access import add_atom_for
from chemvas.ui.transactions.document import DocumentSavepoint
from tests.canvas_factory import build_canvas_view

KINDS = ("plus", "minus", "circled_plus", "circled_minus", "radical")


@pytest.fixture
def drawing():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = build_canvas_view()
    old = add_atom_for(canvas, "N", -40.3, -10.7)
    new = add_atom_for(canvas, "O", 50.9, 20.1)
    canvas.services.input.tool_mode_controller.set_tool("select")
    yield canvas, old, new
    canvas.services.document.canvas_scene_reset_service.clear_scene()
    canvas.close()
    app.processEvents()


def owner_outlines(canvas):
    return [
        item
        for item in selection_outlines_for(canvas)
        if (item.data(2) or {}).get("kind") == "mark_owner"
    ]


def test_selected_distant_mark_shows_actual_owner_without_document_mutation(drawing):
    canvas, old, _new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    canvas.services.interaction.move_controller.move_item(item, 90, 30)
    before = snapshot_canvas_state_for(canvas)
    item.setSelected(True)
    refresh_selection_outline_for(canvas)
    outlines = owner_outlines(canvas)
    assert len(outlines) == 1
    assert outlines[0].data(2)["atom_id"] == old
    assert "far" in outlines[0].toolTip().lower()
    assert snapshot_canvas_state_for(canvas) == before
    item.setSelected(False)
    refresh_selection_outline_for(canvas)
    assert not owner_outlines(canvas)


@pytest.mark.parametrize("kind", KINDS)
def test_explicit_rebind_preserves_glyph_and_both_electronic_states_exactly(
    drawing, kind
):
    canvas, old, new = drawing
    # Existing marks on both owners must survive the transfer and replay.
    add_mark_for_atom_for(canvas, old, QPointF(-47, -17), kind="radical")
    add_mark_for_atom_for(canvas, new, QPointF(57, 14), kind="minus")
    item = add_mark_for_atom_for(canvas, old, QPointF(-33, -17), kind=kind)
    apply_mark_color_for(canvas, item, "#aBc")
    canvas.services.interaction.move_controller.move_item(item, 91.2, 30.8)
    history = canvas.services.history_service
    history.clear()
    before = snapshot_canvas_state_for(canvas)
    before_registry = {
        key: tuple(value) for key, value in mark_registry_for(canvas).items()
    }
    before_annotations = deepcopy(canvas.model.atom_annotations)
    position = item.pos()
    center = mark_center_for(canvas, item)
    assert mark_scene_service_for_access(canvas).rebind_mark(item, new)
    after = snapshot_canvas_state_for(canvas)
    assert item.pos() == position
    assert mark_center_for(canvas, item) == center
    assert item.data(1)["atom_id"] == new
    assert item.data(1)["kind"] == kind
    assert item.data(1)["color"] == "#aBc"
    assert item not in mark_registry_for(canvas).get_for_atom(old)
    assert item in mark_registry_for(canvas).get_for_atom(new)
    assert canvas.model.atom_annotations != before_annotations
    assert len(history.state.history) == 1
    for _ in range(3):
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        assert item.pos() == position
        assert {
            key: tuple(value) for key, value in mark_registry_for(canvas).items()
        } == before_registry
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
        assert item.pos() == position


@pytest.mark.parametrize("failure", ["apply", "refresh", "push", "disabled"])
def test_rebind_failure_restores_scene_registry_annotations_and_stacks(
    drawing, monkeypatch, failure
):
    import chemvas.ui.history_commands as commands

    canvas, old, new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    item.setSelected(True)
    history = canvas.services.history_service
    before = snapshot_canvas_state_for(canvas)
    position = item.pos()
    stacks = (tuple(history.state.history), tuple(history.state.redo_stack))
    registry = {key: tuple(value) for key, value in mark_registry_for(canvas).items()}
    if failure == "disabled":
        history.state.enabled = False
    elif failure == "push":
        monkeypatch.setattr(history, "push", lambda command: False)
    else:
        name = (
            "_apply_scene_item_state"
            if failure == "apply"
            else "refresh_selection_outline_for_canvas"
        )
        original = getattr(commands, name)
        calls = 0

        def fail_once(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected mark rebind failure")
            return original(*args)

        monkeypatch.setattr(commands, name, fail_once)
    with pytest.raises(RuntimeError):
        mark_scene_service_for_access(canvas).rebind_mark(item, new)
    assert snapshot_canvas_state_for(canvas) == before
    assert item.pos() == position
    assert (tuple(history.state.history), tuple(history.state.redo_stack)) == stacks
    assert {
        key: tuple(value) for key, value in mark_registry_for(canvas).items()
    } == registry


def test_rebind_same_owner_invalid_target_and_conflicting_annotation_are_no_edits(
    drawing,
):
    canvas, old, new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    service = mark_scene_service_for_access(canvas)
    before = snapshot_canvas_state_for(canvas)
    count = len(canvas.services.history_service.state.history)
    assert not service.rebind_mark(item, old)
    for target in (-1, True, "1"):
        with pytest.raises(ValueError, match="existing atom"):
            service.rebind_mark(item, target)
    assert snapshot_canvas_state_for(canvas) == before
    canvas.model.atom_annotations[old]["formal_charge"] = 2
    with pytest.raises(ValueError, match="disagree"):
        service.rebind_mark(item, new)
    assert canvas.model.atom_annotations[old]["formal_charge"] == 2
    assert item.data(1)["atom_id"] == old
    assert len(canvas.services.history_service.state.history) == count


@pytest.mark.parametrize("operation", ["undo", "redo"])
def test_failed_rebind_history_replay_remains_exact_and_retryable(
    drawing, monkeypatch, operation
):
    import chemvas.ui.history_commands as commands

    canvas, old, new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="radical")
    history = canvas.services.history_service
    history.clear()
    service = mark_scene_service_for_access(canvas)
    service.rebind_mark(item, new)
    if operation == "redo":
        history.undo()
    before = snapshot_canvas_state_for(canvas)
    stacks = (tuple(history.state.history), tuple(history.state.redo_stack))
    original = commands.refresh_selection_outline_for_canvas
    calls = 0

    def fail_once(canvas):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected rebind replay failure")
        original(canvas)

    monkeypatch.setattr(commands, "refresh_selection_outline_for_canvas", fail_once)
    with pytest.raises(RuntimeError):
        getattr(history, operation)()
    assert snapshot_canvas_state_for(canvas) == before
    assert (tuple(history.state.history), tuple(history.state.redo_stack)) == stacks
    getattr(history, operation)()
    assert item.data(1)["atom_id"] == (old if operation == "undo" else new)


@pytest.mark.parametrize("move_owner", [False, True])
def test_owner_guide_tracks_actual_owner_and_mark_and_savepoint_restores_it(
    drawing, move_owner
):
    canvas, old, _new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    item.setSelected(True)
    if move_owner:
        atom_items_for(canvas)[old].setSelected(True)
    refresh_selection_outline_for(canvas)
    outline = owner_outlines(canvas)[0]
    path, pen, tooltip = outline.path(), outline.pen(), outline.toolTip()
    before = snapshot_canvas_state_for(canvas)
    snapshot = DocumentSavepoint.capture(
        canvas, history_service=canvas.services.history_service
    )
    move = canvas.services.interaction.move_controller
    if move_owner:
        move.move_atom(old, 90, 30)
    else:
        move.move_item(item, 90, 30, update_selection=False)
    canvas.services.selection.selection_controller.shift_selection_outlines(90, 30)
    owner = canvas.model.atoms[old]
    center = mark_center_for(canvas, item)
    actual = outline.path()
    line_start = actual.elementAt(actual.elementCount() - 2)
    line_end = actual.elementAt(actual.elementCount() - 1)
    assert (line_start.x, line_start.y) == (owner.x, owner.y)
    assert (line_end.x, line_end.y) == (center.x(), center.y())
    assert (outline.pen().color().name() == "#b45309") is not move_owner
    assert outline.toolTip() == tooltip
    assert snapshot.restore().authoritative
    assert snapshot_canvas_state_for(canvas) == before
    assert outline.path() == path and outline.pen() == pen
    assert outline.toolTip() == tooltip


def test_switching_tool_removes_owner_guide_and_returning_select_restores_it(drawing):
    canvas, old, _new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    item.setSelected(True)
    assert owner_outlines(canvas)
    before = snapshot_canvas_state_for(canvas)
    canvas.services.input.tool_mode_controller.set_tool("bond")
    assert not owner_outlines(canvas)
    canvas.services.input.tool_mode_controller.set_tool("select")
    assert len(owner_outlines(canvas)) == 1
    assert snapshot_canvas_state_for(canvas) == before


def test_explicit_rebind_refusal_shows_specific_reason(drawing, monkeypatch):
    from chemvas.ui import mark_reassignment_dialog
    from chemvas.ui.canvas_window_access import set_error_callback_for

    canvas, old, new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    canvas.model.atom_annotations[old]["formal_charge"] = 2
    messages = []
    set_error_callback_for(canvas, messages.append)
    monkeypatch.setattr(
        mark_reassignment_dialog.MarkReassignmentDialog,
        "choose_atom",
        lambda self: (True, new),
    )
    assert not mark_reassignment_dialog.reassign_mark_with_dialog(canvas, item)
    assert len(messages) == 1 and "disagree" in messages[0]
    assert item.data(1)["atom_id"] == old


def test_destroying_modal_parent_cancels_without_reading_deleted_widgets():
    from chemvas.ui.mark_reassignment_dialog import reassign_mark_with_dialog

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = build_canvas_view()
    atom_id = add_atom_for(canvas, "N", 0, 0)
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(4, -4), kind="plus")
    QTimer.singleShot(0, lambda: sip.delete(canvas))
    try:
        assert not reassign_mark_with_dialog(canvas, item)
        assert sip.isdeleted(canvas)
    finally:
        if not sip.isdeleted(canvas):
            canvas.services.document.canvas_scene_reset_service.clear_scene()
            canvas.close()
        app.processEvents()
