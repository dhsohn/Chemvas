from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from ui.graphics_items import NoSelectLineItem


LineSegment = tuple[float, float, float, float]


@dataclass(frozen=True)
class BondPreviewConfig:
    style: str
    order: int
    bond_length_px: float
    bond_line_width: float
    bold_bond_width: float
    hash_spacing_px: float


@dataclass(frozen=True)
class BondPreviewBuildResolvers:
    draw_wedge_bond: Callable[[float, float, float, float, int | None, int | None], list]
    draw_hash_bond: Callable[[float, float, float, float, int | None, int | None], list]
    draw_parallel_bonds: Callable[[float, float, float, float, int, int | None, int | None], list]
    line_normal: Callable[[float, float, float, float, QPointF | None], tuple[float, float]]
    one_sided_bond_strip: Callable[[float, float, float, float, float, float, float, float], Any]
    bond_pen: Callable[[], QPen]


@dataclass(frozen=True)
class BondPreviewUpdateResolvers:
    wedge_polygon: Callable[[float, float, float, float, int | None, int | None], QPolygonF]
    hash_segments: Callable[[float, float, float, float, int, int | None, int | None], Sequence[LineSegment]]
    parallel_bond_segments: Callable[[float, float, float, float, int, int | None, int | None], Sequence[LineSegment]]
    line_normal: Callable[[float, float, float, float, QPointF | None], tuple[float, float]]
    strip_polygon: Callable[[float, float, float, float, float, float, float, float], QPolygonF]


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
            pen = QPen(item.pen())
            pen.setColor(preview_color)
            item.setPen(pen)
        if hasattr(item, "brush"):
            brush = item.brush()
            if brush.style() != Qt.BrushStyle.NoBrush:
                brush.setColor(preview_color)
                item.setBrush(brush)
        item.setOpacity(opacity)
        item.setZValue(z_value)
        scene.addItem(item)
        added.append(item)
    return added


def build_bond_preview_items(
    start: QPointF,
    end: QPointF,
    *,
    config: BondPreviewConfig,
    a_id: int | None,
    b_id: int | None,
    resolvers: BondPreviewBuildResolvers,
) -> list:
    style = config.style
    order = config.order
    if style == "wedge":
        return resolvers.draw_wedge_bond(start.x(), start.y(), end.x(), end.y(), a_id, b_id)
    if style == "hash":
        return resolvers.draw_hash_bond(start.x(), start.y(), end.x(), end.y(), a_id, b_id)
    if style in {"bold", "bold_in", "bold_out"}:
        bold_outward = style == "bold_out"
        if order >= 2:
            items = resolvers.draw_parallel_bonds(start.x(), start.y(), end.x(), end.y(), order, a_id, b_id)
            if items and isinstance(items[0], QGraphicsLineItem):
                line = items[0].line()
                nx, ny = resolvers.line_normal(line.x1(), line.y1(), line.x2(), line.y2(), None)
                if bold_outward:
                    nx, ny = -nx, -ny
                items[0] = resolvers.one_sided_bond_strip(
                    line.x1(),
                    line.y1(),
                    line.x2(),
                    line.y2(),
                    nx,
                    ny,
                    config.bond_line_width,
                    config.bold_bond_width * 1.5,
                )
            return items
        bx1, by1, bx2, by2 = _expanded_bold_segment(start, end, config.bond_length_px)
        nx, ny = resolvers.line_normal(bx1, by1, bx2, by2, None)
        if bold_outward:
            nx, ny = -nx, -ny
        return [
            resolvers.one_sided_bond_strip(
                bx1,
                by1,
                bx2,
                by2,
                nx,
                ny,
                config.bond_line_width,
                config.bold_bond_width * 1.5,
            )
        ]
    if order >= 2:
        return resolvers.draw_parallel_bonds(start.x(), start.y(), end.x(), end.y(), order, a_id, b_id)
    line_item = NoSelectLineItem(start.x(), start.y(), end.x(), end.y())
    line_item.setPen(resolvers.bond_pen())
    return [line_item]


