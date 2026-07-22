from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
)

PenWidthGetter = Callable[[QPen], float]
LineStrokePathBuilder = Callable[[QPointF, QPointF, float], QPainterPath]

ARROW_OBJECT_KINDS = {
    "arrow",
    "equilibrium",
    "resonance",
    "curved_single",
    "curved_double",
    "inhibit",
    "dotted",
}


def _default_width_for_pen(pen: QPen) -> float:
    return float(pen.widthF())


def selection_line_stroke_path(
    start: QPointF,
    end: QPointF,
    width: float,
) -> QPainterPath:
    bond_path = QPainterPath(start)
    bond_path.lineTo(end)
    stroker = QPainterPathStroker()
    stroker.setWidth(width)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stroker.createStroke(bond_path)


def selection_path_for_bond_item(
    item: QGraphicsItem,
    *,
    width: float | None = None,
    default_width_for_pen: PenWidthGetter = _default_width_for_pen,
    line_stroke_path: LineStrokePathBuilder = selection_line_stroke_path,
) -> QPainterPath:
    if isinstance(item, QGraphicsLineItem):
        line = item.line()
        start = item.mapToScene(QPointF(line.x1(), line.y1()))
        end = item.mapToScene(QPointF(line.x2(), line.y2()))
        stroke_width = width if width is not None else default_width_for_pen(item.pen())
        return line_stroke_path(start, end, stroke_width)
    if isinstance(item, QGraphicsPolygonItem):
        bond_path = QPainterPath()
        bond_path.addPolygon(item.mapToScene(item.polygon()))
        return bond_path
    if isinstance(item, QGraphicsPathItem):
        mapped_path = item.sceneTransform().map(item.path())
        if (
            item.pen().style() == Qt.PenStyle.NoPen
            and item.brush().style() != Qt.BrushStyle.NoBrush
        ):
            return mapped_path
        stroker = QPainterPathStroker()
        stroker.setWidth(
            width if width is not None else default_width_for_pen(item.pen())
        )
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(mapped_path)
    return QPainterPath()


def selection_path_for_object_item(
    item: QGraphicsItem,
    *,
    kind: object,
    pad: float,
    mark_center: QPointF | None = None,
    mark_radius: float | None = None,
    atom_pick_radius: float = 0.0,
    default_width_for_pen: PenWidthGetter = _default_width_for_pen,
    line_stroke_path: LineStrokePathBuilder = selection_line_stroke_path,
) -> QPainterPath:
    if kind == "mark":
        if mark_center is None or mark_radius is None:
            return QPainterPath()
        path = QPainterPath()
        path.addEllipse(mark_center, mark_radius, mark_radius)
        return path
    if kind in ARROW_OBJECT_KINDS and isinstance(item, QGraphicsPathItem):
        return selection_path_for_bond_item(
            item,
            width=max(item.pen().widthF() + pad * 1.5, atom_pick_radius * 0.7),
            default_width_for_pen=default_width_for_pen,
            line_stroke_path=line_stroke_path,
        )
    if isinstance(item, QGraphicsTextItem):
        rect = item.sceneBoundingRect().adjusted(-pad, -pad, pad, pad)
        path = QPainterPath()
        path.addRoundedRect(rect, pad * 0.7, pad * 0.7)
        return path
    shape = item.mapToScene(item.shape())
    if shape.isEmpty():
        rect = item.sceneBoundingRect().adjusted(-pad, -pad, pad, pad)
        path = QPainterPath()
        path.addRoundedRect(rect, pad * 0.7, pad * 0.7)
        return path
    stroker = QPainterPathStroker()
    stroker.setWidth(pad * 2.0)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    overlay = QPainterPath(shape)
    overlay.addPath(stroker.createStroke(shape))
    simplified = overlay.simplified()
    simplified.setFillRule(Qt.FillRule.WindingFill)
    return simplified


__all__ = [
    "ARROW_OBJECT_KINDS",
    "LineStrokePathBuilder",
    "PenWidthGetter",
    "selection_line_stroke_path",
    "selection_path_for_bond_item",
    "selection_path_for_object_item",
]
