from __future__ import annotations

from chemvas.features.selection import (
    clamp_curved_midpoint as clamp_curved_midpoint_helper,
)
from chemvas.features.selection import (
    control_from_midpoint as control_from_midpoint_helper,
)
from chemvas.features.selection import (
    curved_midpoint as curved_midpoint_helper,
)
from chemvas.features.selection import (
    default_curved_control as default_curved_control_helper,
)
from chemvas.ui.canvas_service_ports import (
    curved_arrow_path_service_for_access,
    handle_mutation_service_for_access,
)
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.renderer_style_access import bond_length_px_for


def orbital_snap_enabled_for(canvas) -> bool:
    return tool_settings_state_for(canvas).orbital_snap_enabled


def orbital_snap_step_for(canvas) -> int:
    return tool_settings_state_for(canvas).orbital_snap_step


def curved_snap_enabled_for(canvas) -> bool:
    return tool_settings_state_for(canvas).curved_snap


def curved_snap_distance_for(canvas) -> float:
    step = tool_settings_state_for(canvas).curved_snap_step
    return bond_length_px_for(canvas) * step


def update_orbital_scale_for(canvas, item, pos) -> None:
    handle_mutation_service_for_access(canvas).update_orbital_scale(item, pos)


def update_orbital_rotate_for(canvas, item, pos) -> None:
    handle_mutation_service_for_access(canvas).update_orbital_rotate(item, pos)


def update_curved_control_for(canvas, item, pos) -> None:
    handle_mutation_service_for_access(canvas).update_curved_control(item, pos)


def update_curved_endpoint_for(canvas, item, pos, endpoint: str) -> None:
    handle_mutation_service_for_access(canvas).update_curved_endpoint(
        item, pos, endpoint
    )


def set_curved_arrow_path_for(canvas, item, start, end, control, double: bool) -> None:
    curved_arrow_path_service_for_access(canvas).set_curved_arrow_path(
        item, start, end, control, double
    )


def default_curved_control_for(canvas, start, end):
    return default_curved_control_helper(start, end)


def curved_midpoint_for(canvas, start, control, end):
    return curved_midpoint_helper(start, control, end)


def control_from_midpoint_for(canvas, start, end, mid):
    return control_from_midpoint_helper(start, end, mid)


def clamp_curved_midpoint_for(canvas, start, end, mid):
    state = tool_settings_state_for(canvas)
    snap_enabled = state.curved_snap
    snap_distance = None
    if snap_enabled:
        step = state.curved_snap_step
        snap_distance = bond_length_px_for(canvas) * step
    return clamp_curved_midpoint_helper(
        start,
        end,
        mid,
        snap_enabled=snap_enabled,
        snap_distance=snap_distance,
    )


__all__ = [
    "clamp_curved_midpoint_for",
    "control_from_midpoint_for",
    "curved_midpoint_for",
    "curved_snap_distance_for",
    "curved_snap_enabled_for",
    "default_curved_control_for",
    "orbital_snap_enabled_for",
    "orbital_snap_step_for",
    "set_curved_arrow_path_for",
    "update_curved_control_for",
    "update_curved_endpoint_for",
    "update_orbital_rotate_for",
    "update_orbital_scale_for",
]
