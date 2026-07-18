from types import SimpleNamespace
from unittest import mock

from chemvas.ui.main_window_context_page_state_service import (
    MainWindowContextPageStateService,
)


def _make_service():
    tool_state_service = mock.Mock()
    status_service = mock.Mock()
    context_bar_service = mock.Mock()
    clear_context_bar_page_override_for_window = mock.Mock()
    set_context_bar_page_override_for_window = mock.Mock()
    tool_action_for_window = mock.Mock()
    service = MainWindowContextPageStateService(
        tool_state_service=tool_state_service,
        status_service=status_service,
        context_bar_service=context_bar_service,
        clear_context_bar_page_override_for_window=clear_context_bar_page_override_for_window,
        set_context_bar_page_override_for_window=set_context_bar_page_override_for_window,
        tool_action_for_window=tool_action_for_window,
    )
    return (
        service,
        tool_state_service,
        status_service,
        context_bar_service,
        clear_context_bar_page_override_for_window,
        set_context_bar_page_override_for_window,
        tool_action_for_window,
    )


def test_sync_tool_actions_clears_override_and_refreshes_tool_context() -> None:
    (
        service,
        tool_state_service,
        status_service,
        context_bar_service,
        clear_context_bar_page_override_for_window,
        _set_context_bar_page_override_for_window,
        _tool_action_for_window,
    ) = _make_service()
    window = SimpleNamespace()

    service.sync_tool_actions_from_canvas(window)

    clear_context_bar_page_override_for_window.assert_called_once_with(window)
    tool_state_service.sync_tool_actions_from_canvas.assert_called_once_with(window)
    status_service.update_tool_status_label.assert_called_once_with(window)
    context_bar_service.refresh_window.assert_called_once_with(window)


def test_set_tool_with_status_clears_override_and_refreshes_context_bar() -> None:
    (
        service,
        tool_state_service,
        status_service,
        context_bar_service,
        clear_context_bar_page_override_for_window,
        _set_context_bar_page_override_for_window,
        _tool_action_for_window,
    ) = _make_service()
    window = SimpleNamespace()

    service.set_tool_with_status(window, "bond", reset_bond_style=False)

    clear_context_bar_page_override_for_window.assert_called_once_with(window)
    tool_state_service.set_tool_with_status.assert_called_once_with(
        window,
        "bond",
        reset_bond_style=False,
    )
    status_service.update_tool_status_label.assert_not_called()
    context_bar_service.refresh_window.assert_called_once_with(window)


def test_show_context_page_sets_override_checks_action_and_refreshes() -> None:
    (
        service,
        _tool_state_service,
        _status_service,
        context_bar_service,
        _clear_context_bar_page_override_for_window,
        set_context_bar_page_override_for_window,
        tool_action_for_window,
    ) = _make_service()
    action = mock.Mock()
    tool_action_for_window.return_value = action
    window = SimpleNamespace()

    service.show_context_page(window, "ring_fill")

    set_context_bar_page_override_for_window.assert_called_once_with(
        window, "ring_fill"
    )
    tool_action_for_window.assert_called_once_with(window, "ring_fill")
    action.setChecked.assert_called_once_with(True)
    context_bar_service.refresh_window.assert_called_once_with(window)


def test_show_context_page_allows_missing_action() -> None:
    (
        service,
        _tool_state_service,
        _status_service,
        context_bar_service,
        _clear_context_bar_page_override_for_window,
        set_context_bar_page_override_for_window,
        tool_action_for_window,
    ) = _make_service()
    tool_action_for_window.return_value = None
    window = SimpleNamespace()

    service.show_context_page(window, "ring_fill")

    set_context_bar_page_override_for_window.assert_called_once_with(
        window, "ring_fill"
    )
    context_bar_service.refresh_window.assert_called_once_with(window)
