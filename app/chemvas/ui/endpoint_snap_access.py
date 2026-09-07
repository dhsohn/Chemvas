from __future__ import annotations

from PyQt6.QtCore import QPointF

from chemvas.features.rendering import (
    nearest_endpoint,
    snapped_endpoint,
    snapped_to_grid,
)
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.renderer_style_access import bond_length_px_for

# Endpoints closer than this fraction of a bond length snap together, so a
# dashed connector meets an energy level exactly and cycle arcs share corners.
ENDPOINT_SNAP_FRACTION = 0.4


def arrow_endpoints_for(canvas, *, exclude=None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for item in arrow_items_for(canvas):
        if item is exclude:
            # Dragging an endpoint must not snap to the item's own ends.
            continue
        data = item.data(2) or {}
        for key in ("start", "end"):
            point = data.get(key)
            if isinstance(point, QPointF):
                points.append((point.x(), point.y()))
    return points


def snap_to_arrow_endpoints_for(canvas, pos: QPointF, *, exclude=None) -> QPointF:
    candidates = arrow_endpoints_for(canvas, exclude=exclude)
    if not candidates:
        return pos
    x, y = snapped_endpoint(
        (pos.x(), pos.y()),
        candidates,
        radius=bond_length_px_for(canvas) * ENDPOINT_SNAP_FRACTION,
    )
    return QPointF(x, y)


def grid_snap_enabled_for(canvas) -> bool:
    return tool_settings_state_for(canvas).grid_snap_enabled


def set_grid_snap_enabled_for(canvas, enabled: bool) -> None:
    tool_settings_state_for(canvas).grid_snap_enabled = bool(enabled)


def grid_step_for(canvas) -> float:
    """Grid spacing in scene units, so the grid scales with the bond length."""
    return bond_length_px_for(canvas) * tool_settings_state_for(canvas).grid_snap_step


def snap_to_endpoint_for(canvas, pos: QPointF, *, exclude=None, avoid=None):
    """The endpoint ``pos`` should take, or ``None`` when none applies.

    ``avoid`` names a point the result must not be, so a gesture cannot be
    collapsed onto the end it started from.
    """
    candidates = arrow_endpoints_for(canvas, exclude=exclude)
    if not candidates:
        return None
    found = nearest_endpoint(
        (pos.x(), pos.y()),
        candidates,
        radius=bond_length_px_for(canvas) * ENDPOINT_SNAP_FRACTION,
    )
    if found is None:
        return None
    point = QPointF(*found)
    return None if point == avoid else point


def snap_to_grid_for(canvas, pos: QPointF) -> QPointF:
    """``pos`` on the grid, or unchanged when the grid is off."""
    if not grid_snap_enabled_for(canvas):
        return pos
    x, y = snapped_to_grid((pos.x(), pos.y()), step=grid_step_for(canvas))
    return QPointF(x, y)


def snap_drawing_point_for(canvas, pos: QPointF, *, exclude=None, avoid=None):
    """Where a drawing gesture should put ``pos``.

    An endpoint is the more specific target, so it wins; the grid catches
    everything else, and with both off the point passes through unchanged.
    """
    endpoint = snap_to_endpoint_for(canvas, pos, exclude=exclude, avoid=avoid)
    return endpoint if endpoint is not None else snap_to_grid_for(canvas, pos)


__all__ = [
    "ENDPOINT_SNAP_FRACTION",
    "arrow_endpoints_for",
    "grid_snap_enabled_for",
    "grid_step_for",
    "set_grid_snap_enabled_for",
    "snap_drawing_point_for",
    "snap_to_arrow_endpoints_for",
    "snap_to_endpoint_for",
    "snap_to_grid_for",
]
