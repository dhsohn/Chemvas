from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsTextItem


def clear_bond_preview_items(
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


def add_bond_preview_items(
    scene: QGraphicsScene,
    items: Sequence[QGraphicsItem],
    *,
    color: QColor | None = None,
    opacity: float = 0.5,
    z_value: float = 4.5,
) -> list[QGraphicsItem]:
    preview_color = QColor(120, 120, 120, 140) if color is None else QColor(color)
    added: list[QGraphicsItem] = []
    for item in items:
        if isinstance(item, QGraphicsTextItem):
            item.setDefaultTextColor(preview_color)
        if hasattr(item, "pen"):
            pen_item = cast(Any, item)
            pen = QPen(pen_item.pen())
            pen.setColor(preview_color)
            pen_item.setPen(pen)
        if hasattr(item, "brush"):
            brush_item = cast(Any, item)
            brush = brush_item.brush()
            if brush.style() != Qt.BrushStyle.NoBrush:
                brush.setColor(preview_color)
                brush_item.setBrush(brush)
        item.setOpacity(opacity)
        item.setZValue(z_value)
        scene.addItem(item)
        added.append(item)
    return added


__all__ = ["add_bond_preview_items", "clear_bond_preview_items"]
