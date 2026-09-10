import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit

from chemvas.ui.main_window_ports import (
    active_tool_name_for_window,
    select_all_for_window,
    services_for_window,
    set_zoom_percent_for_window,
    tool_mode_controller_for_window,
)
from tests.test_note_editing_workflows import _key, _tool
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


@pytest.mark.parametrize(
    ("initial", "key", "modifiers", "expected_tool", "expected_hint"),
    [
        (
            "bond",
            Qt.Key.Key_Space,
            Qt.KeyboardModifier.NoModifier,
            "select",
            "Select: double-click arrows/lines for labels",
        ),
        (
            "arrow",
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
            "select",
            "Select: double-click arrows/lines for labels",
        ),
        (
            "bond",
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
            "select",
            "Select: double-click arrows/lines for labels",
        ),
        (
            "select",
            Qt.Key.Key_X,
            Qt.KeyboardModifier.NoModifier,
            "bond",
            "Bond: click-drag to draw",
        ),
        (
            "select",
            Qt.Key.Key_E,
            Qt.KeyboardModifier.NoModifier,
            "arrow",
            "Arrow: drag to draw; double-click for labels",
        ),
        (
            "select",
            Qt.Key.Key_T,
            Qt.KeyboardModifier.NoModifier,
            "note",
            "Text: click to add/edit; Esc to finish",
        ),
        (
            "select",
            Qt.Key.Key_J,
            Qt.KeyboardModifier.NoModifier,
            "benzene",
            "Ring: click to place template",
        ),
    ],
)
def test_canvas_shortcuts_refresh_tool_hint(
    drawing, initial, key, modifiers, expected_tool, expected_hint
):
    window, canvas = drawing
    _tool(window, initial)
    canvas.setFocus()
    QApplication.processEvents()

    _key(canvas, key, modifiers)

    assert active_tool_name_for_window(window) == expected_tool
    assert window.statusBar().currentMessage() == expected_hint


def test_select_all_action_refreshes_tool_hint(drawing):
    window, canvas = drawing
    _tool(window, "bond")
    canvas.setFocus()

    select_all_for_window(window)

    assert active_tool_name_for_window(window) == "select"
    assert window.statusBar().currentMessage() == (
        "Select: double-click arrows/lines for labels"
    )


def test_smiles_select_all_keeps_text_focus_and_tool_hint(drawing):
    window, _canvas = drawing
    _tool(window, "benzene")
    field = window.findChild(QLineEdit, "contextSmilesInput")
    field.setFocus()
    QTest.keyClicks(field, "CCN")
    hint = window.statusBar().currentMessage()

    select_all_for_window(window)

    assert field.hasFocus()
    assert field.selectedText() == "CCN"
    assert active_tool_name_for_window(window) == "benzene"
    assert window.statusBar().currentMessage() == hint


def test_inactive_canvas_cannot_replace_active_tool_hint(drawing):
    window, _canvas = drawing
    _tool(window, "bond")
    first_controller = tool_mode_controller_for_window(window)
    services_for_window(window).canvas_document_service.new_canvas(window)
    _tool(window, "note")

    first_controller.set_arrow_type("normal")

    assert active_tool_name_for_window(window) == "note"
    assert window.statusBar().currentMessage() == (
        "Text: click to add/edit; Esc to finish"
    )
    window.tab_references.canvas_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert active_tool_name_for_window(window) == "arrow"
    assert window.statusBar().currentMessage() == (
        "Arrow: drag to draw; double-click for labels"
    )


def test_zoom_and_selection_updates_preserve_operation_feedback(drawing):
    window, _canvas = drawing
    window.statusBar().showMessage("Saved drawing", 5000)

    set_zoom_percent_for_window(window, 125)
    services_for_window(window).active_canvas_ui_service.handle_selection_info(window)

    assert window.statusBar().currentMessage() == "Saved drawing"
