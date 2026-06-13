from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.main_window_context_bar_service import MainWindowContextBarService


def _context_bar_service(
    *,
    page_builder=None,
    active_tool_name_for_window=None,
    active_canvas_or_none_for_window=None,
    context_bar_page_override_for_window=None,
) -> MainWindowContextBarService:
    return MainWindowContextBarService(
        page_builder=page_builder or object(),
        active_tool_name_for_window=active_tool_name_for_window or mock.Mock(return_value=None),
        active_canvas_or_none_for_window=active_canvas_or_none_for_window or mock.Mock(return_value=None),
        context_bar_page_override_for_window=context_bar_page_override_for_window or mock.Mock(return_value=None),
    )


def test_active_tool_name_uses_injected_window_port() -> None:
    active_tool_name_for_window = mock.Mock(return_value="arrow")
    service = _context_bar_service(
        active_tool_name_for_window=active_tool_name_for_window,
    )
    window = object()

    assert service.active_tool_name(window) == "arrow"
    active_tool_name_for_window.assert_called_once_with(window)


def test_refresh_window_uses_injected_active_tool_name() -> None:
    active_tool_name_for_window = mock.Mock(return_value="bond")
    context_bar_page_override_for_window = mock.Mock(return_value="ring_fill")
    service = _context_bar_service(
        active_tool_name_for_window=active_tool_name_for_window,
        context_bar_page_override_for_window=context_bar_page_override_for_window,
    )
    service.refresh = mock.Mock()
    window = SimpleNamespace()

    service.refresh_window(window)

    active_tool_name_for_window.assert_called_once_with(window)
    context_bar_page_override_for_window.assert_called_once_with(window)
    service.refresh.assert_called_once_with(window, "bond", page_key="ring_fill")
