"""Document actions cancel an unfinished pointer edit before changing history."""

from unittest import mock

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QKeySequence, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMenu

from chemvas.ui.transactions.document import DocumentSavepoint
from chemvas.ui.window.main_window_ports import (
    cut_selection_for_window,
    group_selection_for_window,
    paste_selection_for_window,
)
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing
from tests.gui_workflow_support import populate, release, start_drag
from tests.gui_workflow_support import qt_errors as qt_errors


def test_double_bond_menu_cancels_drag_before_style_edit(drawing, qt_errors):
    _window, canvas = drawing
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(-40, 0), QPointF(40, 0), style="double_center", order=2
    )
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    history = canvas.services.history_service
    count = len(history.state.history)
    end = start_drag(canvas, "molecule", QPointF(0, 0))
    assert canvas.services.tool_controller.active.has_active_gesture
    assert session.snapshot_state() != before

    class SelectingMenu(QMenu):
        def exec(self, _position):
            assert not canvas.services.tool_controller.active.has_active_gesture
            action = self.actions()[2]
            action.trigger()
            return action

    bond_item = canvas.runtime_state.bond_graphics_state.bond_items[0][0]
    menu_position = canvas.mapFromScene(bond_item.sceneBoundingRect().center())
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(menu_position),
        QPointF(canvas.viewport().mapToGlobal(menu_position)),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert canvas.services.pointer_controller._show_double_bond_context_menu(
        event, menu_factory=SelectingMenu
    )
    after = session.snapshot_state()
    assert after["model"]["atoms"] == before["model"]["atoms"]
    assert canvas.model.bonds[0].style == "double_outer"
    assert len(history.state.history) == count + 1
    release(canvas, end)
    assert not qt_errors
    assert session.snapshot_state() == after
    history.undo()
    assert session.snapshot_state() == before
    history.redo()
    assert session.snapshot_state() == after


