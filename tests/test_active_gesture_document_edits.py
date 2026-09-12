"""Document actions cancel an unfinished pointer edit before changing history."""

import sys
from unittest import mock

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QKeySequence
from PyQt6.QtTest import QTest

from chemvas.features.selection import ROTATION_HANDLE_TYPE
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.handle_overlay_access import show_endpoint_handles_for
from chemvas.ui.handle_state import active_handles_for
from chemvas.ui.history_commands import AddSceneItemsCommand
from chemvas.ui.main_window_ports import (
    cut_selection_for_window,
    group_selection_for_window,
    paste_selection_for_window,
    redo_action_for_window,
    undo_action_for_window,
)
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.transactions.document import DocumentSavepoint
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


@pytest.fixture
def qt_errors(monkeypatch):
    errors = []
    # Qt otherwise aborts when a Python release handler raises. Keep the real
    # event route and report that failure as a normal regression assertion.
    monkeypatch.setattr(
        sys, "excepthook", lambda _type, error, _tb: errors.append(error)
    )
    return errors


def populate(canvas, kind):
    if kind == "note":
        item = canvas.services.tool_controller.context.create_text_note(
            QPointF(-30.3, -20.7), "editable note"
        )
        canvas.services.history_service.push(
            AddSceneItemsCommand([scene_item_state_for(canvas, item)], [item])
        )
        return item.sceneBoundingRect().center(), item
    if kind in {"arrow", "handle", "move"}:
        item = add_arrow_for(canvas, QPointF(-65.2, -13.7), QPointF(25.3, 8.9), "arrow")
        return QPointF(-20, -2.4), item
    add_bond_between_points_for(canvas, QPointF(-45.3, -20.7), QPointF(25.2, 15.8))
    atoms = list(canvas.model.atoms.values())
    return QPointF((atoms[0].x + atoms[1].x) / 2, (atoms[0].y + atoms[1].y) / 2), None


def start_drag(canvas, kind, point, item=None):
    name = (
        kind
        if kind in {"perspective", "bond", "delete", "move", "line", "shape"}
        else "select"
    )
    canvas.services.input.tool_mode_controller.set_tool(name)
    if kind != "move":
        select_all_scene_items_for(canvas)
    else:
        canvas.scene().clearSelection()
    if kind == "handle":
        show_endpoint_handles_for(canvas, item)
        point = active_handles_for(canvas)[0].sceneBoundingRect().center()
    elif kind == "rotation":
        knob = next(
            item
            for item in canvas.scene().items()
            if item.data(1) == ROTATION_HANDLE_TYPE
        )
        point = knob.sceneBoundingRect().center()
    elif kind == "perspective":
        atom = next(iter(canvas.model.atoms.values()))
        point = QPointF(atom.x, atom.y)
    elif kind == "bond":
        atom = next(iter(canvas.model.atoms.values()))
        point = QPointF(atom.x, atom.y)
    elif kind in {"line", "shape"}:
        point = QPointF(90, 70)
    canvas.setFocus()
    start = canvas.mapFromScene(point)
    end = start + QPoint(60, 37)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), start + QPoint(25, 14), delay=20)
    QTest.mouseMove(canvas.viewport(), end, delay=20)
    return end


def invoke(window, canvas, operation, route):
    if route == "window":
        if operation == "undo":
            action = undo_action_for_window(window)
            assert action.isEnabled()
            action.trigger()
        elif operation == "redo":
            action = redo_action_for_window(window)
            assert action.isEnabled()
            action.trigger()
        else:
            cut_selection_for_window(window)
        return
    key = {
        "undo": Qt.Key.Key_Z,
        "redo": Qt.Key.Key_Y,
        "cut": Qt.Key.Key_X,
        "delete": Qt.Key.Key_Delete,
    }[operation]
    modifiers = (
        Qt.KeyboardModifier.NoModifier
        if operation == "delete"
        else Qt.KeyboardModifier.ControlModifier
    )
    if operation == "redo":
        combination = QKeySequence(QKeySequence.StandardKey.Redo)[0]
        key = combination.key()
        modifiers = combination.keyboardModifiers()
    # The canvas has a standalone key route in addition to window QActions.
    canvas.services.input.input_controller.key_press_event(
        QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
    )


def release(canvas, end):
    QTest.mouseMove(canvas.viewport(), end + QPoint(10, 5), delay=20)
    QTest.mouseRelease(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=end + QPoint(10, 5)
    )


