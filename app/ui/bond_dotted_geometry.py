from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath


def dotted_bond_path_from_trimmed_segment(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    start_trim: float,
    end_trim: float,
    dot_radius: float,
    target_spacing: float,
) -> QPainterPath:
    path = QPainterPath()
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        path.addEllipse(QPointF(x1, y1), dot_radius, dot_radius)
        return path

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
    usable_dx = end_x - start_x
    usable_dy = end_y - start_y
    usable_length = math.hypot(usable_dx, usable_dy)

    if usable_length <= 1e-6:
        path.addEllipse(QPointF((x1 + x2) * 0.5, (y1 + y2) * 0.5), dot_radius, dot_radius)
        return path

    count = max(1, int(usable_length / target_spacing))
    step = usable_length / count
    for index in range(count):
        distance = step * (index + 0.5)
        cx = start_x + ux * distance
        cy = start_y + uy * distance
        path.addEllipse(QPointF(cx, cy), dot_radius, dot_radius)
    return path


__all__ = ["dotted_bond_path_from_trimmed_segment"]
