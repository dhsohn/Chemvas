"""Edit > Rotate... hands the canvas to the Select tool, not just its button."""

from PyQt6.QtWidgets import QMenuBar, QToolButton

from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.main_window_ports import active_tool_name_for_window
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


def _menu_action(window, menu_title: str, text: str):
    menu_bar = window.findChild(QMenuBar)
    menu = next(a.menu() for a in menu_bar.actions() if a.text() == menu_title)
    return next(a for a in menu.actions() if a.text() == text)


def test_edit_rotate_switches_the_canvas_to_the_select_tool(drawing):
    window, canvas = drawing
    canvas_services_for(canvas).input.tool_mode_controller.set_tool("bond")
    assert active_tool_name_for_window(window) == "bond"

    _menu_action(window, "Edit", "Rotate...").trigger()

    assert active_tool_name_for_window(window) == "select"
    rotate_button = window.findChild(QToolButton, "rotateApplyButton")
    assert rotate_button is not None
    assert rotate_button.isVisibleTo(window)
