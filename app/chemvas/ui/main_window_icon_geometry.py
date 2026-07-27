from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF


def regular_icon_polygon(
    *,
    center: QPointF,
    radius: float,
    sides: int,
    start_angle_degrees: float,
) -> QPolygonF:
    polygon = QPolygonF()
    for index in range(sides):
        angle = math.radians(360 / sides * index + start_angle_degrees)
        polygon.append(
            QPointF(
                center.x() + radius * math.cos(angle),
                center.y() + radius * math.sin(angle),
            )
        )
    return polygon


def benzene_icon_polygon(center: QPointF, radius: float) -> QPolygonF:
    return regular_icon_polygon(
        center=center,
        radius=radius,
        sides=6,
        start_angle_degrees=-30.0,
    )


__all__ = [
    "benzene_icon_polygon",
    "regular_icon_polygon",
]
