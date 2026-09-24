from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.window.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)


@pytest.fixture
def window(qt_application):
    window = build_main_window()
    yield window
    services = services_for_window(window)
    for canvas in window.tab_references.all_canvases():
        services.canvas_document_service.mark_clean(canvas)
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("key", ["bond", "select", "mark", "arrow", "bond_hash"])
def test_toolbar_choice_publishes_one_complete_tool_update(window, key):
    services = services_for_window(window)
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
    settings = tool_settings_state_for(canvas)
    if key == "bond":
        assert (settings.active_bond_style, settings.active_bond_order) == ("single", 1)
    elif key == "bond_hash":
        assert (settings.active_bond_style, settings.active_bond_order) == ("hash", 1)
    assert window.statusBar().currentMessage()


def test_ring_fill_override_is_cleared_by_direct_canvas_tool_change(window):
    services = services_for_window(window)
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
