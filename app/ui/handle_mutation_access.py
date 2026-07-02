from __future__ import annotations

from ui.canvas_tool_settings_state import tool_settings_state_for
from ui.handle_interaction_logic import (
    clamp_curved_midpoint as clamp_curved_midpoint_helper,
)
from ui.handle_interaction_logic import (
    control_from_midpoint as control_from_midpoint_helper,
)
from ui.handle_interaction_logic import (
    curved_midpoint as curved_midpoint_helper,
)
from ui.handle_interaction_logic import (
    default_curved_control as default_curved_control_helper,
)
from ui.handle_mutation_ports import (
    curved_arrow_path_service_for_access,
    handle_mutation_service_for_access,
)
from ui.renderer_style_access import bond_length_px_for


def _mutation_service_method(canvas, name: str):
    try:
        service = handle_mutation_service_for_access(canvas)
    except AttributeError:
        return None
    method = getattr(service, name, None)
    return method if callable(method) else None


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
    method = _mutation_service_method(canvas, "update_orbital_scale")
    if method is not None:
        method(item, pos)


def update_orbital_rotate_for(canvas, item, pos) -> None:
    method = _mutation_service_method(canvas, "update_orbital_rotate")
    if method is not None:
        method(item, pos)


def update_curved_control_for(canvas, item, pos) -> None:
    method = _mutation_service_method(canvas, "update_curved_control")
    if method is not None:
        method(item, pos)


def update_curved_endpoint_for(canvas, item, pos, endpoint: str) -> None:
    method = _mutation_service_method(canvas, "update_curved_endpoint")
    if method is not None:
        method(item, pos, endpoint)


def set_curved_arrow_path_for(canvas, item, start, end, control, double: bool) -> None:
    try:
        service = curved_arrow_path_service_for_access(canvas)
    except AttributeError:
        service = None
    method = getattr(service, "set_curved_arrow_path", None)
    if callable(method):
        method(item, start, end, control, double)


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
