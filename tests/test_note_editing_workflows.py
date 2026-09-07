import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_callback_state import callback_state_for
from chemvas.ui.canvas_scene_items_state import note_items_for
from chemvas.ui.canvas_service_ports import note_controller_for_access
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    history_service_for_window,
    services_for_window,
    set_zoom_percent_for_window,
    tool_action_for_window,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def drawing(app):
    window = build_main_window()
    window.resize(1120, 700)
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    set_zoom_percent_for_window(window, 180)
    canvas.centerOn(0, 0)
    QTest.qWait(30)
    yield window, canvas
    canvas.scene().clearFocus()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


def _tool(window, name):
    action = tool_action_for_window(window, name)
    button = next(
        b for b in window.findChildren(QToolButton) if b.defaultAction() is action
    )
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def _click(canvas, scene_pos):
    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(scene_pos)
    )
    QApplication.processEvents()


def _key(canvas, key, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(canvas, key, modifiers)
    QApplication.processEvents()


def _saved_note(drawing, tmp_path):
    window, canvas = drawing
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    QTest.keyClicks(canvas, "alpha beta gamma")
    note = note_items_for(canvas)[0]
    _tool(window, "select")
    _click(canvas, QPointF(160, 100))
    actions = services_for_window(window).document_action_service
    assert actions.save_canvas_to_path(window, str(tmp_path / "note.chemvas"))
    assert not window.isWindowModified()
    _tool(window, "note")
    _click(canvas, note.sceneBoundingRect().center())
    assert note.hasFocus()
    _key(canvas, Qt.Key.Key_End)
    return note


def test_tool_switch_commits_note_and_routes_undo_to_drawing(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    QTest.keyClicks(canvas, " changed")
    _tool(window, "bond")
    assert not note.hasFocus()
    assert note.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction
    _click(canvas, QPointF(70, -35))
    assert len(canvas.model.bonds) == 1
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert not canvas.model.bonds
    assert note.toPlainText() == "alpha beta gamma changed"
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "alpha beta gamma"


def test_text_undo_stays_inside_reopened_edit_session(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    history = history_service_for_window(window)
    count = len(history.state.history)
    QTest.keyClicks(canvas, " changed", delay=10)
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "alpha beta gamma"
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "alpha beta gamma"
    _key(canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "alpha beta gamma changed"
    assert len(history.state.history) == count


def _text_point(canvas, note, index):
    block = note.document().firstBlock()
    layout = block.layout()
    line = layout.lineAt(0)
    x, _ = line.cursorToX(index)
    # Stay inside the text area even when view-coordinate rounding shifts the
    # left margin by a fraction of a scene pixel.
    local = layout.position() + QPointF(x + 0.5, line.y() + line.height() / 2)
    return canvas.mapFromScene(note.mapToScene(local))


def test_editing_note_supports_mouse_drag_selection(drawing, tmp_path):
    _, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    start, end = [_text_point(canvas, note, i) for i in (0, 6)]
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, 30)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert note.textCursor().selectedText() == "alpha "
    QTest.keyClicks(canvas, "new ")
    assert note.toPlainText() == "new beta gamma"


def test_unsaved_chrome_tracks_live_text_and_undo(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    services = services_for_window(window)
    count = len(history_service_for_window(window).state.history)
    QTest.keyClicks(canvas, " changed")
    QApplication.processEvents()
    assert services.canvas_document_service.is_dirty(canvas)
    assert window.isWindowModified()
    assert "●" in window.tab_references.canvas_tabs.tabText(0)
    assert note.hasFocus()
    assert len(history_service_for_window(window).state.history) == count
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert not services.canvas_document_service.is_dirty(canvas)
    assert not window.isWindowModified()
    assert "●" not in window.tab_references.canvas_tabs.tabText(0)


def test_double_click_selects_word_and_later_click_places_caret(drawing, tmp_path):
    _, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    QTest.mouseDClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=_text_point(canvas, note, 2),
    )
    assert note.textCursor().selectedText() == "alpha"
    QTest.mouseRelease(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=_text_point(canvas, note, 2)
    )
    # A prompt third click selects a paragraph. Advance both the actual Qt
    # timer and QTest's synthetic event timestamps beyond that gesture window.
    interval = 2 * QApplication.doubleClickInterval() + 100
    QTest.qWait(interval)
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=_text_point(canvas, note, 1),
        delay=interval,
    )
    assert not note.textCursor().hasSelection()


def test_shift_click_extends_text_selection(drawing, tmp_path):
    _, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=_text_point(canvas, note, 1),
    )
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        _text_point(canvas, note, 6),
    )
    assert note.textCursor().selectedText() == "lpha "


