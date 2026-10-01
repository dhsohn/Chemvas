from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

from chemvas.domain.document import VALID_ARROW_KINDS
from chemvas.features.rendering import (
    ENDPOINT_SNAP_SCREEN_PX,
    SNAP_MARK_SCREEN_PX,
    nearest_endpoint,
    points_on_endpoints,
    snapped_drawing_point,
)
from chemvas.ui.canvas.canvas_tool_settings_state import grid_step_for


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
    for item in canvas.runtime_state.arrow_items():
        if item is exclude:
            # Dragging an endpoint must not snap to the item's own ends.
            continue
        record = canvas.render_context.arrows.record(item)
        points.extend((record.start, record.end))
    return points


def snapped_points_among_for(canvas, points, *, exclude=None):
    """The ``points`` that are sitting exactly on an existing endpoint."""
    caught = points_on_endpoints(
        [(point.x(), point.y()) for point in points if point is not None],
        arrow_endpoints_for(canvas, exclude=exclude),
    )
    return [QPointF(*point) for point in caught]


def _item_endpoints(canvas, item) -> list[QPointF]:
    if item.data(0) not in VALID_ARROW_KINDS:
        return []
    record = canvas.render_context.arrows.record(item)
    return [QPointF(*record.start), QPointF(*record.end)]


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
        for item in canvas.runtime_state.arrow_items()
        if id(item) not in moving_ids
        for point in _item_endpoints(canvas, item)
    ]
    if not targets:
        return None
    radius = endpoint_snap_radius_for(canvas)
    best: tuple[float, QPointF, QPointF] | None = None
    for item in moving:
        for point in _item_endpoints(canvas, item):
            found = nearest_endpoint((point.x(), point.y()), targets, radius=radius)
            if found is None:
                continue
            shift = QPointF(found[0] - point.x(), found[1] - point.y())
            distance = math.hypot(shift.x(), shift.y())
            if best is None or distance < best[0]:
                best = (distance, shift, QPointF(*found))
    return None if best is None else (best[1], best[2])


def snap_drawing_point_for(
    canvas, pos: QPointF, *, exclude=None, avoid=None, angle_step=None
):
    """Where a drawing gesture should put ``pos``.

    An endpoint is the more specific target, so it wins; the grid catches
    everything else, and with both off the point passes through unchanged.
    """
    settings = canvas.runtime_state.tool_settings_state
    endpoints = arrow_endpoints_for(canvas, exclude=exclude)
    return QPointF(
        *snapped_drawing_point(
            (pos.x(), pos.y()),
            endpoints,
            radius=endpoint_snap_radius_for(canvas) if endpoints else 0.0,
            avoid=None if avoid is None else (avoid.x(), avoid.y()),
            angle_step=angle_step,
            grid_step=grid_step_for(canvas) if settings.grid_snap_enabled else 0.0,
            grid_style=settings.grid_style,
        )
    )


__all__ = [
    "SNAP_MARK_SCREEN_PX",
    "arrow_endpoints_for",
    "connection_for",
    "endpoint_snap_radius_for",
    "scene_length_for_screen_px",
    "snap_drawing_point_for",
    "snapped_points_among_for",
]