@pytest.mark.parametrize("route", ["window", "canvas"])
@pytest.mark.parametrize(
    "kind",
    [
        "note",
        "arrow",
        "molecule",
        "handle",
        "rotation",
        "perspective",
        "bond",
        "delete",
        "move",
        "line",
        "shape",
    ],
)
def test_undo_during_gesture_preserves_redo_after_late_release(
    drawing, qt_errors, kind, route
):
    window, canvas = drawing
    empty = snapshot_canvas_state_for(canvas)
    point, item = populate(canvas, kind)
    original = snapshot_canvas_state_for(canvas)
    assert original != empty
    end = start_drag(canvas, kind, point, item)
    invoke(window, canvas, "undo", route)
    after_action = snapshot_canvas_state_for(canvas)
    stacks = canvas.services.history_service.capture_stack_snapshot()
    release(canvas, end)
    assert not qt_errors
    assert snapshot_canvas_state_for(canvas) == after_action == empty
    canvas.services.history_service.verify_stack_snapshot(stacks)
    invoke(window, canvas, "redo", route)
    assert snapshot_canvas_state_for(canvas) == original


@pytest.mark.parametrize(
    "operation,route", [("delete", "canvas"), ("cut", "canvas"), ("cut", "window")]
)
def test_delete_or_cut_cancels_move_before_mutating_selection(
    drawing, qt_errors, operation, route
):
    window, canvas = drawing
    empty = snapshot_canvas_state_for(canvas)
    point, item = populate(canvas, "arrow")
    original = snapshot_canvas_state_for(canvas)
    end = start_drag(canvas, "arrow", point, item)
    invoke(window, canvas, operation, route)
    after_action = snapshot_canvas_state_for(canvas)
    stacks = canvas.services.history_service.capture_stack_snapshot()
    release(canvas, end)
    assert not qt_errors
    assert snapshot_canvas_state_for(canvas) == after_action == empty
    canvas.services.history_service.verify_stack_snapshot(stacks)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == original


@pytest.mark.parametrize("route", ["window", "canvas"])
@pytest.mark.parametrize("operation", ["undo", "redo"])
def test_history_action_during_move_of_still_existing_atoms_is_exact(
    drawing, qt_errors, operation, route
):
    window, canvas = drawing
    point, _ = populate(canvas, "molecule")
    select_all_scene_items_for(canvas)
    original = snapshot_canvas_state_for(canvas)
    canvas.services.scene_operations.scene_transform_controller.translate_selected_items(
        8.1, -4.3
    )
    edited = snapshot_canvas_state_for(canvas)
    if operation == "redo":
        canvas.services.history_service.undo()
        expected = edited
    else:
        point += QPointF(8.1, -4.3)
        expected = original
    end = start_drag(canvas, "molecule", point)
    invoke(window, canvas, operation, route)
    stacks = canvas.services.history_service.capture_stack_snapshot()
    release(canvas, end)
    assert not qt_errors
    assert snapshot_canvas_state_for(canvas) == expected
    canvas.services.history_service.verify_stack_snapshot(stacks)
    history = canvas.services.history_service
    while history.can_undo():
        history.undo()
    while history.can_redo():
        history.redo()
    assert snapshot_canvas_state_for(canvas) == edited


@pytest.mark.parametrize("route", ["window", "canvas"])
def test_cancel_failure_does_not_run_requested_history_operation(drawing, route):
    window, canvas = drawing
    point, item = populate(canvas, "arrow")
    end = start_drag(canvas, "arrow", point, item)
    tool = canvas.services.tool_controller.active
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    cancel = tool.deactivate
    error = RuntimeError("gesture cancellation failed")
    with (
        mock.patch.object(tool, "deactivate", side_effect=error),
        mock.patch.object(history, "undo") as undo,
    ):
        with pytest.raises(RuntimeError, match="gesture cancellation failed"):
            if route == "window":
                from chemvas.ui.main_window_ports import undo_for_window

                undo_for_window(window)
            else:
                invoke(window, canvas, "undo", route)
        undo.assert_not_called()
    history.verify_stack_snapshot(stacks)
    cancel()
    release(canvas, end)