def update_bond_preview_items(
    items: list,
    start: QPointF,
    end: QPointF,
    *,
    config: BondPreviewConfig,
    a_id: int | None,
    b_id: int | None,
    resolvers: BondPreviewUpdateResolvers,
) -> bool:
    if not items:
        return False
    style = config.style
    order = config.order
    if style == "wedge":
        if len(items) != 1 or not isinstance(items[0], QGraphicsPolygonItem):
            return False
        items[0].setPolygon(resolvers.wedge_polygon(start.x(), start.y(), end.x(), end.y(), a_id, b_id))
        return True
    if style == "hash":
        length = math.hypot(end.x() - start.x(), end.y() - start.y()) or 1.0
        count = max(3, int(length / max(config.hash_spacing_px, 1e-6)))
        segments = tuple(resolvers.hash_segments(start.x(), start.y(), end.x(), end.y(), count, a_id, b_id))
        if len(items) != len(segments):
            return False
        for item, seg in zip(items, segments):
            if not isinstance(item, QGraphicsLineItem):
                return False
            item.setLine(*seg)
        return True
    if style in {"bold", "bold_in", "bold_out"}:
        bold_outward = style == "bold_out"
        if order >= 2:
            segments = tuple(resolvers.parallel_bond_segments(start.x(), start.y(), end.x(), end.y(), order, a_id, b_id))
            if not segments or len(items) != len(segments):
                return False
            x1, y1, x2, y2 = segments[0]
            nx, ny = resolvers.line_normal(x1, y1, x2, y2, None)
            if bold_outward:
                nx, ny = -nx, -ny
            first = items[0]
            if isinstance(first, QGraphicsPolygonItem):
                first.setPolygon(
                    resolvers.strip_polygon(
                        x1,
                        y1,
                        x2,
                        y2,
                        nx,
                        ny,
                        config.bond_line_width,
                        config.bold_bond_width * 1.5,
                    )
                )
            elif isinstance(first, QGraphicsLineItem):
                first.setLine(x1, y1, x2, y2)
            else:
                return False
            for item, seg in zip(items[1:], segments[1:]):
                if not isinstance(item, QGraphicsLineItem):
                    return False
                item.setLine(*seg)
            return True
        bx1, by1, bx2, by2 = _expanded_bold_segment(start, end, config.bond_length_px)
        nx, ny = resolvers.line_normal(bx1, by1, bx2, by2, None)
        if bold_outward:
            nx, ny = -nx, -ny
        first = items[0]
        if isinstance(first, QGraphicsPolygonItem):
            first.setPolygon(
                resolvers.strip_polygon(
                    bx1,
                    by1,
                    bx2,
                    by2,
                    nx,
                    ny,
                    config.bond_line_width,
                    config.bold_bond_width * 1.5,
                )
            )
        elif isinstance(first, QGraphicsLineItem):
            first.setLine(bx1, by1, bx2, by2)
        else:
            return False
        return True
    if order >= 2:
        segments = tuple(resolvers.parallel_bond_segments(start.x(), start.y(), end.x(), end.y(), order, a_id, b_id))
        if len(items) != len(segments):
            return False
        for item, seg in zip(items, segments):
            if not isinstance(item, QGraphicsLineItem):
                return False
            item.setLine(*seg)
        return True
    if len(items) != 1 or not isinstance(items[0], QGraphicsLineItem):
        return False
    items[0].setLine(start.x(), start.y(), end.x(), end.y())
    return True


def _expanded_bold_segment(start: QPointF, end: QPointF, bond_length_px: float) -> LineSegment:
    bx1 = start.x()
    by1 = start.y()
    bx2 = end.x()
    by2 = end.y()
    dx = bx2 - bx1
    dy = by2 - by1
    length = math.hypot(dx, dy) or 1.0
    pad = bond_length_px * 0.1
    factor = pad / length
    bx1 = bx1 - dx * factor
    by1 = by1 - dy * factor
    bx2 = bx2 + dx * factor
    by2 = by2 + dy * factor
    dx = bx2 - bx1
    dy = by2 - by1
    bx1 = bx1 + dx * 0.025
    by1 = by1 + dy * 0.025
    bx2 = bx2 - dx * 0.025
    by2 = by2 - dy * 0.025
    return bx1, by1, bx2, by2


__all__ = [
    "BondPreviewBuildResolvers",
    "BondPreviewConfig",
    "BondPreviewUpdateResolvers",
    "add_bond_preview_items",
    "build_bond_preview_items",
    "clear_bond_preview_items",
    "update_bond_preview_items",
]
