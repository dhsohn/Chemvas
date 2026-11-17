from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QMetaObject, QPointF, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QToolButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from tests.gui_workflow_support import _tool
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


def cpp_toggle(button: QToolButton) -> None:
    QMetaObject.invokeMethod(button, "toggle", Qt.ConnectionType.DirectConnection)


def _tool_button_by_tip(window, tip: str) -> QToolButton:
    return next(
        button for button in window.findChildren(QToolButton) if button.toolTip() == tip
    )


@pytest.fixture
def window(qt_application):
    window = build_main_window()
    yield window
    services = window.services
    for canvas in window.tab_references.all_canvases():
        services.canvas_document_service.mark_clean(canvas)
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("key", ["bond", "select", "mark", "arrow", "bond_hash"])
def test_toolbar_choice_publishes_one_complete_tool_update(window, key):
    services = window.services
    canvas = active_canvas_for_window(window)
    controller = canvas.services.tool_mode_controller
    services.tool_state_service.set_bond_style(window, "Double")
    with (
        patch.object(
            controller, "_emit_tool_changed", wraps=controller._emit_tool_changed
        ) as emit,
        patch.object(
            services.context_bar_service,
            "refresh_window",
            wraps=services.context_bar_service.refresh_window,
        ) as refresh,
    ):
        # Re-selecting the active tool must still cancel insertion/reset defaults,
        # but must not publish an intermediate state or refresh it twice.
        for _ in range(2):
            emit.reset_mock()
            refresh.reset_mock()
            window.ui_references.tool_actions[key].trigger()
            emit.assert_called_once_with()
            refresh.assert_called_once_with(window)
    settings = canvas.runtime_state.tool_settings_state
    if key == "bond":
        assert (settings.active_bond_style, settings.active_bond_order) == ("single", 1)
    elif key == "bond_hash":
        assert (settings.active_bond_style, settings.active_bond_order) == ("hash", 1)
    assert window.statusBar().currentMessage()


def test_top_toolbar_accessibility_toggle_selects_tool_and_publishes_once(window):
    services = window.services
    canvas = active_canvas_for_window(window)
    controller = canvas.services.tool_mode_controller
    bond_action = window.ui_references.tool_actions["bond"]
    ring_button = window.findChild(QToolButton, "toolButton_benzene")
    assert ring_button is not None

    with (
        patch.object(
            controller, "_emit_tool_changed", wraps=controller._emit_tool_changed
        ) as emit,
        patch.object(
            services.context_bar_service,
            "refresh_window",
            wraps=services.context_bar_service.refresh_window,
        ) as refresh,
    ):
        cpp_toggle(ring_button)

    assert canvas.services.tool_controller.active.name == "benzene"
    assert services.status_service.status_context_texts()["tool"] == "Tool: Ring"
    assert window.ui_references.tool_actions["benzene"].isChecked()
    assert not bond_action.isChecked()
    benzene_template = _tool_button_by_tip(window, "Benzene")
    assert benzene_template.isChecked()
    emit.assert_called_once_with()
    refresh.assert_called_once_with(window)


def test_top_toolbar_cpp_toggle_active_tool_stays_checked_and_publishes_once(window):
    services = window.services
    controller = active_canvas_for_window(window).services.tool_mode_controller
    window.ui_references.tool_actions["benzene"].trigger()
    ring_button = window.findChild(QToolButton, "toolButton_benzene")
    assert ring_button is not None
    group = window.ui_references.tool_actions["benzene"].actionGroup()
    assert group is not None

    with (
        patch.object(
            controller, "_emit_tool_changed", wraps=controller._emit_tool_changed
        ) as emit,
        patch.object(
            services.context_bar_service,
            "refresh_window",
            wraps=services.context_bar_service.refresh_window,
        ) as refresh,
    ):
        cpp_toggle(ring_button)

    assert ring_button.isChecked()
    assert window.ui_references.tool_actions["benzene"].isChecked()
    assert group.checkedAction() is window.ui_references.tool_actions["benzene"]
    emit.assert_called_once_with()
    refresh.assert_called_once_with(window)


def test_top_toolbar_toggle_and_click_each_publish_one_complete_update(window):
    services = window.services
    canvas = active_canvas_for_window(window)
    controller = canvas.services.tool_mode_controller
    ring_button = window.findChild(QToolButton, "toolButton_benzene")
    assert ring_button is not None
    window.ui_references.tool_actions["select"].trigger()

    with (
        patch.object(
            controller, "_emit_tool_changed", wraps=controller._emit_tool_changed
        ) as emit,
        patch.object(
            services.context_bar_service,
            "refresh_window",
            wraps=services.context_bar_service.refresh_window,
        ) as refresh,
    ):
        cpp_toggle(ring_button)
        emit.assert_called_once_with()
        refresh.assert_called_once_with(window)

        emit.reset_mock()
        refresh.reset_mock()
        ring_button.click()
        emit.assert_called_once_with()
        refresh.assert_called_once_with(window)


