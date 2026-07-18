from __future__ import annotations

import math
from collections.abc import Sequence

Point2D = tuple[float, float]


def regular_ring_radius(n: int, bond_length: float) -> float:
    if n < 3:
        return bond_length
    denom = 2.0 * math.sin(math.pi / n)
    if denom <= 1e-6:
        return bond_length
    return bond_length / denom


def ring_points(center: Point2D, n: int, radius: float) -> list[Point2D]:
    cx, cy = center
    points: list[Point2D] = []
    for i in range(n):
        angle = math.radians(360.0 / n * i - 90.0)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        points.append((x, y))
    return points


def scale_points(
    points: Sequence[Point2D], center: Point2D, scale: float
) -> list[Point2D]:
    cx, cy = center
    return [
        (
            cx + (x - cx) * scale,
            cy + (y - cy) * scale,
        )
        for x, y in points
    ]


def scale_points_to_bond_length(
    points: Sequence[Point2D],
    center: Point2D,
    bond_length: float,
) -> list[Point2D]:
    scaled_points = list(points)
    if len(scaled_points) < 2:
        return scaled_points

    x0, y0 = scaled_points[0]
    x1, y1 = scaled_points[1]
    dist = math.hypot(x1 - x0, y1 - y0)
    if dist <= 1e-6:
        return scaled_points

    scale = bond_length / dist
    if abs(scale - 1.0) < 1e-6:
        return scaled_points
    return scale_points(scaled_points, center, scale)


def cyclohexane_chair_points(center: Point2D, bond_length: float) -> list[Point2D]:
    angle_steep = math.radians(-68.0)
    angle_shallow = math.radians(-25.0)
    v1 = (math.cos(angle_steep), math.sin(angle_steep))
    v2 = (math.cos(angle_shallow), math.sin(angle_shallow))

    base_points = [
        (0.0, 0.0),
        (v1[0], v1[1]),
        (v1[0] + 1.0, v1[1]),
        (v1[0] + 1.0 + v2[0], v1[1] + v2[1]),
        (1.0 + v2[0], v2[1]),
        (v2[0], v2[1]),
    ]
    local_points = _center_points_on_bounds(base_points)
    cx, cy = center
    shifted = [
        (
            cx + x * bond_length,
            cy + y * bond_length,
        )
        for x, y in local_points
    ]
    return scale_points_to_bond_length(shifted, center, bond_length)


def cyclohexane_chair_flipped_points(
    center: Point2D, bond_length: float
) -> list[Point2D]:
    """Cyclohexane chair mirrored left-to-right (the other chair orientation)."""
    cx, _ = center
    return [(2.0 * cx - x, y) for x, y in cyclohexane_chair_points(center, bond_length)]


def cyclohexane_boat_points(center: Point2D, bond_length: float) -> list[Point2D]:
    cx, cy = center
    height = bond_length
    bow = height * 0.2
    belly = height * 1.3
    points = [
        (cx - 1.5 * bond_length, cy - bow),
        (cx - 0.5 * bond_length, cy - height),
        (cx + 0.5 * bond_length, cy - height),
        (cx + 1.5 * bond_length, cy - bow),
        (cx + 0.5 * bond_length, cy + belly),
        (cx - 0.5 * bond_length, cy + belly),
    ]
    return scale_points_to_bond_length(points, center, bond_length)


def regular_ring_points_for_atom(
    n: int,
    attach_point: Point2D,
    neighbor_points: Sequence[Point2D],
    bond_length: float,
) -> list[Point2D] | None:
    if n < 3:
        return None
    ax, ay = attach_point
    radius = regular_ring_radius(n, bond_length)
    direction = (0.0, -1.0)
    vectors: list[Point2D] = []
    for x, y in neighbor_points:
        vx = x - ax
        vy = y - ay
        length = math.hypot(vx, vy)
        if length > 1e-6:
            vectors.append((vx / length, vy / length))
    if vectors:
        sx = sum(vx for vx, _ in vectors)
        sy = sum(vy for _, vy in vectors)
        if math.hypot(sx, sy) > 1e-6:
            direction = (-sx, -sy)
        else:
            direction = (-vectors[0][1], vectors[0][0])
    length = math.hypot(*direction) or 1.0
    center = (ax + direction[0] * radius / length, ay + direction[1] * radius / length)
    theta0 = math.atan2(ay - center[1], ax - center[0])
    step = 2.0 * math.pi / n
    return [
        (
            center[0] + radius * math.cos(theta0 + step * index),
            center[1] + radius * math.sin(theta0 + step * index),
        )
        for index in range(n)
    ]


