from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen

from chemvas.ui.graphics_items import NoSelectEllipseItem, NoSelectPathItem


def selection_group_outline_item(rect: QRectF, color: QColor) -> NoSelectPathItem:
    path = QPainterPath()
    corner = min(6.0, min(rect.width(), rect.height()) / 4.0)
    path.addRoundedRect(rect, corner, corner)
    outline = NoSelectPathItem(path)
    outline.setData(0, "selection_outline")
    outline.setData(2, {"kind": "group"})
    outline.setZValue(20)
    pen = QPen(color)
    pen.setWidthF(1.2)
    pen.setStyle(Qt.PenStyle.DashLine)
    outline.setPen(pen)
    outline.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    return outline


def selection_object_outline_item(
    path: QPainterPath, color: QColor
) -> NoSelectPathItem:
    outline = NoSelectPathItem(path)
    outline.setData(0, "selection_outline")
    outline.setData(2, {"kind": "object"})
    outline.setZValue(19)
    outline.setPen(QPen(Qt.PenStyle.NoPen))
    outline.setBrush(QBrush(color))
    return outline


def selection_component_outline_item(
    path: QPainterPath,
    *,
    color: QColor,
    atom_ids: set[int],
) -> NoSelectPathItem:
    outline = NoSelectPathItem(path)
    outline.setData(0, "selection_outline")
    outline.setData(2, {"kind": "component", "atom_ids": sorted(atom_ids)})
    outline.setZValue(19)
    outline.setPen(QPen(Qt.PenStyle.NoPen))
    outline.setBrush(QBrush(color))
    return outline


def selection_center_outline_items(
    center: QPointF,
    *,
    outer_radius: float,
    inner_radius: float,
) -> tuple[NoSelectEllipseItem, NoSelectEllipseItem]:
    outer = NoSelectEllipseItem(
        center.x() - outer_radius,
        center.y() - outer_radius,
        outer_radius * 2.0,
        outer_radius * 2.0,
    )
    outer.setData(0, "selection_outline")
    outer.setData(2, {"kind": "center"})
    outer.setZValue(21)
    pen = QPen(QColor("#ff4dc9"))
    pen.setWidthF(1.4)
    outer.setPen(pen)
    outer.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    inner = NoSelectEllipseItem(
        center.x() - inner_radius,
        center.y() - inner_radius,
        inner_radius * 2.0,
        inner_radius * 2.0,
    )
    inner.setData(0, "selection_outline")
    inner.setData(2, {"kind": "center"})
    inner.setZValue(21)
    inner.setPen(QPen(Qt.PenStyle.NoPen))
    inner.setBrush(QBrush(QColor("#ff4dc9")))
    return outer, inner


__all__ = [
    "selection_center_outline_items",
    "selection_component_outline_item",
    "selection_group_outline_item",
    "selection_object_outline_item",
]
