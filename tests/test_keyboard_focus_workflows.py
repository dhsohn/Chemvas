"""Actual widget traversal remains available before and after note editing."""

import pytest
from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QSpinBox, QToolButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_scene_items_state import note_items_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    active_tool_name_for_window,
    current_zoom_percent_for_window,
    services_for_window,
    set_zoom_percent_for_window,
)
from chemvas.ui.main_window_status_service import _ZoomPercentButton
from tests.test_active_gesture_document_edits import qt_errors as qt_errors
from tests.test_note_editing_workflows import _click, _tool
from tests.test_note_editing_workflows import app as app


@pytest.fixture
def fresh_window(app, qt_errors):
    window = build_main_window()
    window.resize(1120, 700)
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowExposed(window, 5000)
    assert QTest.qWaitForWindowActive(window, 5000)
    app.processEvents()
    canvas = active_canvas_for_window(window)
    yield window, canvas
    canvas.scene().clearFocus()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()
    assert not qt_errors


def _tab_cycle(window, canvas, backwards):
    canvas.setFocus()
    seen = []
    modifiers = (
        Qt.KeyboardModifier.ShiftModifier
        if backwards
        else Qt.KeyboardModifier.NoModifier
    )
    for _ in range(30):
        focused = QApplication.focusWidget()
        assert focused is not None
        QTest.keyClick(focused, Qt.Key.Key_Tab, modifiers)
        QApplication.processEvents()
        focused = QApplication.focusWidget()
        assert focused is not None
        if focused is canvas:
            assert seen
            return seen
        assert focused not in seen, "Focus must wrap to the canvas, not a dead end"
        seen.append(focused)
    pytest.fail("Widget traversal did not return to the drawing")


def test_fresh_window_accepts_canvas_hotkey_without_click(fresh_window, monkeypatch):
    window, canvas = fresh_window
    assert QApplication.focusWidget() is canvas
    # Keep the hover cursor away from atoms on native and offscreen platforms.
    monkeypatch.setattr(
        "chemvas.ui.hover.QCursor.pos",
        lambda: canvas.viewport().mapToGlobal(canvas.viewport().rect().center()),
    )
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_J)
    assert active_tool_name_for_window(window) == "benzene"


@pytest.mark.parametrize("backwards", [False, True])
@pytest.mark.parametrize("committed_note", [False, True])
def test_tab_cycle_preserves_drawing_and_history(
    fresh_window, backwards, committed_note
):
    window, canvas = fresh_window
    if committed_note:
        _tool(window, "note")
        _click(canvas, QPointF(0, 0))
        QTest.keyClicks(canvas, "caption")
        QTest.keyClick(canvas, Qt.Key.Key_Escape)
        _tool(window, "select")
        assert note_items_for(canvas)[0].toPlainText() == "caption"
        assert canvas.scene().focusItem() is None
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = (list(history.state.history), list(history.state.redo_stack))
    forward = _tab_cycle(window, canvas, backwards)
    reverse = _tab_cycle(window, canvas, not backwards)
    assert reverse == list(reversed(forward))
    assert snapshot_canvas_state_for(canvas) == before
    assert (history.state.history, history.state.redo_stack) == stacks


