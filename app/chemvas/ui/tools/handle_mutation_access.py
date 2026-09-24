from __future__ import annotations

from chemvas.ui.selection.selection_handles import (
    clamp_curved_midpoint as clamp_curved_midpoint_helper,
)
from chemvas.ui.selection.selection_handles import (
    control_from_midpoint as control_from_midpoint_helper,
)
from chemvas.ui.selection.selection_handles import (
    curved_midpoint as curved_midpoint_helper,
)
from chemvas.ui.selection.selection_handles import (
    default_curved_control as default_curved_control_helper,
)


def curved_snap_distance_for(canvas) -> float:
    step = canvas.runtime_state.tool_settings_state.curved_snap_step
    return canvas.renderer.style.bond_length_px * step


def default_curved_control_for(canvas, start, end):
    return default_curved_control_helper(start, end)


def curved_midpoint_for(canvas, start, control, end):
    return curved_midpoint_helper(start, control, end)


def control_from_midpoint_for(canvas, start, end, mid):
    return control_from_midpoint_helper(start, end, mid)


def clamp_curved_midpoint_for(canvas, start, end, mid):
    state = canvas.runtime_state.tool_settings_state
    snap_enabled = state.curved_snap
    snap_distance = None
    if snap_enabled:
        step = state.curved_snap_step
        snap_distance = canvas.renderer.style.bond_length_px * step
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
    "default_curved_control_for",
]
