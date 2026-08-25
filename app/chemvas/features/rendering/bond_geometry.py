from __future__ import annotations

import math

from .bond_style import DOUBLE_STYLE_OUTER

LineSegment = tuple[float, float, float, float]
Point2D = tuple[float, float]
DEFAULT_BOLD_OUT_LENGTH_SCALE = 1.1


def scale_segment(
    x1: float, y1: float, x2: float, y2: float, scale: float
) -> LineSegment:
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


def extend_segment(
    x1: float, y1: float, x2: float, y2: float, extend: float
) -> LineSegment:
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


def bold_out_scale(
    bold_outward: bool,
    ring_center: object | None,
    *,
    length_scale: float = DEFAULT_BOLD_OUT_LENGTH_SCALE,
) -> float:
    if bold_outward and ring_center is not None:
        return length_scale
    return 1.0


__all__ = [
    "DEFAULT_BOLD_OUT_LENGTH_SCALE",
    "LineSegment",
    "bold_double_strip_geometry",
    "bold_out_scale",
    "extend_segment",
    "line_intersection",
    "normal_away_from_parallel_segment",
    "offset_segment",
    "scale_segment",
    "strip_corners",
    "trim_segment",
]
