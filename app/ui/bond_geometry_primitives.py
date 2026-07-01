from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

LineSegment = tuple[float, float, float, float]
DEFAULT_BOLD_OUT_LENGTH_SCALE = 1.1


def normalize_3d(dx: float, dy: float, dz: float) -> tuple[float, float, float] | None:
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 1e-9:
        return None
    return (dx / length, dy / length, dz / length)


def scale_segment(x1: float, y1: float, x2: float, y2: float, scale: float) -> LineSegment:
    if scale <= 1.0 + 1e-6:
        return x1, y1, x2, y2
    dx = x2 - x1
    dy = y2 - y1
    extend = (scale - 1.0) * 0.5
    return (
        x1 - dx * extend,
        y1 - dy * extend,
        x2 + dx * extend,
        y2 + dy * extend,
    )


def extend_segment(x1: float, y1: float, x2: float, y2: float, extend: float) -> LineSegment:
    if extend <= 1e-6:
        return x1, y1, x2, y2
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy) or 1.0
    factor = extend / length
    return (
        x1 - dx * factor,
        y1 - dy * factor,
        x2 + dx * factor,
        y2 + dy * factor,
    )


def offset_segment(segment: LineSegment, nx: float, ny: float, offset: float) -> LineSegment:
    x1, y1, x2, y2 = segment
    ox = nx * offset
    oy = ny * offset
    return (x1 + ox, y1 + oy, x2 + ox, y2 + oy)


def trim_segment(segment: LineSegment, trim: float) -> LineSegment:
    if trim <= 1e-6:
        return segment
    x1, y1, x2, y2 = segment
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy) or 1.0
    ratio = min(0.45, trim / length)
    return (
        x1 + dx * ratio,
        y1 + dy * ratio,
        x2 - dx * ratio,
        y2 - dy * ratio,
    )


def line_intersection(
    px: float,
    py: float,
    dx: float,
    dy: float,
    qx: float,
    qy: float,
    ex: float,
    ey: float,
) -> tuple[float, float] | None:
    """Intersection of infinite lines ``(px,py)+t*(dx,dy)`` and ``(qx,qy)+s*(ex,ey)``.

    Returns ``None`` when the directions are parallel (no unique crossing).
    """
    denom = dx * ey - dy * ex
    if abs(denom) < 1e-9:
        return None
    t = ((qx - px) * ey - (qy - py) * ex) / denom
    return (px + dx * t, py + dy * t)


def strip_polygon(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    nx: float,
    ny: float,
    base_width: float,
    bold_width: float,
) -> QPolygonF:
    half_base = base_width / 2.0
    inner_offset = half_base + max(0.0, bold_width - base_width)
    outer_offset = -half_base
    return QPolygonF(
        [
            QPointF(x1 + nx * outer_offset, y1 + ny * outer_offset),
            QPointF(x2 + nx * outer_offset, y2 + ny * outer_offset),
            QPointF(x2 + nx * inner_offset, y2 + ny * inner_offset),
            QPointF(x1 + nx * inner_offset, y1 + ny * inner_offset),
        ]
    )


def bold_out_scale(
    bold_outward: bool,
    ring_center,
    *,
    length_scale: float = DEFAULT_BOLD_OUT_LENGTH_SCALE,
) -> float:
    if bold_outward and ring_center is not None:
        return length_scale
    return 1.0


__all__ = [
    "DEFAULT_BOLD_OUT_LENGTH_SCALE",
    "LineSegment",
    "bold_out_scale",
    "extend_segment",
    "line_intersection",
    "normalize_3d",
    "offset_segment",
    "scale_segment",
    "strip_polygon",
    "trim_segment",
]
