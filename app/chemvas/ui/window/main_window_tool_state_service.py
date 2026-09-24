from __future__ import annotations

from chemvas.ui.window.main_window_toolbar_logic import (
    arrow_preset_from_label,
    bond_style_from_label,
    orbital_type_from_label,
    tool_action_key_for_canvas_state,
)


class MainWindowToolStateService:
    """Translate tool choices and reflect the canvas's one completed update.

    CanvasToolModeController owns mode changes and publishes their result. UI
    commands never refresh again after that callback; direct canvas changes and
    tab activation use the same reflection path.
    """

    def __init__(
        self,
        *,
        tool_mode_controller_for_window,
        active_tool_name_for_window,
        tool_action_for_window,
        status_service,
        refresh_context_bar_for_window,
        clear_context_bar_page_override_for_window,
        set_context_bar_page_override_for_window,
    ) -> None:
        self._tool_mode_controller_for_window = tool_mode_controller_for_window
        self._active_tool_name_for_window = active_tool_name_for_window
        self._tool_action_for_window = tool_action_for_window
        self._status = status_service
        self._refresh_context_bar_for_window = refresh_context_bar_for_window
        self._clear_context_bar_page_override_for_window = (
            clear_context_bar_page_override_for_window
        )
        self._set_context_bar_page_override_for_window = (
            set_context_bar_page_override_for_window
        )

    def _tool_mode_controller(self, window):
        return self._tool_mode_controller_for_window(window)

    def set_bond_style(self, window, value: str) -> None:
        style, order = bond_style_from_label(value)
        self._tool_mode_controller(window).set_bond_style(style, order)

    def sync_tool_actions_from_canvas(self, window) -> None:
        self._clear_context_bar_page_override_for_window(window)
        active = self._active_tool_name_for_window(window)
        action_key = tool_action_key_for_canvas_state(active)
        action = (
            self._tool_action_for_window(window, action_key)
            if action_key is not None
            else None
        )
        if action is not None:
            action.setChecked(True)
        self._status.update_tool_status_label(window)
        self._status.show_active_tool_hint(window)
        self._refresh_context_bar_for_window(window)

    def show_context_page(self, window, page_key: str) -> None:
        self._set_context_bar_page_override_for_window(window, page_key)
        action = self._tool_action_for_window(window, page_key)
        if action is not None and action.isCheckable():
            action.setChecked(True)
        self._status.update_tool_status_label(window)
        self._status.show_active_tool_hint(window)
        self._refresh_context_bar_for_window(window)

    def set_tool_with_status(
        self, window, tool: str, reset_bond_style: bool = True
    ) -> None:
        controller = self._tool_mode_controller(window)
        if tool == "mark":
            controller.set_mark_kind("plus")
        elif tool == "bond" and reset_bond_style:
            self.set_bond_style(window, "Single")
        else:
            controller.set_tool(tool)

    def set_mark_kind(self, window, kind: str) -> None:
        self._tool_mode_controller(window).set_mark_kind(kind)

    def set_arrow_type(self, window, kind: str) -> None:
        self._tool_mode_controller(window).set_arrow_type(kind)

    def set_bracket_type(self, window, value: str) -> None:
        self._tool_mode_controller(window).set_bracket_type(value)

    def set_orbital_type(self, window, value: str) -> None:
        self._tool_mode_controller(window).set_orbital_type(
            orbital_type_from_label(value)
        )

    def set_orbital_phase(self, window, value: str) -> None:
        self._tool_mode_controller(window).set_orbital_phase_enabled(
            value == "Phase On"
        )

    def set_shape_type(self, window, value: str) -> None:
        self._tool_mode_controller(window).set_shape_type(value)

    def set_shape_stroke(self, window, value: str) -> None:
        self._tool_mode_controller(window).set_shape_stroke(value)

    def set_line_kind(self, window, value: str) -> None:
        self._tool_mode_controller(window).set_line_kind(value)

    def set_arrow_preset(self, window, value: str) -> None:
        width, head = arrow_preset_from_label(value)
        controller = self._tool_mode_controller(window)
        controller.set_arrow_style(width, head)


__all__ = ["MainWindowToolStateService"]
