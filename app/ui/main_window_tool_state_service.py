from __future__ import annotations

from ui.main_window_toolbar_logic import (
    arrow_preset_from_label,
    arrow_type_from_label,
    bond_style_from_label,
    orbital_type_from_label,
    tool_action_key_for_canvas_state,
    tool_display_name,
)


class MainWindowToolStateService:
    def set_bond_style(self, window, value: str) -> None:
        style, order = bond_style_from_label(value)
        window.canvas.set_bond_style(style, order)

    def sync_tool_actions_from_canvas(self, window) -> None:
        if not hasattr(window, "_tool_actions"):
            return
        active = window.canvas.tools.active.name if window.canvas.tools.active is not None else None
        action_key = tool_action_key_for_canvas_state(
            active,
            active_bond_style=window.canvas.active_bond_style,
            mark_kind=window.canvas.mark_kind,
        )
        action = window._tool_actions.get(action_key) if action_key is not None else None
        if action is not None:
            action.setChecked(True)

    def set_tool_with_status(self, window, tool: str, reset_bond_style: bool = True) -> None:
        window.canvas.set_tool(tool)
        if tool == "bond" and reset_bond_style:
            self.set_bond_style(window, "Single")
        window.statusBar().showMessage(f"{tool_display_name(tool)} Tool")

    def set_arrow_type(self, window, value: str) -> None:
        window.canvas.set_arrow_type(arrow_type_from_label(value))

    def set_orbital_type(self, window, value: str) -> None:
        window.canvas.set_orbital_type(orbital_type_from_label(value))

    def set_orbital_phase(self, window, value: str) -> None:
        window.canvas.set_orbital_phase_enabled(value == "Phase On")

    def set_arrow_preset(self, window, value: str) -> None:
        width, head = arrow_preset_from_label(value)
        window.canvas.set_arrow_line_width(width)
        window.canvas.set_arrow_head_scale(head)


__all__ = ["MainWindowToolStateService"]
