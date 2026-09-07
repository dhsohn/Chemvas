from __future__ import annotations

from PyQt6.QtCore import QPointF

from chemvas.features.rendering import snapped_endpoint
from chemvas.ui.canvas_scene_items_state import arrow_items_for
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


__all__ = [
    "ENDPOINT_SNAP_FRACTION",
    "arrow_endpoints_for",
    "snap_to_arrow_endpoints_for",
]
