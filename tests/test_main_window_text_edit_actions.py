import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTextCursor, QTextDocument
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit

from chemvas.ui.canvas_scene_items_state import note_items_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import history_service_for_window
from tests.test_note_editing_workflows import _click, _key, _saved_note, _tool
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


def _edit_menu(window):
    return next(a.menu() for a in window.menuBar().actions() if a.text() == "Edit")


def _action(window, name):
    menu = _edit_menu(window)
    menu.aboutToShow.emit()
    return next(a for a in menu.actions() if a.text() == name)


def _smiles_with_drawing(drawing):
    window, canvas = drawing
    _tool(window, "bond")
    _click(canvas, QPointF(70, -35))
    assert canvas.model.bonds
    _tool(window, "select")
    _key(canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert canvas.scene().selectedItems()
    baseline = snapshot_canvas_state_for(canvas)
    field = window.findChild(QLineEdit, "contextSmilesInput")
    field.setFocus()
    QTest.keyClicks(field, "CCN")
    assert field.hasFocus()
    return field, baseline


def test_smiles_menu_cut_copy_paste_and_select_all_keep_drawing(drawing):
    window, canvas = drawing
    field, baseline = _smiles_with_drawing(drawing)
    field.setSelection(2, 1)
    _action(window, "Copy").trigger()
    assert QApplication.clipboard().text() == "N"
    _action(window, "Cut").trigger()
    assert field.text() == "CC"
    _action(window, "Paste").trigger()
    assert field.text() == "CCN"
    _action(window, "Select All").trigger()
    assert field.selectedText() == "CCN"
    assert field.hasFocus()
    assert snapshot_canvas_state_for(canvas) == baseline


def test_smiles_menu_undo_redo_uses_text_history_then_canvas_history(drawing):
    window, canvas = drawing
    field, baseline = _smiles_with_drawing(drawing)
    undo = _action(window, "Undo")
    assert undo.isEnabled()
    undo.trigger()
    assert field.text() == ""
    assert not _action(window, "Undo").isEnabled()
    redo = _action(window, "Redo")
    assert redo.isEnabled()
    redo.trigger()
    assert field.text() == "CCN"
    assert snapshot_canvas_state_for(canvas) == baseline
    canvas.setFocus()
    _action(window, "Undo").trigger()
    assert not canvas.model.bonds
    assert field.text() == "CCN"
    _action(window, "Redo").trigger()
    assert snapshot_canvas_state_for(canvas) == baseline


def test_empty_drawing_enables_menu_undo_for_typed_smiles(drawing):
    window, _canvas = drawing
    field = window.findChild(QLineEdit, "contextSmilesInput")
    field.setFocus()
    QTest.keyClicks(field, "CCN")
    assert not history_service_for_window(window).can_undo()
    undo = _action(window, "Undo")
    assert undo.isEnabled()
    undo.trigger()
    assert field.text() == ""
    assert _action(window, "Redo").isEnabled()


@pytest.mark.parametrize("action", ["Copy", "Cut"])
def test_empty_text_selection_does_not_use_selected_canvas_objects(drawing, action):
    window, canvas = drawing
    field, baseline = _smiles_with_drawing(drawing)
    assert not field.hasSelectedText()
    QApplication.clipboard().setText("previous clipboard")
    _action(window, action).trigger()
    assert field.text() == "CCN"
    assert QApplication.clipboard().text() == "previous clipboard"
    assert snapshot_canvas_state_for(canvas) == baseline


@pytest.mark.parametrize("action", ["Cut", "Paste", "Undo", "Redo"])
def test_read_only_text_field_does_not_edit_drawing(drawing, action):
    window, canvas = drawing
    field, baseline = _smiles_with_drawing(drawing)
    field.setReadOnly(True)
    field.selectAll()
    _action(window, action).trigger()
    assert field.text() == "CCN"
    assert snapshot_canvas_state_for(canvas) == baseline
    assert not _action(window, "Undo").isEnabled()
    assert not _action(window, "Redo").isEnabled()


def test_note_menu_clipboard_preserves_partial_rich_text_and_editor(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    cursor = note.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
    fmt = cursor.charFormat()
    fmt.setFontWeight(700)
    cursor.mergeCharFormat(fmt)
    note.setTextCursor(cursor)
    history = history_service_for_window(window)
    count = len(history.state.history)
    _action(window, "Copy").trigger()
    mime = QApplication.clipboard().mimeData()
    assert mime.text() == "beta"
    assert mime.hasHtml()
    copied = QTextDocument()
    copied.setHtml(mime.html())
    copied_cursor = QTextCursor(copied)
    copied_cursor.movePosition(QTextCursor.MoveOperation.Right)
    assert copied_cursor.charFormat().fontWeight() == 700
    _action(window, "Cut").trigger()
    assert note.toPlainText() == "alpha  gamma"
    assert note_items_for(canvas) == [note]
    _action(window, "Paste").trigger()
    assert note.toPlainText() == "alpha beta gamma"
    _action(window, "Select All").trigger()
    assert note.textCursor().selectedText() == "alpha beta gamma"
    assert note.hasFocus()
    assert len(history.state.history) == count


def test_note_menu_undo_redo_stays_inside_active_edit_session(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    history = history_service_for_window(window)
    count = len(history.state.history)
    QTest.keyClicks(canvas, " changed")
    _action(window, "Undo").trigger()
    assert note.toPlainText() == "alpha beta gamma"
    assert not _action(window, "Undo").isEnabled()
    assert _action(window, "Redo").isEnabled()
    _action(window, "Redo").trigger()
    assert note.toPlainText() == "alpha beta gamma changed"
    assert note.hasFocus()
    assert len(history.state.history) == count


def test_text_target_is_owned_by_action_window(drawing):
    from chemvas.bootstrap.main_window import build_main_window
    from chemvas.ui.main_window_ports import (
        active_canvas_for_window,
        services_for_window,
    )

    first, _canvas = drawing
    second = build_main_window()
    second.show()
    second.activateWindow()
    try:
        field = second.findChild(QLineEdit, "contextSmilesInput")
        field.setFocus()
        QTest.keyClicks(field, "CCN")
        field.selectAll()
        _action(first, "Cut").trigger()
        assert field.text() == "CCN"
    finally:
        services_for_window(second).canvas_document_service.mark_clean(
            active_canvas_for_window(second)
        )
        second.close()
        QApplication.processEvents()
