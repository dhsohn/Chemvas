"""Real canvas input keeps mark placement distinct from electronic ownership."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMenu

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
    set_zoom_percent_for_window,
)
from chemvas.ui.mark_item_access import mark_center_for
from chemvas.ui.mark_reassignment_dialog import MarkReassignmentDialog
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.selection_outline_state import selection_outlines_for
from chemvas.ui.structure_mutation_access import add_atom_for


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def drawing(app):
    window = build_main_window()
    window.resize(1100, 760)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    set_zoom_percent_for_window(window, 200)
    canvas.centerOn(0, 0)
    canvas.services.input.tool_mode_controller.set_tool("select")
    owner = add_atom_for(canvas, "N", -60, 0)
    target = add_atom_for(canvas, "O", 60, 0)
    mark = add_mark_for_atom_for(canvas, owner, QPointF(-50, -10), kind="plus")
    center = mark_center_for(canvas, mark)
    move_item_for(canvas, mark, -center.x(), -center.y())
    canvas.services.history_service.clear()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    app.processEvents()
    yield window, canvas, mark, owner, target
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


def _owner_outline(canvas):
    outlines = [
        item
        for item in selection_outlines_for(canvas)
        if (item.data(2) or {}).get("kind") == "mark_owner"
    ]
    assert len(outlines) == 1
    return outlines[0]


def _select_mark(canvas, mark):
    position = canvas.mapFromScene(mark_center_for(canvas, mark))
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
    assert mark.isSelected()
    return position


def test_real_drag_keeps_owner_highlight_stationary_and_undo_exact(drawing, app):
    _window, canvas, mark, owner, _target = drawing
    start = _select_mark(canvas, mark)
    before = snapshot_canvas_state_for(canvas)
    original_atom = canvas.model.atoms[owner]
    owner_position = QPointF(original_atom.x, original_atom.y)
    end = canvas.mapFromScene(QPointF(30, 25))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, delay=20)
    app.processEvents()
    assert mark.data(1)["atom_id"] == owner
    outline = _owner_outline(canvas)
    assert outline.sceneBoundingRect().contains(owner_position)
    assert outline.sceneBoundingRect().contains(mark_center_for(canvas, mark))
    assert "far" in outline.toolTip().lower()
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    after = snapshot_canvas_state_for(canvas)
    assert after["model"] == before["model"]
    assert after["marks"] != before["marks"]
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_real_nudge_and_deselect_preserve_binding_and_clear_owner_overlay(drawing):
    _window, canvas, mark, owner, _target = drawing
    _select_mark(canvas, mark)
    before = snapshot_canvas_state_for(canvas)
    QTest.keyClick(
        canvas.viewport(), Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
    )
    after = snapshot_canvas_state_for(canvas)
    assert after["model"] == before["model"]
    assert after["marks"] != before["marks"]
    assert mark.data(1)["atom_id"] == owner
    assert _owner_outline(canvas).data(2)["atom_id"] == owner
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(0, 100)),
    )
    assert not mark.isSelected()
    assert not [
        item
        for item in selection_outlines_for(canvas)
        if (item.data(2) or {}).get("kind") == "mark_owner"
    ]
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("outcome", ["accept", "cancel", "unchanged"])
def test_actual_context_menu_previews_atom_before_explicit_reassignment(
    drawing, app, outcome
):
    window, canvas, mark, owner, target = drawing
    position = _select_mark(canvas, mark)
    before = snapshot_canvas_state_for(canvas)
    before_position = mark.pos()
    scroll = (canvas.horizontalScrollBar().value(), canvas.verticalScrollBar().value())
    history = canvas.services.history_service
    before_stacks = history.capture_stack_snapshot()
    completed = []
    errors = []

    def edit_dialog():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, MarkReassignmentDialog)
            assert dialog.atoms.currentData() == owner
            candidate = owner if outcome == "unchanged" else target
            dialog.atoms.setCurrentIndex(dialog.atoms.findData(candidate))
            preview = [
                item
                for item in selection_outlines_for(canvas)
                if (item.data(2) or {}).get("kind") == "mark_candidate"
            ]
            assert len(preview) == 1
            assert preview[0].data(2)["atom_id"] == candidate
            assert not preview[0].path().isEmpty()
            assert snapshot_canvas_state_for(canvas) == before
            assert mark.data(1)["atom_id"] == owner
            history.verify_stack_snapshot(before_stacks)
            standard = (
                QDialogButtonBox.StandardButton.Cancel
                if outcome == "cancel"
                else QDialogButtonBox.StandardButton.Ok
            )
            QTest.mouseClick(dialog.buttons.button(standard), Qt.MouseButton.LeftButton)
            completed.append("dialog")
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            if isinstance(dialog, QDialog) and dialog.isVisible():
                dialog.reject()

    def choose_menu():
        menu = app.activePopupWidget()
        try:
            assert isinstance(menu, QMenu)
            action = next(a for a in menu.actions() if a.text() == "Reassign to atom…")
            menu.setActiveAction(action)
            QTimer.singleShot(30, edit_dialog)
            QTest.keyClick(menu, Qt.Key.Key_Return)
            completed.append("menu")
        except Exception as exc:
            errors.append(repr(exc))
            if isinstance(menu, QMenu):
                menu.close()

    def timeout():
        errors.append("The context-menu/dialog workflow did not finish.")
        modal = app.activeModalWidget()
        if isinstance(modal, QDialog):
            modal.reject()
        popup = app.activePopupWidget()
        if popup is not None:
            popup.close()

    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(timeout)
    watchdog.start(5000)
    QTimer.singleShot(0, choose_menu)
    try:
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.RightButton, pos=position)
    finally:
        watchdog.stop()
    assert not errors
    assert completed == ["menu", "dialog"]
    assert not [
        item
        for item in selection_outlines_for(canvas)
        if (item.data(2) or {}).get("kind") == "mark_candidate"
    ]
    assert (
        canvas.horizontalScrollBar().value(),
        canvas.verticalScrollBar().value(),
    ) == scroll
    assert mark.pos() == before_position
    after = snapshot_canvas_state_for(canvas)
    if outcome == "accept":
        assert mark.data(1)["atom_id"] == target
        assert _owner_outline(canvas).data(2)["atom_id"] == target
        assert (
            f"#{target}"
            in services_for_window(window).status_service.selection_label.text()
        )
        assert len(history.state.history) == 1
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
    else:
        assert after == before
        history.verify_stack_snapshot(before_stacks)
