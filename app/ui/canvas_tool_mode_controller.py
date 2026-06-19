from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ui.canvas_callback_state import callback_state_for
from ui.canvas_insert_state import insert_state_for
from ui.canvas_tool_settings_state import set_tool_setting_for, tool_settings_state_for
from ui.bracket_types import BRACKET_KIND_VALUES
from ui.selection_service_access import refresh_selection_outline_for


class CanvasToolModeController:
    MARK_KINDS = {"plus", "minus", "radical"}

    def __init__(
        self,
        canvas: Any,
        *,
        insert_controller=None,
        hover_refresh: Callable[[], None] | None = None,
        set_active_tool: Callable[[str], None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.insert_controller = insert_controller
        self._hover_refresh = hover_refresh or (lambda: None)
        self._set_active_tool = set_active_tool or (lambda _name: None)

    @property
    def settings(self):
        return tool_settings_state_for(self.canvas)

    def _cancel_active_insert_modes(self) -> None:
        insert_controller = self.insert_controller
        if insert_controller is None:
            return
        insert_state = insert_state_for(self.canvas)
        if insert_state.template_active:
            insert_controller.cancel_template_insert()
        if insert_state.smiles_active:
            insert_controller.cancel_smiles_insert()

    def _emit_tool_changed(self) -> None:
        callback = callback_state_for(self.canvas).tool_change
        if callback is not None:
            callback()

    def _refresh_tool_mode(self) -> None:
        refresh_selection_outline_for(self.canvas)
        self._emit_tool_changed()
        self._hover_refresh()

    def set_tool(self, tool_name: str) -> None:
        self._cancel_active_insert_modes()
        self._set_active_tool(tool_name)
        if tool_name == "benzene" and self.insert_controller is not None:
            self.insert_controller.begin_ring_template_insert(6, "benzene")
        self._refresh_tool_mode()

    def set_mark_kind(self, kind: str) -> None:
        if kind not in self.MARK_KINDS:
            return
        self._cancel_active_insert_modes()
        set_tool_setting_for(self.canvas, "mark_kind", kind)
        self._set_active_tool("mark")
        self._refresh_tool_mode()

    def set_bond_style(self, style: str, order: int) -> None:
        set_tool_setting_for(self.canvas, "active_bond_style", style)
        set_tool_setting_for(self.canvas, "active_bond_order", order)
        self._set_active_tool("bond")
        self._refresh_tool_mode()

    def set_arrow_type(self, arrow_type: str) -> None:
        set_tool_setting_for(self.canvas, "active_arrow_type", arrow_type)
        self._set_active_tool("arrow")
        self._refresh_tool_mode()

    def set_bracket_type(self, bracket_type: str) -> None:
        if bracket_type not in BRACKET_KIND_VALUES:
            return
        self._cancel_active_insert_modes()
        set_tool_setting_for(self.canvas, "active_bracket_type", bracket_type)
        self._set_active_tool("ts_bracket")
        self._refresh_tool_mode()

    def set_orbital_type(self, orbital_type: str) -> None:
        set_tool_setting_for(self.canvas, "active_orbital_type", orbital_type)
        self._set_active_tool("orbital")
        self._refresh_tool_mode()

    def set_orbital_phase_enabled(self, enabled: bool) -> None:
        set_tool_setting_for(self.canvas, "orbital_phase_enabled", enabled)

    def set_arrow_line_width(self, width: float) -> None:
        set_tool_setting_for(self.canvas, "arrow_line_width", max(0.5, float(width)))

    def get_arrow_line_width(self) -> float:
        return self.settings.arrow_line_width

    def set_arrow_head_scale(self, scale: float) -> None:
        set_tool_setting_for(self.canvas, "arrow_head_scale", max(0.1, min(0.8, scale)))

    def get_arrow_head_scale(self) -> float:
        return self.settings.arrow_head_scale

    def set_curved_snap(self, enabled: bool) -> None:
        tool_settings_state_for(self.canvas).curved_snap = bool(enabled)

    def get_curved_snap(self) -> bool:
        return tool_settings_state_for(self.canvas).curved_snap

    def set_curved_snap_step(self, step: float) -> None:
        tool_settings_state_for(self.canvas).curved_snap_step = max(0.05, float(step))

    def get_curved_snap_step(self) -> float:
        return tool_settings_state_for(self.canvas).curved_snap_step

    def set_curved_symmetry(self, enabled: bool) -> None:
        tool_settings_state_for(self.canvas).curved_symmetry = bool(enabled)

    def get_curved_symmetry(self) -> bool:
        return tool_settings_state_for(self.canvas).curved_symmetry

    def set_orbital_snap_enabled(self, enabled: bool) -> None:
        tool_settings_state_for(self.canvas).orbital_snap_enabled = bool(enabled)

    def get_orbital_snap_enabled(self) -> bool:
        return tool_settings_state_for(self.canvas).orbital_snap_enabled

    def set_orbital_snap_step(self, step: int) -> None:
        tool_settings_state_for(self.canvas).orbital_snap_step = max(1, int(step))

    def get_orbital_snap_step(self) -> int:
        return tool_settings_state_for(self.canvas).orbital_snap_step

    def set_atom_symbol(self, symbol: str) -> None:
        set_tool_setting_for(self.canvas, "atom_symbol", symbol.strip())

    def get_atom_symbol(self) -> str:
        return self.settings.atom_symbol

    def set_snap_angle_step(self, step: int) -> None:
        set_tool_setting_for(self.canvas, "snap_angle_step", step)
        self._set_active_tool("bond")
        refresh_selection_outline_for(self.canvas)

__all__ = ["CanvasToolModeController"]