def test_active_note_keeps_tab_and_backtab_in_text_editor(fresh_window):
    window, canvas = fresh_window
    _tool(window, "note")
    _click(canvas, QPointF(0, 0))
    QTest.keyClicks(canvas, "before")
    note = note_items_for(canvas)[0]
    history = canvas.services.history_service
    count = len(history.state.history)
    QTest.keyClick(canvas, Qt.Key.Key_Tab)
    QTest.keyClicks(canvas, "after")
    assert note.toPlainText() == "before\tafter"
    QTest.keyClick(canvas, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert QApplication.focusWidget() is canvas
    assert canvas.scene().focusItem() is note
    assert note.toPlainText() == "before\tafter"
    assert len(history.state.history) == count
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert len(history.state.history) == count + 1


@pytest.mark.parametrize("which", ["context", "minus", "percent", "plus", "fit"])
def test_tab_focus_is_painted_without_resizing_control(fresh_window, which):
    window, canvas = fresh_window
    chain = _tab_cycle(window, canvas, backwards=True)
    buttons = [control for control in chain if isinstance(control, QToolButton)]
    if which == "context":
        target = next(button for button in buttons if not button.objectName())
    elif which == "percent":
        target = window.findChild(_ZoomPercentButton)
    elif which == "fit":
        target = window.findChild(QToolButton, "statusZoomFitButton")
    else:
        target = next(
            button
            for button in buttons
            if button.text() == {"minus": "−", "plus": "+"}[which]
        )
    assert target is not None
    canvas.setFocus()
    QApplication.processEvents()
    before = target.grab().toImage()
    geometry = target.geometry()
    for _ in range(30):
        QTest.keyClick(
            QApplication.focusWidget(),
            Qt.Key.Key_Tab,
            Qt.KeyboardModifier.ShiftModifier,
        )
        if QApplication.focusWidget() is target:
            break
    assert target.hasFocus()
    QApplication.processEvents()
    assert target.grab().toImage() != before
    assert target.geometry() == geometry


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_zoom_percent_keyboard_opens_existing_exact_dialog(
    fresh_window, monkeypatch, key
):
    window, canvas = fresh_window
    set_zoom_percent_for_window(window, 175)
    calls = []
    monkeypatch.setattr(
        "chemvas.ui.main_window_status_service.prompt_zoom_percent",
        lambda parent, current: calls.append((parent, current)) or 142,
    )
    button = window.findChild(_ZoomPercentButton)
    button.setFocus()
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = (list(history.state.history), list(history.state.redo_stack))
    QTest.keyClick(button, key)
    assert calls == [(window, 175)]
    assert current_zoom_percent_for_window(window) == 142
    assert snapshot_canvas_state_for(canvas) == before
    assert (history.state.history, history.state.redo_stack) == stacks


def test_zoom_percent_space_resets_without_mouse_delay(fresh_window):
    window, canvas = fresh_window
    set_zoom_percent_for_window(window, 175)
    button = window.findChild(_ZoomPercentButton)
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert current_zoom_percent_for_window(window) == 100


def test_zoom_dialog_accepts_enter_from_its_text_field(fresh_window):
    window, canvas = fresh_window
    set_zoom_percent_for_window(window, 175)
    seen = []

    def enter_value():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        # Close even if a future input regression prevents Enter acceptance.
        QTimer.singleShot(1500, dialog.reject)
        assert dialog.windowTitle() == "Set Zoom"
        spin = dialog.findChild(QSpinBox)
        assert spin.value() == 175
        spin.setFocus()
        spin.selectAll()
        QTest.keyClicks(spin, "142")
        QTest.keyClick(spin, Qt.Key.Key_Return)
        seen.append(spin.value())

    button = window.findChild(_ZoomPercentButton)
    button.setFocus()
    before = snapshot_canvas_state_for(canvas)
    QTimer.singleShot(0, enter_value)
    QTest.keyClick(button, Qt.Key.Key_Return)
    assert seen == [142]
    assert current_zoom_percent_for_window(window) == 142
    assert snapshot_canvas_state_for(canvas) == before


def test_smiles_field_tab_preserves_text_and_returns_through_widget_chain(fresh_window):
    window, canvas = fresh_window
    _tool(window, "benzene")
    field = window.findChild(QLineEdit, "contextSmilesInput")
    button = window.findChild(QToolButton, "smiles_render_button")
    assert field.isVisible() and button.isVisible()
    field.setFocus()
    QTest.keyClicks(field, "CCO")
    before = snapshot_canvas_state_for(canvas)
    QTest.keyClick(field, Qt.Key.Key_Tab)
    assert QApplication.focusWidget() is button
    QTest.keyClick(button, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert QApplication.focusWidget() is field
    assert field.text() == "CCO"
    _tab_cycle(window, canvas, backwards=False)
    assert field.text() == "CCO"
    assert snapshot_canvas_state_for(canvas) == before


def test_zoom_percent_mouse_single_double_contract_is_unchanged(app):
    calls = []
    button = _ZoomPercentButton(
        lambda: calls.append("single"), lambda: calls.append("double")
    )
    button.show()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert calls == []
    button._emit_single()
    assert calls == ["single"]
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QTest.mouseDClick(button, Qt.MouseButton.LeftButton)
    button._emit_single()
    assert calls == ["single", "double"]
    button.close()
