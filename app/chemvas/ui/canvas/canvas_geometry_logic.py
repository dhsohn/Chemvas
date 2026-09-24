from __future__ import annotations

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


def line_rect_intersections(p1: Point, p2: Point, rect: Rect) -> list[float]:
    left, top, right, bottom = rect
    top_left = (left, top)
    top_right = (right, top)
    bottom_right = (right, bottom)
    bottom_left = (left, bottom)
    edges = [
        (top_left, top_right),
        (top_right, bottom_right),
        (bottom_right, bottom_left),
        (bottom_left, top_left),
    ]
    hits = []
    for edge_start, edge_end in edges:
        t = segment_intersection_t(p1, p2, edge_start, edge_end)
        if t is not None:
            hits.append(t)
    return hits


__all__ = [
    "Point",
    "Rect",
    "line_rect_clip_t",
    "line_rect_intersections",
    "ray_rect_exit_distance",
    "segment_intersection_t",
]
