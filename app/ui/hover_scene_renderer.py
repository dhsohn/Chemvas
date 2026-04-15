from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsTextItem,
)


def clear_hover_items(
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


def build_atom_hover_indicator(
    center: QPointF,
    radius: float,
    *,
    pen_color: QColor | None = None,
    brush_color: QColor | None = None,
    z_value: float = 5.0,
) -> QGraphicsEllipseItem:
    circle = QGraphicsEllipseItem(
        center.x() - radius,
        center.y() - radius,
        radius * 2.0,
        radius * 2.0,
    )
    pen = QPen(_indicator_pen_color() if pen_color is None else QColor(pen_color))
    pen.setWidthF(1.0)
    circle.setPen(pen)
    circle.setBrush(_indicator_brush_color() if brush_color is None else QColor(brush_color))
    circle.setZValue(z_value)
    return circle


def build_bond_hover_indicator(
    start: QPointF,
    end: QPointF,
    radius: float,
    *,
    pen_color: QColor | None = None,
    brush_color: QColor | None = None,
    z_value: float = 4.0,
) -> QGraphicsEllipseItem:
    midpoint = QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
    return build_atom_hover_indicator(
        midpoint,
        radius,
        pen_color=pen_color,
        brush_color=brush_color,
        z_value=z_value,
    )


def add_hover_preview_items(
    scene: QGraphicsScene,
    items: Sequence[QGraphicsItem],
    *,
    color: QColor | None = None,
    opacity: float = 0.55,
    z_value: float = 4.5,
) -> list[QGraphicsItem]:
    preview_color = _preview_color() if color is None else QColor(color)
    added_items: list[QGraphicsItem] = []
    for item in items:
        _apply_preview_style(item, preview_color)
        item.setOpacity(opacity)
        item.setZValue(z_value)
        scene.addItem(item)
        added_items.append(item)
    return added_items


def _apply_preview_style(item: QGraphicsItem, color: QColor) -> None:
    if isinstance(item, QGraphicsTextItem):
        item.setDefaultTextColor(color)
    if hasattr(item, "pen"):
        pen = QPen(item.pen())
        pen.setColor(color)
        item.setPen(pen)
    if hasattr(item, "brush"):
        brush = item.brush()
        if brush.style() != Qt.BrushStyle.NoBrush:
            brush.setColor(color)
            item.setBrush(brush)


def _indicator_pen_color() -> QColor:
    return QColor("#9a9a9a")


def _indicator_brush_color() -> QColor:
    return QColor(190, 190, 190, 80)


def _preview_color() -> QColor:
    return QColor(120, 120, 120, 140)


__all__ = [
    "add_hover_preview_items",
    "build_atom_hover_indicator",
    "build_bond_hover_indicator",
    "clear_hover_items",
]
