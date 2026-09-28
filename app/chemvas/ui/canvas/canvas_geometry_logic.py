from __future__ import annotations

import math
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

Point = tuple[float, float]
"""A scene point as ``(x, y)``."""

Rect = tuple[float, float, float, float]
"""A scene rectangle as ``(left, top, right, bottom)``."""


def line_rect_clip_t(p1: Point, p2: Point, rect: Rect) -> tuple[float, float] | None:
    left, top, right, bottom = rect
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    p = [-dx, dx, -dy, dy]
    q = [
        p1[0] - left,
        right - p1[0],
        p1[1] - top,
        bottom - p1[1],
    ]
    u1 = 0.0
    u2 = 1.0
    for pi, qi in zip(p, q, strict=False):
        if abs(pi) < 1e-9:
            if qi < 0:
                return None
            continue
        t = qi / pi
        if pi < 0:
            u1 = max(u1, t)
        else:
            u2 = min(u2, t)
        if u1 > u2:
            return None
    return u1, u2


def segment_intersection_t(p1: Point, p2: Point, q1: Point, q2: Point) -> float | None:
    r = (p2[0] - p1[0], p2[1] - p1[1])
    s = (q2[0] - q1[0], q2[1] - q1[1])
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) < 1e-8:
        return None
    q_p = (q1[0] - p1[0], q1[1] - p1[1])
    t = (q_p[0] * s[1] - q_p[1] * s[0]) / denom
    u = (q_p[0] * r[1] - q_p[1] * r[0]) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t
    return None


def ray_rect_exit_distance(origin: Point, direction: Point, rect: Rect) -> float | None:
    left, top, right, bottom = rect
    t_min = float("-inf")
    t_max = float("inf")
    for origin_value, direction_value, min_value, max_value in (
        (origin[0], direction[0], left, right),
        (origin[1], direction[1], top, bottom),
    ):
        if abs(direction_value) < 1e-8:
            if origin_value < min_value or origin_value > max_value:
                return None
            continue
        t1 = (min_value - origin_value) / direction_value
        t2 = (max_value - origin_value) / direction_value
        t_near = min(t1, t2)
        t_far = max(t1, t2)
        t_min = max(t_min, t_near)
        t_max = min(t_max, t_far)
        if t_min > t_max:
            return None
    if t_max < 0.0:
        return None
    return max(0.0, t_max)


def glyph_clearance_radius(stroke_width: float) -> float:
    """Native square-cap envelope plus visible air gap and flattening allowance."""
    return stroke_width / math.sqrt(2.0) + max(0.2, stroke_width * 0.5) + 0.01


def glyph_convex_hull(points: Iterable[Point]) -> list[Point]:
    """Native label silhouette, closing counters and gaps between runs."""
    points = sorted(set(points))
    if len(points) < 3:
        return []
    hulls = []
    for ordered in (points, list(reversed(points))):
        half: list[tuple[float, float]] = []
        for point in ordered:
            while len(half) >= 2:
                a, b = half[-2:]
                cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (
                    point[0] - a[0]
                )
                if cross > 0:
                    break
                half.pop()
            half.append(point)
        hulls.extend(half[:-1])
    return hulls


def glyph_contour_clip_t(
    p1: Point,
    p2: Point,
    contours: Iterable[Iterable[Point]],
    offsets: tuple[Point, ...] = (),
    *,
    start_inside: bool = False,
    end_inside: bool = False,
) -> tuple[float, float] | None:
    """Native first/last contour crossings, including the full offset band.

    Adapters provide closed, scene-space contours of the glyph envelope and
    its painted clearance. Containment uses the adapter's filled-path rule.
    A collapsed segment has no visible span and returns None, even inside ink.
    """
    hits = []
    if start_inside:
        hits.append(0.0)
    if end_inside:
        hits.append(1.0)
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if length == 0:
        return None
    ux, uy = (p2[0] - p1[0]) / length, (p2[1] - p1[1]) / length
    along = [ux * x + uy * y for x, y in offsets] or [0.0]
    across = [-uy * x + ux * y for x, y in offsets] or [0.0]
    low, high = min(across), max(across)
    for contour in contours:
        polygon = tuple(contour)
        if offsets:
            # Include ink between parallel strokes, not only on their edges.
            points = [
                (
                    (x - p1[0]) * ux + (y - p1[1]) * uy,
                    -(x - p1[0]) * uy + (y - p1[1]) * ux,
                )
                for x, y in polygon
            ]
            xs = [x for x, y in points if low <= y <= high]
            for index in range(len(points) - 1):
                x0, y0 = points[index]
                x1, y1 = points[index + 1]
                if abs(y1 - y0) < 1e-12:
                    continue
                for y in (low, high):
                    ratio = (y - y0) / (y1 - y0)
                    if 0 <= ratio <= 1:
                        xs.append(x0 + ratio * (x1 - x0))
            if xs:
                first = (min(xs) - max(along)) / length
                last = (max(xs) - min(along)) / length
                if first <= 1 and last >= 0:
                    hits.extend((max(0.0, first), min(1.0, last)))
            continue
        # Preserve the native 64x intersection tolerance used for Qt contours.
        scale = 64.0
        start = (p1[0] * scale, p1[1] * scale)
        end = (p2[0] * scale, p2[1] * scale)
        for left, right in pairwise(polygon):
            hit = segment_intersection_t(
                start,
                end,
                (left[0] * scale, left[1] * scale),
                (right[0] * scale, right[1] * scale),
            )
            if hit is not None:
                hits.append(hit)
    return (min(hits), max(hits)) if hits else None


__all__ = [
    "Point",
    "Rect",
    "glyph_clearance_radius",
    "glyph_contour_clip_t",
    "glyph_convex_hull",
    "line_rect_clip_t",
    "ray_rect_exit_distance",
    "segment_intersection_t",
]