def test_bold_toolbar_keeps_editor_focus_and_live_dirty_state(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    html = note.toHtml()
    _key(canvas, Qt.Key.Key_Home)
    _key(canvas, Qt.Key.Key_End, Qt.KeyboardModifier.ShiftModifier)
    button = next(
        b
        for b in window.findChildren(QToolButton)
        if b.toolTip() == "Bold the selected text"
    )
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert note.hasFocus()
    assert note.toHtml() != html
    assert window.isWindowModified()
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toHtml() == html
    assert not window.isWindowModified()


def test_empty_new_note_leaves_no_undo_or_dirty_marker(drawing):
    window, canvas = drawing
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    QTest.keyClicks(canvas, "draft")
    assert window.isWindowModified()
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    _tool(window, "bond")
    assert not note_items_for(canvas)
    assert not history_service_for_window(window).can_undo()
    assert not services_for_window(window).canvas_document_service.is_dirty(canvas)
    assert not window.isWindowModified()


def test_tool_switch_deletes_empty_existing_note_and_undo_restores_it(
    drawing, tmp_path
):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    _key(canvas, Qt.Key.Key_Home)
    _key(canvas, Qt.Key.Key_End, Qt.KeyboardModifier.ShiftModifier)
    _key(canvas, Qt.Key.Key_Backspace)
    _tool(window, "bond")
    assert not note_items_for(canvas)
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note_items_for(canvas) == [note]
    assert note.toPlainText() == "alpha beta gamma"
    assert not window.isWindowModified()
    _key(canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert not note_items_for(canvas)
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "alpha beta gamma"


def test_repeated_begin_edit_does_not_clear_active_session_undo(drawing, tmp_path):
    _, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    QTest.keyClicks(canvas, " changed")
    note_controller_for_access(canvas).begin_note_edit(note)
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "alpha beta gamma"


def test_save_while_editing_keeps_session_undo_and_updates_chrome(drawing, tmp_path):
    import json

    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    QTest.keyClicks(canvas, " changed")
    _key(canvas, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    assert note.hasFocus()
    assert not window.isWindowModified()
    payload = json.loads((tmp_path / "note.chemvas").read_text(encoding="utf-8"))
    assert payload["state"]["notes"][0]["text"] == "alpha beta gamma changed"
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "alpha beta gamma"
    assert window.isWindowModified()
    _key(canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "alpha beta gamma changed"
    assert not window.isWindowModified()


def test_switch_between_notes_commits_each_edit_independently(drawing, tmp_path):
    window, canvas = drawing
    first = _saved_note(drawing, tmp_path)
    QTest.keyClicks(canvas, " changed")
    _click(canvas, QPointF(-80, 80))
    QTest.keyClicks(canvas, "second")
    second = next(n for n in note_items_for(canvas) if n is not first)
    _tool(window, "bond")
    history = history_service_for_window(window)
    history.undo()
    assert note_items_for(canvas) == [first]
    assert first.toPlainText() == "alpha beta gamma changed"
    history.undo()
    assert first.toPlainText() == "alpha beta gamma"
    history.redo()
    history.redo()
    assert second in note_items_for(canvas)
    assert second.toPlainText() == "second"


def test_rich_text_session_undo_preserves_committed_format(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    cursor = note.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    note.setTextCursor(cursor)
    note_controller_for_access(canvas).toggle_text_bold()
    _tool(window, "select")
    html = note.toHtml()
    _tool(window, "note")
    _click(canvas, note.sceneBoundingRect().center())
    _key(canvas, Qt.Key.Key_End)
    QTest.keyClicks(canvas, " changed")
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toHtml() == html


def test_dirty_observer_failure_does_not_lose_editor_text_or_history(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    callback_state = callback_state_for(canvas)
    original = callback_state.document_change

    def fail_refresh():
        raise RuntimeError("chrome refresh failed")

    callback_state.document_change = fail_refresh
    try:
        QTest.keyClicks(canvas, " changed")
        assert note.toPlainText() == "alpha beta gamma changed"
        _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert note.toPlainText() == "alpha beta gamma"
        _key(canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        _tool(window, "bond")
        history_service_for_window(window).undo()
        assert note.toPlainText() == "alpha beta gamma"
    finally:
        callback_state.document_change = original