@pytest.mark.parametrize("route", ["window", "canvas"])
@pytest.mark.parametrize("retry", ["document-edit", "new-press"])
def test_failed_eraser_cancel_cannot_publish_on_late_release(
    drawing, qt_errors, route, retry
):
    window, canvas = drawing
    point, item = populate(canvas, "molecule")
    history = canvas.services.history_service
    add_arrow_for(canvas, QPointF(130, 90), QPointF(175, 90), "arrow")
    history.undo()
    original = snapshot_canvas_state_for(canvas)
    stacks = history.capture_stack_snapshot()
    assert stacks.redo_stack
    end = start_drag(canvas, "delete", point, item)
    tool = canvas.services.tool_controller.active
    session = tool._delete_session
    assert session is not None and session.active and tool._changed
    pending = snapshot_canvas_state_for(canvas)
    assert pending != original
    commands = tuple(tool._commands)
    restore = DocumentSavepoint.restore

    def fail_this_restore(savepoint, *args, **kwargs):
        if savepoint is session.snapshot:
            raise RuntimeError("delete snapshot restore failed")
        return restore(savepoint, *args, **kwargs)

    with (
        mock.patch.object(DocumentSavepoint, "restore", fail_this_restore),
        mock.patch.object(history, "undo", wraps=history.undo) as undo,
    ):
        with pytest.raises(RuntimeError, match="delete snapshot restore failed"):
            if route == "window":
                from chemvas.ui.main_window_ports import undo_for_window

                undo_for_window(window)
            else:
                invoke(window, canvas, "undo", route)
        undo.assert_not_called()
    assert not tool._erasing
    assert tool._delete_session is session and session.active
    history.verify_stack_snapshot(stacks)
    release(canvas, end)
    assert not qt_errors
    assert snapshot_canvas_state_for(canvas) == pending
    history.verify_stack_snapshot(stacks)
    assert tool._delete_session is session and session.active
    assert tuple(tool._commands) == commands

    # The failed cancellation still has its original recovery owner. A new
    # explicit cancellation or the next press can retry after the fault clears.
    if retry == "document-edit":
        canvas.services.tool_controller.prepare_for_document_edit()
    else:
        empty = canvas.mapFromScene(QPointF(120, 160))
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=empty)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=empty)
    assert not session.active
    assert not tool.has_active_gesture
    assert snapshot_canvas_state_for(canvas) == original
    history.verify_stack_snapshot(stacks)
    release(canvas, end)
    assert snapshot_canvas_state_for(canvas) == original
    history.verify_stack_snapshot(stacks)


def test_idle_history_action_does_not_reset_select_handles(drawing):
    window, canvas = drawing
    _point, item = populate(canvas, "arrow")
    tool = canvas.services.tool_controller.active
    show_endpoint_handles_for(canvas, item)
    with mock.patch.object(tool, "deactivate", wraps=tool.deactivate) as deactivate:
        invoke(window, canvas, "undo", "window")
        deactivate.assert_not_called()


@pytest.mark.parametrize(
    "operation,route",
    [
        ("paste", "window"),
        ("paste", "canvas"),
        ("group", "window"),
        ("group", "canvas"),
        ("nudge", "canvas"),
        ("rotate", "canvas"),
        ("flip", "canvas"),
    ],
)
def test_other_keyboard_document_edits_do_not_keep_stale_gesture(
    drawing, qt_errors, operation, route
):
    window, canvas = drawing
    point, item = populate(canvas, "arrow")
    populate(canvas, "molecule")
    select_all_scene_items_for(canvas)
    original = snapshot_canvas_state_for(canvas)
    if operation == "paste":
        assert canvas.services.scene_operations.scene_clipboard_controller.copy_selection_to_clipboard()
    end = start_drag(canvas, "arrow", point, item)
    if route == "window" and operation in {"paste", "group"}:
        {"paste": paste_selection_for_window, "group": group_selection_for_window}[
            operation
        ](window)
    else:
        key, modifiers = {
            "paste": (Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier),
            "group": (Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier),
            "nudge": (Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier),
            "rotate": (Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier),
            "flip": (
                Qt.Key.Key_H,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            ),
        }[operation]
        event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
        canvas.services.input.input_controller.key_press_event(event)
    expected = snapshot_canvas_state_for(canvas)
    assert expected != original
    stacks = canvas.services.history_service.capture_stack_snapshot()
    release(canvas, end)
    assert not qt_errors
    assert snapshot_canvas_state_for(canvas) == expected
    canvas.services.history_service.verify_stack_snapshot(stacks)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == original
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == expected


def test_shift_modifier_does_not_cancel_active_rotation(drawing, qt_errors):
    _window, canvas = drawing
    point, item = populate(canvas, "molecule")
    before = snapshot_canvas_state_for(canvas)
    end = start_drag(canvas, "rotation", point, item)
    tool = canvas.services.tool_controller.active
    session = tool._rotation_session
    assert session is not None
    QTest.keyPress(canvas, Qt.Key.Key_Shift)
    assert tool._rotation_session is session
    QTest.keyRelease(canvas, Qt.Key.Key_Shift)
    release(canvas, end)
    assert not qt_errors
    assert snapshot_canvas_state_for(canvas) != before
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
