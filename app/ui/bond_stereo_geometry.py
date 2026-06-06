from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

LineSegment = tuple[float, float, float, float]


def trimmed_line_segment(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    t0: float,
    t1: float,
) -> LineSegment:
    dx = x2 - x1
    dy = y2 - y1
    return (
        x1 + dx * t0,
        y1 + dy * t0,
        x1 + dx * t1,
        y1 + dy * t1,
    )


def wedge_polygon_from_segment(segment: LineSegment, *, max_width: float) -> QPolygonF:
    base_x1, base_y1, base_x2, base_y2 = segment
    dx = base_x2 - base_x1
    dy = base_y2 - base_y1
    base_x1 = base_x1 + dx * 0.1
    base_y1 = base_y1 + dy * 0.1
    dx = base_x2 - base_x1
    dy = base_y2 - base_y1
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    half_width = max_width * 0.5 * 0.95
    p1 = QPointF(base_x1, base_y1)
    p2 = QPointF(base_x2 + nx * half_width, base_y2 + ny * half_width)
    p3 = QPointF(base_x2 - nx * half_width, base_y2 - ny * half_width)
    return QPolygonF([p1, p2, p3])


def hash_segments_from_segment(
    segment: LineSegment,
    *,
    count: int,
    max_size: float,
) -> list[LineSegment]:
    base_x1, base_y1, base_x2, base_y2 = segment
    dx = base_x2 - base_x1
    dy = base_y2 - base_y1
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    if count <= 1:
        t_positions = [0.5]
        t_sizes = [1.0]
    else:
        t_positions = [index / (count - 1) for index in range(count)]
        t_sizes = [(index + 1) / (count + 1) for index in range(count)]
    max_t = max(t_sizes) if t_sizes else 1.0
    segments: list[LineSegment] = []
    for t_pos, t_size in zip(t_positions, t_sizes, strict=False):
        cx = base_x1 + dx * t_pos
        cy = base_y1 + dy * t_pos
        size = max_size * (t_size / max_t) if max_t > 0 else max_size
        hx = nx * size / 2.0
        hy = ny * size / 2.0
        segments.append((cx - hx, cy - hy, cx + hx, cy + hy))
    return segments


__all__ = [
    "LineSegment",
    "hash_segments_from_segment",
    "trimmed_line_segment",
    "wedge_polygon_from_segment",
]
