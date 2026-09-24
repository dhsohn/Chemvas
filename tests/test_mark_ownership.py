from copy import deepcopy

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QTimer
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.scene.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.transactions.document import DocumentSavepoint
from tests.canvas_factory import build_canvas_view

KINDS = ("plus", "minus", "circled_plus", "circled_minus", "radical")


@pytest.fixture
def drawing():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = build_canvas_view()
    old = canvas.services.canvas_atom_mutation_service.add_atom("N", -40.3, -10.7)
    new = canvas.services.canvas_atom_mutation_service.add_atom("O", 50.9, 20.1)
    canvas.services.tool_mode_controller.set_tool("select")
    yield canvas, old, new
    canvas.services.canvas_scene_reset_service.clear_scene()
    canvas.close()
    app.processEvents()


def owner_outlines(canvas):
    return [
        item
        for item in canvas.runtime_state.selection_state.outlines
        if (item.data(2) or {}).get("kind") == "mark_owner"
    ]


def test_selected_distant_mark_shows_actual_owner_without_document_mutation(drawing):
    canvas, old, _new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    canvas.services.move_controller.move_item(item, 90, 30)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    item.setSelected(True)
    canvas.services.selection.update_selection_outline()
    outlines = owner_outlines(canvas)
    assert len(outlines) == 1
    assert outlines[0].data(2)["atom_id"] == old
    assert "far" in outlines[0].toolTip().lower()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    item.setSelected(False)
    canvas.services.selection.update_selection_outline()
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
    canvas.services.scene_decoration_build_service.apply_mark_color(item, "#aBc")
    canvas.services.move_controller.move_item(item, 91.2, 30.8)
    history = canvas.services.history_service
    history.clear()
    before = canvas.services.canvas_document_session_service.snapshot_state()
    before_registry = {
        key: tuple(value) for key, value in mark_registry_for(canvas).items()
    }
    before_annotations = deepcopy(canvas.model.atom_annotations)
    position = item.pos()
    center = canvas.services.scene_decoration_build_service.mark_center(item)
    assert canvas.services.canvas_mark_scene_service.rebind_mark(item, new)
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert item.pos() == position
    assert canvas.services.scene_decoration_build_service.mark_center(item) == center
    assert item.data(1)["atom_id"] == new
    assert item.data(1)["kind"] == kind
    assert item.data(1)["color"] == "#aBc"
    assert item not in mark_registry_for(canvas).get_for_atom(old)
    assert item in mark_registry_for(canvas).get_for_atom(new)
    assert canvas.model.atom_annotations != before_annotations
    assert len(history.state.history) == 1
    for _ in range(3):
        history.undo()
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() == before
        )
        assert item.pos() == position
        assert {
            key: tuple(value) for key, value in mark_registry_for(canvas).items()
        } == before_registry
        history.redo()
        assert canvas.services.canvas_document_session_service.snapshot_state() == after
        assert item.pos() == position


