from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from chemvas.features.annotations import DEFAULT_BRACKET_KIND

GRID_MODES: tuple[Literal["none", "hex", "square"], ...] = ("none", "hex", "square")
GRID_STRENGTHS = (15, 20, 25)
# Below this on-screen spacing the grid reads as a grey wash rather than as a
# guide, so it is left unpainted while the snapping itself keeps working.
MIN_GRID_SPACING_PX = 6.0
GRID_COLOR = "#8c8c87"
GRID_CONTROL_HINT = (
    "Cycle grid and arrow/line snapping; open the menu for grid strength"
)


@dataclass(slots=True, kw_only=True)
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
    active_line_kind: str = "line"
    orbital_phase_enabled: bool = False
    arrow_line_width: float = 1.0
    arrow_head_scale: float = 0.3
    curved_snap: bool = False
    curved_snap_step: float = 0.15
    orbital_snap_enabled: bool = False
    orbital_snap_step: int = 15
    grid_snap_enabled: bool = False
    grid_snap_step: float = 0.5
    grid_style: Literal["square", "hex"] = "square"
    grid_opacity: float = 0.20
    valence_checking: bool = True


def grid_step_for(canvas) -> float:
    """Grid spacing in scene units, so the grid scales with the bond length."""
    return (
        canvas.renderer.style.bond_length_px
        * canvas.runtime_state.tool_settings_state.grid_snap_step
    )


def normalized_arrow_style(width: float, head_scale: float) -> dict[str, float]:
    return {
        "arrow_line_width": max(0.5, float(width)),
        "arrow_head_scale": max(0.1, min(0.8, head_scale)),
    }


def set_tool_setting_for(canvas: Any, name: str, value: Any) -> None:
    state = canvas.runtime_state.tool_settings_state
    setattr(state, name, value)


__all__ = ["CanvasToolSettingsState", "normalized_arrow_style", "set_tool_setting_for"]