def invoke(window, canvas, operation, route):
    if route == "window":
        if operation == "undo":
            action = window.ui_references.undo_action
            assert action.isEnabled()
            action.trigger()
        elif operation == "redo":
            action = window.ui_references.redo_action
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
    canvas.services.input_controller.key_press_event(
        QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
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
    empty = canvas.services.canvas_document_session_service.snapshot_state()
    point, item = populate(canvas, kind)
    original = canvas.services.canvas_document_session_service.snapshot_state()
    assert original != empty
    end = start_drag(canvas, kind, point, item)
    invoke(window, canvas, "undo", route)
    after_action = canvas.services.canvas_document_session_service.snapshot_state()
    stacks = canvas.services.history_service.capture_stack_snapshot()
    release(canvas, end)
    assert not qt_errors
    assert (
        canvas.services.canvas_document_session_service.snapshot_state()
        == after_action
        == empty
    )
    canvas.services.history_service.verify_stack_snapshot(stacks)
    invoke(window, canvas, "redo", route)
    assert canvas.services.canvas_document_session_service.snapshot_state() == original


@pytest.mark.parametrize(
    "operation,route", [("delete", "canvas"), ("cut", "canvas"), ("cut", "window")]
)
def test_delete_or_cut_cancels_move_before_mutating_selection(
    drawing, qt_errors, operation, route
):
    window, canvas = drawing
    empty = canvas.services.canvas_document_session_service.snapshot_state()
    point, item = populate(canvas, "arrow")
    original = canvas.services.canvas_document_session_service.snapshot_state()
    end = start_drag(canvas, "arrow", point, item)
    invoke(window, canvas, operation, route)
    after_action = canvas.services.canvas_document_session_service.snapshot_state()
    stacks = canvas.services.history_service.capture_stack_snapshot()
    release(canvas, end)
    assert not qt_errors
    assert (
        canvas.services.canvas_document_session_service.snapshot_state()
        == after_action
        == empty
    )
    canvas.services.history_service.verify_stack_snapshot(stacks)
    canvas.services.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == original


@pytest.mark.parametrize("route", ["window", "canvas"])
@pytest.mark.parametrize("operation", ["undo", "redo"])
def test_history_action_during_move_of_still_existing_atoms_is_exact(
    drawing, qt_errors, operation, route
):
    window, canvas = drawing
    point, _ = populate(canvas, "molecule")
    canvas.services.selection.select_all()
    original = canvas.services.canvas_document_session_service.snapshot_state()
    canvas.services.scene_transform_controller.translate_selected_items(8.1, -4.3)
    edited = canvas.services.canvas_document_session_service.snapshot_state()
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
    assert canvas.services.canvas_document_session_service.snapshot_state() == expected
    canvas.services.history_service.verify_stack_snapshot(stacks)
    history = canvas.services.history_service
    while history.can_undo():
        history.undo()
    while history.can_redo():
        history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == edited


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
                from chemvas.ui.window.main_window_ports import undo_for_window

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
    canvas.services.scene_decoration_service.add_arrow(
        QPointF(130, 90), QPointF(175, 90), "arrow"
    )
    history.undo()
    original = canvas.services.canvas_document_session_service.snapshot_state()
    stacks = history.capture_stack_snapshot()
    assert stacks.redo_stack
    end = start_drag(canvas, "delete", point, item)
    tool = canvas.services.tool_controller.active
    session = tool._delete_session
    assert session is not None and session.active and tool._changed
    pending = canvas.services.canvas_document_session_service.snapshot_state()
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
                from chemvas.ui.window.main_window_ports import undo_for_window

                undo_for_window(window)
            else:
                invoke(window, canvas, "undo", route)
        undo.assert_not_called()
    assert not tool._erasing
    assert tool._delete_session is session and session.active
    history.verify_stack_snapshot(stacks)
    release(canvas, end)
    assert not qt_errors
    assert canvas.services.canvas_document_session_service.snapshot_state() == pending
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
    assert canvas.services.canvas_document_session_service.snapshot_state() == original
    history.verify_stack_snapshot(stacks)
    release(canvas, end)
    assert canvas.services.canvas_document_session_service.snapshot_state() == original
    history.verify_stack_snapshot(stacks)


def test_idle_history_action_does_not_reset_select_handles(drawing):
    window, canvas = drawing
    _point, item = populate(canvas, "arrow")
    tool = canvas.services.tool_controller.active
    canvas.services.handle_overlay_service.show_endpoint_handles(item)
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
    canvas.services.selection.select_all()
    original = canvas.services.canvas_document_session_service.snapshot_state()
    if operation == "paste":
        assert canvas.services.scene_clipboard_controller.copy_selection_to_clipboard()
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
        canvas.services.input_controller.key_press_event(event)
    expected = canvas.services.canvas_document_session_service.snapshot_state()
    assert expected != original
    stacks = canvas.services.history_service.capture_stack_snapshot()
    release(canvas, end)
    assert not qt_errors
    assert canvas.services.canvas_document_session_service.snapshot_state() == expected
    canvas.services.history_service.verify_stack_snapshot(stacks)
    canvas.services.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == original
    canvas.services.history_service.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == expected


def test_shift_modifier_does_not_cancel_active_rotation(drawing, qt_errors):
    _window, canvas = drawing
    point, item = populate(canvas, "molecule")
    before = canvas.services.canvas_document_session_service.snapshot_state()
    end = start_drag(canvas, "rotation", point, item)
    tool = canvas.services.tool_controller.active
    session = tool._rotation_session
    assert session is not None
    QTest.keyPress(canvas, Qt.Key.Key_Shift)
    assert tool._rotation_session is session
    QTest.keyRelease(canvas, Qt.Key.Key_Shift)
    release(canvas, end)
    assert not qt_errors
    assert canvas.services.canvas_document_session_service.snapshot_state() != before
    canvas.services.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