@pytest.mark.parametrize("failure", ["apply", "refresh", "push", "disabled"])
def test_rebind_failure_restores_scene_registry_annotations_and_stacks(
    drawing, monkeypatch, failure
):
    canvas, old, new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    item.setSelected(True)
    history = canvas.services.history_service
    before = canvas.services.canvas_document_session_service.snapshot_state()
    position = item.pos()
    stacks = (tuple(history.state.history), tuple(history.state.redo_stack))
    registry = {key: tuple(value) for key, value in mark_registry_for(canvas).items()}
    if failure == "disabled":
        history.state.enabled = False
    elif failure == "push":
        monkeypatch.setattr(history, "push", lambda command: False)
    else:
        target, name = (
            (canvas.services.scene_item_controller, "apply_scene_item_state")
            if failure == "apply"
            else (canvas.services.selection, "update_selection_outline")
        )
        original = getattr(target, name)
        calls = 0

        def fail_once(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected mark rebind failure")
            return original(*args)

        monkeypatch.setattr(target, name, fail_once)
    with pytest.raises(RuntimeError):
        canvas.services.canvas_mark_scene_service.rebind_mark(item, new)
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
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
    service = canvas.services.canvas_mark_scene_service
    before = canvas.services.canvas_document_session_service.snapshot_state()
    count = len(canvas.services.history_service.state.history)
    assert not service.rebind_mark(item, old)
    for target in (-1, True, "1"):
        with pytest.raises(ValueError, match="existing atom"):
            service.rebind_mark(item, target)
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
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
    canvas, old, new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="radical")
    history = canvas.services.history_service
    history.clear()
    service = canvas.services.canvas_mark_scene_service
    service.rebind_mark(item, new)
    if operation == "redo":
        history.undo()
    before = canvas.services.canvas_document_session_service.snapshot_state()
    stacks = (tuple(history.state.history), tuple(history.state.redo_stack))
    selection = canvas.services.selection
    original = selection.update_selection_outline
    calls = 0

    def fail_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected rebind replay failure")
        original()

    monkeypatch.setattr(selection, "update_selection_outline", fail_once)
    with pytest.raises(RuntimeError):
        getattr(history, operation)()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
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
        canvas.runtime_state.atom_graphics_state.atom_items[old].setSelected(True)
    canvas.services.selection.update_selection_outline()
    outline = owner_outlines(canvas)[0]
    path, pen, tooltip = outline.path(), outline.pen(), outline.toolTip()
    before = canvas.services.canvas_document_session_service.snapshot_state()
    snapshot = DocumentSavepoint.capture(
        canvas, history_service=canvas.services.history_service
    )
    move = canvas.services.move_controller
    if move_owner:
        move.move_atom(old, 90, 30)
    else:
        move.move_item(item, 90, 30, update_selection=False)
    canvas.services.selection.shift_selection_outlines(90, 30)
    owner = canvas.model.atoms[old]
    center = canvas.services.scene_decoration_build_service.mark_center(item)
    actual = outline.path()
    line_start = actual.elementAt(actual.elementCount() - 2)
    line_end = actual.elementAt(actual.elementCount() - 1)
    assert (line_start.x, line_start.y) == (owner.x, owner.y)
    assert (line_end.x, line_end.y) == (center.x(), center.y())
    assert (outline.pen().color().name() == "#b45309") is not move_owner
    assert outline.toolTip() == tooltip
    assert snapshot.restore().authoritative
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert outline.path() == path and outline.pen() == pen
    assert outline.toolTip() == tooltip


def test_switching_tool_removes_owner_guide_and_returning_select_restores_it(drawing):
    canvas, old, _new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    item.setSelected(True)
    assert owner_outlines(canvas)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    canvas.services.tool_mode_controller.set_tool("bond")
    assert not owner_outlines(canvas)
    canvas.services.tool_mode_controller.set_tool("select")
    assert len(owner_outlines(canvas)) == 1
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


def test_explicit_rebind_refusal_shows_specific_reason(drawing, monkeypatch):
    from chemvas.ui.dialogs import mark_reassignment_dialog

    canvas, old, new = drawing
    item = add_mark_for_atom_for(canvas, old, QPointF(-35, -15), kind="plus")
    canvas.model.atom_annotations[old]["formal_charge"] = 2
    messages = []
    canvas.runtime_state.callback_state.error = messages.append
    monkeypatch.setattr(
        mark_reassignment_dialog.MarkReassignmentDialog,
        "choose_atom",
        lambda self: (True, new),
    )
    assert not mark_reassignment_dialog.reassign_mark_with_dialog(canvas, item)
    assert len(messages) == 1 and "disagree" in messages[0]
    assert item.data(1)["atom_id"] == old


def test_destroying_modal_parent_cancels_without_reading_deleted_widgets():
    from chemvas.ui.dialogs.mark_reassignment_dialog import reassign_mark_with_dialog

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = build_canvas_view()
    atom_id = canvas.services.canvas_atom_mutation_service.add_atom("N", 0, 0)
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(4, -4), kind="plus")
    QTimer.singleShot(0, lambda: sip.delete(canvas))
    try:
        assert not reassign_mark_with_dialog(canvas, item)
        assert sip.isdeleted(canvas)
    finally:
        if not sip.isdeleted(canvas):
            canvas.services.canvas_scene_reset_service.clear_scene()
            canvas.close()
        app.processEvents()
