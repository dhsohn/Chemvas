from __future__ import annotations

import math
from typing import Any

from .bond_style import DOUBLE_STYLE_OUTER

LineSegment = tuple[float, float, float, float]
Point2D = tuple[float, float]


def normalize_3d(dx: float, dy: float, dz: float) -> tuple[float, float, float] | None:
    """Unit vector of ``(dx, dy, dz)``, or ``None`` for a degenerate length.

    Bond geometry owns it so this module stays free of Qt: the selection
    package imports it from here, and nothing here imports selection.
    """
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 1e-9:
        return None
    return (dx / length, dy / length, dz / length)


def offset_segment(
    segment: LineSegment, nx: float, ny: float, offset: float
) -> LineSegment:
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


def normal_away_from_parallel_segment(
    segment: LineSegment,
    other: LineSegment,
    nx: float,
    ny: float,
) -> tuple[float, float]:
    """Orient a strip normal away from the other line of a multiple bond."""
    segment_mid_x = (segment[0] + segment[2]) * 0.5
    segment_mid_y = (segment[1] + segment[3]) * 0.5
    other_mid_x = (other[0] + other[2]) * 0.5
    other_mid_y = (other[1] + other[3]) * 0.5
    toward_other = (other_mid_x - segment_mid_x) * nx + (
        other_mid_y - segment_mid_y
    ) * ny
    if toward_other >= 0.0:
        return -nx, -ny
    return nx, ny


def bold_double_strip_geometry(
    outer_segment: LineSegment,
    inner_segment: LineSegment,
    normal: tuple[float, float],
    *,
    is_ring: bool,
    position_style: str,
) -> tuple[int, LineSegment, LineSegment, tuple[float, float]]:
    """Choose the bold line and its one-sided strip normal for a double bond."""
    segments = (outer_segment, inner_segment)
    # Ring Outward makes the inward segment full length. Keep the bold
    # primitive in slot zero while assigning it that second segment so ring
    # attach/removal never has to replace or reorder scene items.
    bold_index = 1 if is_ring and position_style == DOUBLE_STYLE_OUTER else 0
    bold_segment = segments[bold_index]
    other_segment = segments[1 - bold_index]
    if is_ring and bold_index == 0:
        # Ring normals point at the centre. Inward thickening matches bold
        # singles and lets neighboring strips meet at one sharp mitre.
        bold_normal = normal
    else:
        bold_normal = normal_away_from_parallel_segment(
            bold_segment,
            other_segment,
            *normal,
        )
    return bold_index, bold_segment, other_segment, bold_normal


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


def strip_corners(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    nx: float,
    ny: float,
    base_width: float,
    bold_width: float,
) -> tuple[Point2D, Point2D, Point2D, Point2D]:
    half_base = base_width / 2.0
    inner_offset = half_base + max(0.0, bold_width - base_width)
    outer_offset = -half_base
    return (
        (x1 + nx * outer_offset, y1 + ny * outer_offset),
        (x2 + nx * outer_offset, y2 + ny * outer_offset),
        (x2 + nx * inner_offset, y2 + ny * inner_offset),
        (x1 + nx * inner_offset, y1 + ny * inner_offset),
    )


def line_normal(
    x1: float, y1: float, x2: float, y2: float, target: Any = None
) -> tuple[float, float]:
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 0.0
    nx, ny = -dy / length, dx / length
    if (
        target is not None
        and nx * (target.x() - (x1 + x2) * 0.5) + ny * (target.y() - (y1 + y2) * 0.5)
        < 0
    ):
        return -nx, -ny
    return nx, ny


__all__ = [
    "LineSegment",
    "bold_double_strip_geometry",
    "line_intersection",
    "line_normal",
    "normal_away_from_parallel_segment",
    "normalize_3d",
    "offset_segment",
    "strip_corners",
    "trim_segment",
]