def place_template_on_bond(
    points_local: Sequence[Point2D],
    bond_start: Point2D,
    bond_end: Point2D,
    center_hint: Point2D | None = None,
    occupied_polygon: Sequence[Point2D] | None = None,
) -> list[Point2D] | None:
    if len(points_local) < 2:
        return None
    ax, ay = bond_start
    bx, by = bond_end
    p0x, p0y = points_local[0]
    p1x, p1y = points_local[1]
    local_dx = p1x - p0x
    local_dy = p1y - p0y
    local_len = math.hypot(local_dx, local_dy)
    if local_len <= 1e-6:
        return None
    target_dx = bx - ax
    target_dy = by - ay
    target_len = math.hypot(target_dx, target_dy)
    if target_len <= 1e-6:
        return None
    scale = target_len / local_len
    angle = math.atan2(target_dy, target_dx) - math.atan2(local_dy, local_dx)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    ux = local_dx / local_len
    uy = local_dy / local_len
    vx = -uy
    vy = ux

    def transform(mirror: bool) -> list[Point2D]:
        points: list[Point2D] = []
        for x, y in points_local:
            dx = x - p0x
            dy = y - p0y
            du = dx * ux + dy * uy
            dv = dx * vx + dy * vy
            if mirror:
                dv = -dv
            px = (ux * du + vx * dv) * scale
            py = (uy * du + vy * dv) * scale
            rx = px * cos_a - py * sin_a
            ry = px * sin_a + py * cos_a
            points.append((ax + rx, ay + ry))
        return points

    points_a = transform(False)
    points_b = transform(True)
    center_a = _points_center(points_a)
    center_b = _points_center(points_b)

    if occupied_polygon is not None:
        a_in = _polygon_contains_point(center_a, occupied_polygon)
        b_in = _polygon_contains_point(center_b, occupied_polygon)
        if a_in and not b_in:
            return points_b
        if b_in and not a_in:
            return points_a
        if a_in and b_in:
            return None
    if center_hint is not None and _manhattan_distance(
        center_b, center_hint
    ) < _manhattan_distance(center_a, center_hint):
        return points_b
    return points_a


def regular_ring_points_for_bond(
    n: int,
    bond_start: Point2D,
    bond_end: Point2D,
    center_hint: Point2D | None = None,
    occupied_polygon: Sequence[Point2D] | None = None,
) -> list[Point2D] | None:
    if n < 3:
        return None
    ax, ay = bond_start
    bx, by = bond_end
    dx = bx - ax
    dy = by - ay
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        return None
    radius = length / (2.0 * math.sin(math.pi / n))
    apothem = length / (2.0 * math.tan(math.pi / n))
    mid = ((ax + bx) / 2.0, (ay + by) / 2.0)
    nx = -dy / length
    ny = dx / length
    center_a = (mid[0] + nx * apothem, mid[1] + ny * apothem)
    center_b = (mid[0] - nx * apothem, mid[1] - ny * apothem)
    use_center = center_a
    if occupied_polygon is not None:
        a_in = _polygon_contains_point(center_a, occupied_polygon)
        b_in = _polygon_contains_point(center_b, occupied_polygon)
        if a_in and not b_in:
            use_center = center_b
        elif b_in and not a_in:
            use_center = center_a
        elif a_in and b_in:
            return None
    elif center_hint is not None and _manhattan_distance(
        center_b, center_hint
    ) < _manhattan_distance(center_a, center_hint):
        use_center = center_b

    theta_a = math.atan2(ay - use_center[1], ax - use_center[0])
    step = 2.0 * math.pi / n
    p_forward = (
        use_center[0] + radius * math.cos(theta_a + step),
        use_center[1] + radius * math.sin(theta_a + step),
    )
    p_backward = (
        use_center[0] + radius * math.cos(theta_a - step),
        use_center[1] + radius * math.sin(theta_a - step),
    )
    direction = (
        1.0
        if _distance(p_forward, bond_end) <= _distance(p_backward, bond_end)
        else -1.0
    )
    return [
        (
            use_center[0] + radius * math.cos(theta_a + direction * step * index),
            use_center[1] + radius * math.sin(theta_a + direction * step * index),
        )
        for index in range(n)
    ]


def _center_points_on_bounds(points: Sequence[Point2D]) -> list[Point2D]:
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    return [(x - cx, y - cy) for x, y in points]


def _distance(a: Point2D, b: Point2D) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _manhattan_distance(a: Point2D, b: Point2D) -> float:
    return abs(b[0] - a[0]) + abs(b[1] - a[1])


def _points_center(points: Sequence[Point2D]) -> Point2D:
    return (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )


def _polygon_contains_point(point: Point2D, polygon: Sequence[Point2D]) -> bool:
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        intersects = ((y1 > y) != (y2 > y)) and (
            x < ((x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1)
        )
        if intersects:
            inside = not inside
    return inside


__all__ = [
    "Point2D",
    "cyclohexane_boat_points",
    "cyclohexane_chair_flipped_points",
    "cyclohexane_chair_points",
    "place_template_on_bond",
    "regular_ring_points_for_atom",
    "regular_ring_points_for_bond",
    "regular_ring_radius",
    "ring_points",
    "scale_points",
    "scale_points_to_bond_length",
]
