from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen

from chemvas.features.selection import create_rotation_handle_item
from chemvas.ui.graphics_items import NoSelectEllipseItem, NoSelectPathItem

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsPathItem

# Every selection mark is the same thin line in the accent colour, drawn at
# this width on screen regardless of zoom, so a selection reads as one thing
# whether it is a structure, an arrow, a note or a group.
SELECTION_OUTLINE_SCREEN_PX = 1.5


def selection_outline_pen(color: QColor) -> QPen:
    pen = QPen(color)
    pen.setWidthF(SELECTION_OUTLINE_SCREEN_PX)
    pen.setCosmetic(True)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def selection_group_outline_item(rect: QRectF, color: QColor) -> NoSelectPathItem:
    # A group box is dashed: it says "these move as a unit", which is a
    # different fact from the solid selection frame around what is selected.
    path = QPainterPath()
    corner = min(6.0, min(rect.width(), rect.height()) / 4.0)
    path.addRoundedRect(rect, corner, corner)
    outline = NoSelectPathItem(path)
    outline.setData(0, "selection_outline")
    outline.setData(2, {"kind": "group"})
    outline.setZValue(20)
    pen = selection_outline_pen(color)
    pen.setWidthF(1.0)
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
    outline.setPen(selection_outline_pen(color))
    outline.setBrush(QBrush(Qt.BrushStyle.NoBrush))
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
    outline.setPen(selection_outline_pen(color))
    outline.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    return outline


def selection_frame_outline_items(
    rect: QRectF, color: QColor
) -> tuple[NoSelectPathItem, QGraphicsPathItem]:
    """The solid frame around a rotatable selection and its rotation knob.

    Both live in the outline layer so they move with a drag and go with the
    selection; the knob alone is a handle, so the select tool can grip it.
    """
    path = QPainterPath()
    path.addRoundedRect(rect, 2.0, 2.0)
    frame = NoSelectPathItem(path)
    frame.setData(0, "selection_outline")
    frame.setData(2, {"kind": "frame"})
    frame.setZValue(20)
    frame.setPen(selection_outline_pen(color))
    frame.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    knob = create_rotation_handle_item(QPointF(rect.center().x(), rect.top()))
    return frame, knob


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
    "SELECTION_OUTLINE_SCREEN_PX",
    "selection_center_outline_items",
    "selection_component_outline_item",
    "selection_frame_outline_items",
    "selection_group_outline_item",
    "selection_object_outline_item",
    "selection_outline_pen",
]
