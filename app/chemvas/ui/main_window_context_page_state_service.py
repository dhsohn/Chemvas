from __future__ import annotations


class MainWindowContextPageStateService:
    def __init__(
        self,
        *,
        tool_state_service,
        status_service,
        context_bar_service,
        clear_context_bar_page_override_for_window,
        set_context_bar_page_override_for_window,
        tool_action_for_window,
    ) -> None:
        self._tool_state = tool_state_service
        self._status = status_service
        self._context_bar = context_bar_service
        self._clear_context_bar_page_override_for_window = (
            clear_context_bar_page_override_for_window
        )
        self._set_context_bar_page_override_for_window = (
            set_context_bar_page_override_for_window
        )
        self._tool_action_for_window = tool_action_for_window

    def sync_tool_actions_from_canvas(self, window) -> None:
        self._clear_context_bar_page_override_for_window(window)
        self._tool_state.sync_tool_actions_from_canvas(window)
        self._status.update_tool_status_label(window)
        self._context_bar.refresh_window(window)

    def set_tool_with_status(
        self, window, tool: str, *, reset_bond_style: bool = True
    ) -> None:
        self._clear_context_bar_page_override_for_window(window)
        self._tool_state.set_tool_with_status(
            window,
            tool,
            reset_bond_style=reset_bond_style,
        )
        self._context_bar.refresh_window(window)

    def show_context_page(self, window, page_key: str) -> None:
        self._set_context_bar_page_override_for_window(window, page_key)
        action = self._tool_action_for_window(window, page_key)
        if action is not None:
            action.setChecked(True)
        self._context_bar.refresh_window(window)


__all__ = ["MainWindowContextPageStateService"]
