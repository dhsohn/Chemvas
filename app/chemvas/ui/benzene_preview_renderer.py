from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsScene

from chemvas.ui.graphics_items import NoSelectLineItem
from chemvas.ui.preview_scene_renderer import preview_color, preview_pen

InnerBondItemFactory = Callable[[QPointF, QPointF, QPointF], QGraphicsItem | None]


def clear_benzene_preview(
    scene: QGraphicsScene,
    items: Sequence[QGraphicsItem],
) -> list[QGraphicsItem]:
    for item in items:
        try:
            if item.scene() is scene:
                scene.removeItem(item)
        except RuntimeError:
            pass
    return []


def rebuild_benzene_preview(
    scene: QGraphicsScene,
    ring_points: Sequence[QPointF],
    *,
    base_pen: QPen,
    atom_radius: float,
    create_inner_bond_item: InnerBondItemFactory,
    existing_items: Sequence[QGraphicsItem] | None = None,
) -> list[QGraphicsItem]:
    if existing_items is not None:
        clear_benzene_preview(scene, existing_items)
    if not ring_points:
        return []

    color = preview_color()
    center = _ring_center(ring_points)
    items: list[QGraphicsItem] = []

    for index, point in enumerate(ring_points):
        next_point = ring_points[(index + 1) % len(ring_points)]
        line = NoSelectLineItem(point.x(), point.y(), next_point.x(), next_point.y())
        line.setPen(preview_pen(base_pen, color))
        line.setOpacity(0.5)
        scene.addItem(line)
        items.append(line)

    for index in range(0, len(ring_points), 2):
        point = ring_points[index]
        next_point = ring_points[(index + 1) % len(ring_points)]
        inner_item = create_inner_bond_item(point, next_point, center)
        if inner_item is None:
            continue
        _apply_preview_style(inner_item, color)
        inner_item.setOpacity(0.5)
        scene.addItem(inner_item)
        items.append(inner_item)

    dot_radius = max(0.0, float(atom_radius))
    for point in ring_points:
        dot = QGraphicsEllipseItem(
            point.x() - dot_radius,
            point.y() - dot_radius,
            dot_radius * 2.0,
            dot_radius * 2.0,
        )
        dot.setBrush(color)
        dot.setPen(QPen(Qt.PenStyle.NoPen))
        dot.setOpacity(0.5)
        scene.addItem(dot)
        items.append(dot)

    return items


def _apply_preview_style(item: QGraphicsItem, color: QColor) -> None:
    styleable: Any = item
    if hasattr(item, "pen"):
        pen = QPen(styleable.pen())
        pen.setColor(color)
        styleable.setPen(pen)
    if hasattr(item, "brush"):
        brush = styleable.brush()
        if brush.style() != Qt.BrushStyle.NoBrush:
            brush.setColor(color)
            styleable.setBrush(brush)


def _ring_center(ring_points: Sequence[QPointF]) -> QPointF:
    count = len(ring_points)
    return QPointF(
        sum(point.x() for point in ring_points) / count,
        sum(point.y() for point in ring_points) / count,
    )


__all__ = [
    "InnerBondItemFactory",
    "clear_benzene_preview",
    "rebuild_benzene_preview",
]
