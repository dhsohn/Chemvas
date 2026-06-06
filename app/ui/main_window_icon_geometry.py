from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF
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


def template_preview_ring_polygon(sides: int) -> QPolygonF:
    return regular_icon_polygon(
        center=QPointF(15.0, 15.0),
        radius=10.0,
        sides=sides,
        start_angle_degrees=-90.0,
    )


def template_preview_ring_sides(label: str) -> int | None:
    lower = label.lower()
    if "cyclopropane" in lower:
        return 3
    if "cyclobutane" in lower:
        return 4
    if "cyclopentane" in lower or "furan" in lower or "thiophene" in lower:
        return 5
    if "cycloheptane" in lower:
        return 7
    if "cyclooctane" in lower:
        return 8
    if "benzene" in lower or "pyridine" in lower or "pyrimidine" in lower:
        return 6
    if "crown" in lower:
        return 10
    return None


def chair_icon_rect() -> QRectF:
    return QRectF(2.0, 5.5, 26.0, 19.0)


def chair_icon_points(rect: QRectF) -> QPolygonF:
    angle_steep = math.radians(-68.0)
    angle_shallow = math.radians(-25.0)
    v1 = QPointF(math.cos(angle_steep), math.sin(angle_steep))
    v2 = QPointF(math.cos(angle_shallow), math.sin(angle_shallow))

    points = [
        QPointF(0.0, 0.0),
        QPointF(v1.x(), v1.y()),
        QPointF(v1.x() + 1.0, v1.y()),
        QPointF(v1.x() + 1.0 + v2.x(), v1.y() + v2.y()),
        QPointF(1.0 + v2.x(), v2.y()),
        QPointF(v2.x(), v2.y()),
    ]
    min_x = min(point.x() for point in points)
    max_x = max(point.x() for point in points)
    min_y = min(point.y() for point in points)
    max_y = max(point.y() for point in points)
    width = max_x - min_x
    height = max_y - min_y
    scale = min(rect.width() / width, rect.height() / height) * 0.92
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    center = rect.center()
    polygon = QPolygonF()
    for point in points:
        polygon.append(
            QPointF(
                center.x() + (point.x() - cx) * scale,
                center.y() + (point.y() - cy) * scale,
            )
        )
    return polygon


__all__ = [
    "benzene_icon_polygon",
    "chair_icon_points",
    "chair_icon_rect",
    "regular_icon_polygon",
    "template_preview_ring_polygon",
    "template_preview_ring_sides",
]
