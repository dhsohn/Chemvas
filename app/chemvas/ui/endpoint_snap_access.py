from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

from chemvas.features.rendering import (
    nearest_endpoint,
    snapped_to_grid,
)
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.renderer_style_access import bond_length_px_for

# Snapping is an input affordance, so its reach is a distance on screen
# rather than in the document: an endpoint this many pixels from the cursor
# is caught, at any zoom. A dashed connector then meets an energy level
# exactly, and cycle arcs share corners, without aiming at a few pixels.
ENDPOINT_SNAP_SCREEN_PX = 12.0
# Diameter of the ring that says an end has been caught. It has to clear
# a bold line's own width to be seen at all.
SNAP_MARK_SCREEN_PX = 16.0


def scene_length_for_screen_px(canvas, pixels: float) -> float:
    """``pixels`` on screen, in scene units at the canvas's current zoom.

    The smaller axis governs, so the reach is at least ``pixels`` in every
    direction when the perspective tool squashes one of them.
    """
    transform = canvas.transform()
    scale = min(abs(transform.m11()), abs(transform.m22())) or 1.0
    return pixels / scale


def endpoint_snap_radius_for(canvas) -> float:
    return scene_length_for_screen_px(canvas, ENDPOINT_SNAP_SCREEN_PX)


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


def snapped_points_among_for(canvas, points, *, exclude=None):
    """The ``points`` that are sitting exactly on an existing endpoint.

    A gesture takes an endpoint by copying it, so equality is the whole
    test; this is what the ring is drawn from, rather than a record of
    which stage of the funnel answered.
    """
    endpoints = set(arrow_endpoints_for(canvas, exclude=exclude))
    return [
        point
        for point in points
        if point is not None and (point.x(), point.y()) in endpoints
    ]


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
        radius=endpoint_snap_radius_for(canvas),
    )
    if found is None:
        return None
    point = QPointF(*found)
    return None if point == avoid else point


def _item_endpoints(item) -> list[QPointF]:
    data = item.data(2) or {}
    return [data[key] for key in ("start", "end") if isinstance(data.get(key), QPointF)]


def connection_for(canvas, items):
    """The shift that joins ``items`` to another end, and where they meet.

    ``None`` when no pair is inside the catch. The smallest shift wins,
    so the pair the drag has come closest to joining is the one that
    joins, and moving several items at once still connects only once.
    """
    moving = [item for item in items if item is not None]
    if not moving:
        return None
    moving_ids = {id(item) for item in moving}
    targets = [
        (point.x(), point.y())
        for item in arrow_items_for(canvas)
        if id(item) not in moving_ids
        for point in _item_endpoints(item)
    ]
    if not targets:
        return None
    radius = endpoint_snap_radius_for(canvas)
    best: tuple[float, QPointF, QPointF] | None = None
    for item in moving:
        for point in _item_endpoints(item):
            found = nearest_endpoint((point.x(), point.y()), targets, radius=radius)
            if found is None:
                continue
            shift = QPointF(found[0] - point.x(), found[1] - point.y())
            distance = math.hypot(shift.x(), shift.y())
            if best is None or distance < best[0]:
                best = (distance, shift, QPointF(*found))
    return None if best is None else (best[1], best[2])


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
    "ENDPOINT_SNAP_SCREEN_PX",
    "SNAP_MARK_SCREEN_PX",
    "arrow_endpoints_for",
    "connection_for",
    "endpoint_snap_radius_for",
    "grid_snap_enabled_for",
    "grid_step_for",
    "scene_length_for_screen_px",
    "set_grid_snap_enabled_for",
    "snap_drawing_point_for",
    "snap_to_endpoint_for",
    "snap_to_grid_for",
    "snapped_points_among_for",
]