def test_canvas_tool_sync_does_not_reset_bond_style_after_wedge(window):
    services = window.services
    canvas = active_canvas_for_window(window)
    services.tool_state_service.set_bond_style(window, "Wedge")
    settings = canvas.runtime_state.tool_settings_state
    assert settings.active_bond_style == "wedge"

    services.tool_state_service.sync_tool_actions_from_canvas(window)

    assert settings.active_bond_style == "wedge"
    assert window.ui_references.tool_actions["bond"].isChecked()


def test_context_ring_template_accessibility_toggle_applies_choice(window):
    insert_controller = active_canvas_for_window(window).services.insert_controller
    window.ui_references.tool_actions["benzene"].trigger()

    benzene = _tool_button_by_tip(window, "Benzene")
    cyclopropane = _tool_button_by_tip(window, "Cyclopropane")
    assert benzene.isChecked()

    with patch.object(
        insert_controller,
        "begin_ring_template_insert",
        wraps=insert_controller.begin_ring_template_insert,
    ) as begin_insert:
        cpp_toggle(cyclopropane)

    begin_insert.assert_called_once_with(3, style="regular")
    assert cyclopropane.isChecked()
    assert not benzene.isChecked()
    insert_state = active_canvas_for_window(window).runtime_state.insert_state
    assert insert_state.template_ring_size == 3
    assert insert_state.template_ring_style == "regular"


def test_context_wedge_accessibility_toggle_applies_bond_style(window):
    window.ui_references.tool_actions["bond"].trigger()
    wedge = _tool_button_by_tip(window, "Wedge bond (W)")
    assert not wedge.isChecked()

    cpp_toggle(wedge)

    settings = active_canvas_for_window(window).runtime_state.tool_settings_state
    assert settings.active_bond_style == "wedge"
    assert wedge.isChecked()


def test_select_context_perspective_accessibility_toggle_activates_tool(window):
    services = window.services
    canvas = active_canvas_for_window(window)
    controller = canvas.services.tool_mode_controller
    window.ui_references.tool_actions["select"].trigger()
    perspective_button = window.findChild(QToolButton, "toolButton_perspective")
    assert perspective_button is not None

    with (
        patch.object(
            controller, "_emit_tool_changed", wraps=controller._emit_tool_changed
        ) as emit,
        patch.object(
            services.context_bar_service,
            "refresh_window",
            wraps=services.context_bar_service.refresh_window,
        ) as refresh,
    ):
        cpp_toggle(perspective_button)

    assert canvas.services.tool_controller.active.name == "perspective"
    assert services.status_service.status_context_texts()["tool"] == "Tool: Perspective"
    emit.assert_called_once_with()
    refresh.assert_called_once_with(window)


def test_text_corner_menu_cpp_toggle_selects_tool_once(window):
    services = window.services
    canvas = active_canvas_for_window(window)
    controller = canvas.services.tool_mode_controller
    window.ui_references.tool_actions["select"].trigger()
    note_button = window.findChild(QToolButton, "toolButton_note")
    assert note_button is not None

    with (
        patch.object(
            controller, "_emit_tool_changed", wraps=controller._emit_tool_changed
        ) as emit,
        patch.object(
            services.context_bar_service,
            "refresh_window",
            wraps=services.context_bar_service.refresh_window,
        ) as refresh,
    ):
        cpp_toggle(note_button)

    assert canvas.services.tool_controller.active.name == "note"
    emit.assert_called_once_with()
    refresh.assert_called_once_with(window)


def test_context_bold_cpp_toggle_applies_and_unchecks(drawing):
    window, canvas = drawing
    _tool(window, "note")
    controller = canvas.services.note_controller
    note = controller.create_text_note(QPointF(-70, -20), "Caption")
    controller.begin_note_edit(note)
    cursor = note.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    note.setTextCursor(cursor)
    bold = _tool_button_by_tip(window, "Bold the selected text")

    cpp_toggle(bold)
    assert "font-weight:700" in note.toHtml()
    assert bold.isChecked()

    cpp_toggle(bold)
    assert "font-weight:700" not in note.toHtml()
    assert not bold.isChecked()


def test_ring_fill_override_is_cleared_by_direct_canvas_tool_change(window):
    services = window.services
    window.ui_references.tool_actions["ring_fill"].trigger()
    assert window.runtime_state.context_bar_page_override == "ring_fill"
    assert (
        active_canvas_for_window(window).services.tool_controller.active.name
        == "select"
    )
    controller = active_canvas_for_window(window).services.tool_mode_controller
    controller.set_arrow_type("reaction")
    assert window.runtime_state.context_bar_page_override is None
    assert window.ui_references.tool_actions["arrow"].isChecked()
    assert services.status_service.status_context_texts()["tool"] == "Tool: Arrow"
