from __future__ import annotations

import math
from collections.abc import Sequence

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsScene


def clear_handle_items(
    scene: QGraphicsScene,
    handles: Sequence[QGraphicsItem],
) -> list[QGraphicsItem]:
    for handle in handles:
        try:
            if handle.scene() is scene:
                scene.removeItem(handle)
        except RuntimeError:
            pass
    return []


def create_handle_item(
    pos: QPointF,
    handle_type: str,
    target,
    *,
    radius: float = 5.0,
) -> QGraphicsEllipseItem:
    handle = QGraphicsEllipseItem(pos.x() - radius, pos.y() - radius, radius * 2.0, radius * 2.0)
    handle.setBrush(QColor("#ffffff"))
    handle.setPen(QPen(QColor("#333333")))
    handle.setData(0, "handle")
    handle.setData(1, handle_type)
    handle.setData(2, target)
    handle.setZValue(30)
    return handle


def orbital_handle_positions(center: QPointF, base_dist: float) -> tuple[QPointF, QPointF]:
    return (
        QPointF(center.x() + base_dist, center.y()),
        QPointF(center.x(), center.y() - base_dist),
    )


def orbital_scale_factor(
    center: QPointF,
    pos: QPointF,
    base_dist: float,
    *,
    minimum_scale: float = 0.2,
) -> float:
    safe_base_dist = max(float(base_dist), 1e-6)
    dist = math.hypot(pos.x() - center.x(), pos.y() - center.y())
    return max(minimum_scale, dist / safe_base_dist)


def orbital_rotation_angle(
    center: QPointF,
    pos: QPointF,
    *,
    snap_enabled: bool,
    snap_step: int,
) -> float:
    angle = math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()))
    if snap_enabled:
        step = max(1, int(snap_step))
        angle = round(angle / step) * step
    return angle


def default_curved_control(start: QPointF, end: QPointF) -> QPointF:
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    return QPointF(
        start.x() + dx * 0.5 + nx * length * 0.3,
        start.y() + dy * 0.5 + ny * length * 0.3,
    )


def curved_midpoint(start: QPointF, control: QPointF, end: QPointF) -> QPointF:
    return QPointF(
        0.25 * start.x() + 0.5 * control.x() + 0.25 * end.x(),
        0.25 * start.y() + 0.5 * control.y() + 0.25 * end.y(),
    )


def control_from_midpoint(start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
    return QPointF(
        2.0 * mid.x() - 0.5 * (start.x() + end.x()),
        2.0 * mid.y() - 0.5 * (start.y() + end.y()),
    )


def clamp_curved_midpoint(
    start: QPointF,
    end: QPointF,
    mid: QPointF,
    *,
    snap_enabled: bool,
    snap_distance: float | None,
    max_offset_ratio: float = 0.8,
) -> QPointF:
    chord_mid = QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    v = QPointF(mid.x() - chord_mid.x(), mid.y() - chord_mid.y())
    offset = v.x() * nx + v.y() * ny
    if snap_enabled and snap_distance is not None and snap_distance > 0:
        offset = round(offset / snap_distance) * snap_distance
    max_offset = length * max_offset_ratio
    offset = max(-max_offset, min(max_offset, offset))
    return QPointF(chord_mid.x() + nx * offset, chord_mid.y() + ny * offset)


__all__ = [
    "clamp_curved_midpoint",
    "clear_handle_items",
    "control_from_midpoint",
    "create_handle_item",
    "curved_midpoint",
    "default_curved_control",
    "orbital_handle_positions",
    "orbital_rotation_angle",
    "orbital_scale_factor",
]
