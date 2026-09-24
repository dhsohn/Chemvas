from __future__ import annotations

from chemvas.ui.selection.selection_handles import (
    clamp_curved_midpoint as clamp_curved_midpoint_helper,
)


def curved_snap_distance_for(canvas) -> float:
    step = canvas.runtime_state.tool_settings_state.curved_snap_step
    return canvas.renderer.style.bond_length_px * step


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
    "curved_snap_distance_for",
]
