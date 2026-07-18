from __future__ import annotations

from chemvas.ui.main_window_toolbar_logic import (
    arrow_preset_from_label,
    arrow_type_from_label,
    bond_style_from_label,
    orbital_type_from_label,
    tool_action_key_for_canvas_state,
)


class MainWindowToolStateService:
    def __init__(
        self,
        *,
        tool_mode_controller_for_window,
        active_tool_name_for_window,
        tool_settings_for_window,
        tool_actions_for_window,
        tool_action_for_window,
        status_service,
    ) -> None:
        self._tool_mode_controller_for_window = tool_mode_controller_for_window
        self._active_tool_name_for_window = active_tool_name_for_window
        self._tool_settings_for_window = tool_settings_for_window
        self._tool_actions_for_window = tool_actions_for_window
        self._tool_action_for_window = tool_action_for_window
        self._status = status_service

    def _tool_mode_controller(self, window):
        return self._tool_mode_controller_for_window(window)

    def set_bond_style(self, window, value: str) -> None:
        style, order = bond_style_from_label(value)
        self._tool_mode_controller(window).set_bond_style(style, order)

    def sync_tool_actions_from_canvas(self, window) -> None:
        if not self._tool_actions_for_window(window):
            return
        active = self._active_tool_name_for_window(window)
        settings = self._tool_settings_for_window(window)
        action_key = tool_action_key_for_canvas_state(
            active,
            active_bond_style=settings.active_bond_style,
            mark_kind=settings.mark_kind,
        )
        action = (
            self._tool_action_for_window(window, action_key)
            if action_key is not None
            else None
        )
        if action is not None:
            action.setChecked(True)

    def set_tool_with_status(
        self, window, tool: str, reset_bond_style: bool = True
    ) -> None:
        controller = self._tool_mode_controller(window)
        if tool == "mark":
            controller.set_mark_kind("plus")
        else:
            controller.set_tool(tool)
        if tool == "bond" and reset_bond_style:
            self.set_bond_style(window, "Single")
        self._status.refresh_status_context(window)

    def set_mark_kind(self, window, kind: str) -> None:
        self._tool_mode_controller(window).set_mark_kind(kind)
        self._status.refresh_status_context(window)

    def set_arrow_type(self, window, value: str) -> None:
        self._tool_mode_controller(window).set_arrow_type(arrow_type_from_label(value))

    def set_bracket_type(self, window, value: str) -> None:
        self._tool_mode_controller(window).set_bracket_type(value)
        self._status.refresh_status_context(window)

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
        self._status.refresh_status_context(window)

    def set_shape_stroke(self, window, value: str) -> None:
        self._tool_mode_controller(window).set_shape_stroke(value)
        self._status.refresh_status_context(window)

    def set_arrow_preset(self, window, value: str) -> None:
        width, head = arrow_preset_from_label(value)
        controller = self._tool_mode_controller(window)
        controller.set_arrow_line_width(width)
        controller.set_arrow_head_scale(head)


__all__ = ["MainWindowToolStateService"]
