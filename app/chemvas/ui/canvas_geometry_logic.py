from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF


def line_rect_clip_t(
    p1: QPointF, p2: QPointF, rect: QRectF
) -> tuple[float, float] | None:
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    p = [-dx, dx, -dy, dy]
    q = [
        p1.x() - rect.left(),
        rect.right() - p1.x(),
        p1.y() - rect.top(),
        rect.bottom() - p1.y(),
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


def segment_intersection_t(
    p1: QPointF, p2: QPointF, q1: QPointF, q2: QPointF
) -> float | None:
    r = QPointF(p2.x() - p1.x(), p2.y() - p1.y())
    s = QPointF(q2.x() - q1.x(), q2.y() - q1.y())
    denom = r.x() * s.y() - r.y() * s.x()
    if abs(denom) < 1e-8:
        return None
    q_p = QPointF(q1.x() - p1.x(), q1.y() - p1.y())
    t = (q_p.x() * s.y() - q_p.y() * s.x()) / denom
    u = (q_p.x() * r.y() - q_p.y() * r.x()) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t
    return None


def ray_rect_exit_distance(
    origin: QPointF, direction: QPointF, rect: QRectF
) -> float | None:
    t_min = float("-inf")
    t_max = float("inf")
    for origin_value, direction_value, min_value, max_value in (
        (origin.x(), direction.x(), rect.left(), rect.right()),
        (origin.y(), direction.y(), rect.top(), rect.bottom()),
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


def line_rect_intersections(p1: QPointF, p2: QPointF, rect: QRectF) -> list[float]:
    top_left = rect.topLeft()
    top_right = rect.topRight()
    bottom_right = rect.bottomRight()
    bottom_left = rect.bottomLeft()
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
    "line_rect_clip_t",
    "line_rect_intersections",
    "ray_rect_exit_distance",
    "segment_intersection_t",
]
