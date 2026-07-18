from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chemvas.features.annotations import DEFAULT_BRACKET_KIND
from chemvas.ui.canvas_state_lookup import ensure_canvas_state


@dataclass(slots=True)
class CanvasToolSettingsState:
    atom_symbol: str = "C"
    active_bond_style: str = "single"
    active_bond_order: int = 1
    snap_angle_step: int = 30
    mark_kind: str = "plus"
    active_arrow_type: str = "reaction"
    active_bracket_type: str = DEFAULT_BRACKET_KIND
    active_orbital_type: str = "s"
    active_shape_type: str = "circle"
    active_shape_stroke: str = "solid"
    orbital_phase_enabled: bool = False
    arrow_line_width: float = 1.0
    arrow_head_scale: float = 0.3
    curved_snap: bool = False
    curved_symmetry: bool = False
    curved_snap_step: float = 0.15
    orbital_snap_enabled: bool = False
    orbital_snap_step: int = 15


TOOL_SETTING_ATTRS = (
    "atom_symbol",
    "active_bond_style",
    "active_bond_order",
    "snap_angle_step",
    "mark_kind",
    "active_arrow_type",
    "active_bracket_type",
    "active_orbital_type",
    "active_shape_type",
    "active_shape_stroke",
    "orbital_phase_enabled",
    "arrow_line_width",
    "arrow_head_scale",
)


def tool_settings_state_for(canvas: Any) -> CanvasToolSettingsState:
    return ensure_canvas_state(canvas, "tool_settings_state", CanvasToolSettingsState)


def set_tool_setting_for(canvas: Any, name: str, value: Any) -> None:
    state = tool_settings_state_for(canvas)
    setattr(state, name, value)


__all__ = ["CanvasToolSettingsState", "set_tool_setting_for", "tool_settings_state_for"]
