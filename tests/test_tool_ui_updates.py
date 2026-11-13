from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QToolButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.window.main_window_ports import active_canvas_for_window


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
        ring_button.toggle()

    assert canvas.services.tool_controller.active.name == "benzene"
    assert services.status_service.status_context_texts()["tool"] == "Tool: Ring"
    assert window.ui_references.tool_actions["benzene"].isChecked()
    assert not bond_action.isChecked()
    for ring_template_button in window.findChildren(QToolButton):
        if ring_template_button.toolTip() == "Benzene":
            assert ring_template_button.isChecked()
            break
    else:
        raise AssertionError("benzene ring template button not found")
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
        ring_button.toggle()
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

    benzene = next(
        button
        for button in window.findChildren(QToolButton)
        if button.toolTip() == "Benzene"
    )
    cyclopropane = next(
        button
        for button in window.findChildren(QToolButton)
        if button.toolTip() == "Cyclopropane"
    )
    assert benzene.isChecked()

    with patch.object(
        insert_controller,
        "begin_ring_template_insert",
        wraps=insert_controller.begin_ring_template_insert,
    ) as begin_insert:
        cyclopropane.toggle()

    begin_insert.assert_called_once_with(3, style="regular")
    assert cyclopropane.isChecked()
    assert not benzene.isChecked()
    insert_state = active_canvas_for_window(window).runtime_state.insert_state
    assert insert_state.template_ring_size == 3
    assert insert_state.template_ring_style == "regular"


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
        perspective_button.toggle()

    assert canvas.services.tool_controller.active.name == "perspective"
    assert services.status_service.status_context_texts()["tool"] == "Tool: Perspective"
    emit.assert_called_once_with()
    refresh.assert_called_once_with(window)


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
