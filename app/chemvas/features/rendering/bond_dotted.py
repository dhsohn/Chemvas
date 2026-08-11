from __future__ import annotations

import math

Point2D = tuple[float, float]


def dotted_bond_dot_centers(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    start_trim: float,
    end_trim: float,
    target_spacing: float,
) -> list[Point2D]:
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        return [(x1, y1)]

    ux = dx / length
    uy = dy / length
    trim_total = start_trim + end_trim
    if trim_total >= length * 0.8:
        scale = (length * 0.8) / trim_total if trim_total > 1e-6 else 0.0
        start_trim *= scale
        end_trim *= scale

    start_x = x1 + ux * start_trim
    start_y = y1 + uy * start_trim
    end_x = x2 - ux * end_trim
    end_y = y2 - uy * end_trim
    usable_length = math.hypot(end_x - start_x, end_y - start_y)

    if usable_length <= 1e-6:
        return [((x1 + x2) * 0.5, (y1 + y2) * 0.5)]

    count = max(1, int(usable_length / target_spacing))
    step = usable_length / count
    centers: list[Point2D] = []
    for index in range(count):
        distance = step * (index + 0.5)
        centers.append((start_x + ux * distance, start_y + uy * distance))
    return centers


__all__ = ["dotted_bond_dot_centers"]
