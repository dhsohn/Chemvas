from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, cast

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
)

from chemvas.features.rendering import (
    BOLD_BOND_STYLES,
    PLAIN_DOUBLE_STYLES,
    LineSegment,
    double_position_for_style,
    normal_away_from_parallel_segment,
    normalized_plain_double_style,
    plain_double_preview_segments,
)
from chemvas.ui.graphics_items import NoSelectLineItem


def _set_line_segments(items: Sequence, segments: Sequence[LineSegment]) -> bool:
    """Apply segments 1:1 onto line items; False on count/type mismatch."""
    if len(items) != len(segments):
        return False
    for item, segment in zip(items, segments, strict=False):
        if not isinstance(item, QGraphicsLineItem):
            return False
        item.setLine(*segment)
    return True


def _apply_plain_double_preview_variant(items: list, style: str) -> list:
    if len(items) != 2 or not all(
        isinstance(item, QGraphicsLineItem) for item in items
    ):
        return items
    segments = tuple(
        (line.x1(), line.y1(), line.x2(), line.y2())
        for line in (item.line() for item in items)
    )
    for item, segment in zip(
        items, plain_double_preview_segments(segments, style), strict=False
    ):
        item.setLine(*segment)
    return items


def _bold_normal(
    bond_renderer, segment: LineSegment, bold_outward: bool
) -> tuple[float, float]:
    nx, ny = bond_renderer.line_normal(
        segment[0], segment[1], segment[2], segment[3], None
    )
    if bold_outward:
        return -nx, -ny
    return nx, ny


def _bold_strip_item(
    segment: LineSegment,
    *,
    canvas_renderer,
    bond_renderer,
    bold_outward: bool,
    normal: tuple[float, float] | None = None,
):
    nx, ny = normal or _bold_normal(bond_renderer, segment, bold_outward)
    return bond_renderer.one_sided_bond_strip(
        segment[0],
        segment[1],
        segment[2],
        segment[3],
        nx,
        ny,
        canvas_renderer.style.bond_line_width,
        canvas_renderer.style.bold_bond_width,
    )


def _update_bold_first_item(
    first,
    segment: LineSegment,
    *,
    canvas_renderer,
    bond_renderer,
    bold_outward: bool,
    normal: tuple[float, float] | None = None,
) -> bool:
    x1, y1, x2, y2 = segment
    nx, ny = normal or _bold_normal(bond_renderer, segment, bold_outward)
    if isinstance(first, QGraphicsPolygonItem):
        first.setPolygon(
            bond_renderer.strip_polygon(
                x1,
                y1,
                x2,
                y2,
                nx,
                ny,
                canvas_renderer.style.bond_line_width,
                canvas_renderer.style.bold_bond_width,
            )
        )
        return True
    if isinstance(first, QGraphicsLineItem):
        first.setLine(x1, y1, x2, y2)
        return True
    return False


def build_bond_preview_items(
    start: QPointF,
    end: QPointF,
    *,
    style: str,
    order: int,
    a_id: int | None,
    b_id: int | None,
    canvas_renderer,
    bond_renderer,
) -> list:
    if style == "wedge":
        return bond_renderer.draw_wedge_bond(
            start.x(), start.y(), end.x(), end.y(), a_id, b_id
        )
    if style == "hash":
        return bond_renderer.draw_hash_bond(
            start.x(), start.y(), end.x(), end.y(), a_id, b_id
        )
    if style == "dotted":
        return bond_renderer.draw_dotted_bond(
            start.x(), start.y(), end.x(), end.y(), a_id, b_id
        )
    if style in BOLD_BOND_STYLES:
        bold_outward = style == "bold_out"
        if order == 2:
            items = bond_renderer.draw_parallel_bonds(
                start.x(), start.y(), end.x(), end.y(), order, a_id, b_id
            )
            items = _apply_plain_double_preview_variant(
                items, double_position_for_style(style, order)
            )
            if len(items) == 2 and all(
                isinstance(item, QGraphicsLineItem) for item in items
            ):
                first_line = items[0].line()
                second_line = items[1].line()
                first_segment = (
                    first_line.x1(),
                    first_line.y1(),
                    first_line.x2(),
                    first_line.y2(),
                )
                second_segment = (
                    second_line.x1(),
                    second_line.y1(),
                    second_line.x2(),
                    second_line.y2(),
                )
                base_normal = bond_renderer.line_normal(*first_segment, None)
                normal = normal_away_from_parallel_segment(
                    first_segment, second_segment, *base_normal
                )
                items[0] = _bold_strip_item(
                    first_segment,
                    canvas_renderer=canvas_renderer,
                    bond_renderer=bond_renderer,
                    bold_outward=False,
                    normal=normal,
                )
            return items
        if order >= 2:
            items = bond_renderer.draw_parallel_bonds(
                start.x(), start.y(), end.x(), end.y(), order, a_id, b_id
            )
            if items and isinstance(items[0], QGraphicsLineItem):
                line = items[0].line()
                items[0] = _bold_strip_item(
                    (line.x1(), line.y1(), line.x2(), line.y2()),
                    canvas_renderer=canvas_renderer,
                    bond_renderer=bond_renderer,
                    bold_outward=bold_outward,
                )
            return items
        segment = start.x(), start.y(), end.x(), end.y()
        return [
            _bold_strip_item(
                segment,
                canvas_renderer=canvas_renderer,
                bond_renderer=bond_renderer,
                bold_outward=bold_outward,
            )
        ]
    if order == 2 and style in PLAIN_DOUBLE_STYLES:
        items = bond_renderer.draw_parallel_bonds(
            start.x(), start.y(), end.x(), end.y(), order, a_id, b_id
        )
        return _apply_plain_double_preview_variant(
            items,
            normalized_plain_double_style(style, order),
        )
    if order >= 2:
        return bond_renderer.draw_parallel_bonds(
            start.x(), start.y(), end.x(), end.y(), order, a_id, b_id
        )
    line_item = NoSelectLineItem(start.x(), start.y(), end.x(), end.y())
    line_item.setPen(canvas_renderer.bond_pen())
    return [line_item]


def update_bond_preview_items(
    items: list,
    start: QPointF,
    end: QPointF,
    *,
    style: str,
    order: int,
    a_id: int | None,
    b_id: int | None,
    canvas_renderer,
    bond_renderer,
) -> bool:
    if not items:
        return False
    if style == "wedge":
        if len(items) != 1 or not isinstance(items[0], QGraphicsPolygonItem):
            return False
        items[0].setPolygon(
            bond_renderer.wedge_polygon(
                start.x(), start.y(), end.x(), end.y(), a_id, b_id
            )
        )
        return True
    if style == "hash":
        length = math.hypot(end.x() - start.x(), end.y() - start.y()) or 1.0
        count = max(3, int(length / max(canvas_renderer.style.hash_spacing_px, 1e-6)))
        segments = tuple(
            bond_renderer.hash_segments(
                start.x(), start.y(), end.x(), end.y(), count, a_id, b_id
            )
        )
        return _set_line_segments(items, segments)
    if style == "dotted":
        if len(items) != 1 or not isinstance(items[0], QGraphicsPathItem):
            return False
        items[0].setPath(
            bond_renderer.dotted_bond_path(
                start.x(), start.y(), end.x(), end.y(), a_id, b_id
            )
        )
        return True
    if style in BOLD_BOND_STYLES:
        bold_outward = style == "bold_out"
        if order == 2:
            segments = tuple(
                bond_renderer.parallel_bond_segments(
                    start.x(),
                    start.y(),
                    end.x(),
                    end.y(),
                    order,
                    a_id,
                    b_id,
                )
            )
            updated_segments = plain_double_preview_segments(
                segments,
                double_position_for_style(style, order),
            )
            if len(updated_segments) != 2 or len(items) != 2:
                return False
            base_normal = bond_renderer.line_normal(*updated_segments[0], None)
            normal = normal_away_from_parallel_segment(
                updated_segments[0],
                updated_segments[1],
                *base_normal,
            )
            if not _update_bold_first_item(
                items[0],
                updated_segments[0],
                canvas_renderer=canvas_renderer,
                bond_renderer=bond_renderer,
                bold_outward=False,
                normal=normal,
            ):
                return False
            return _set_line_segments(items[1:], updated_segments[1:])
        if order >= 2:
            segments = tuple(
                bond_renderer.parallel_bond_segments(
                    start.x(), start.y(), end.x(), end.y(), order, a_id, b_id
                )
            )
            if not segments or len(items) != len(segments):
                return False
            if not _update_bold_first_item(
                items[0],
                segments[0],
                canvas_renderer=canvas_renderer,
                bond_renderer=bond_renderer,
                bold_outward=bold_outward,
            ):
                return False
            return _set_line_segments(items[1:], segments[1:])
        segment = start.x(), start.y(), end.x(), end.y()
        return _update_bold_first_item(
            items[0],
            segment,
            canvas_renderer=canvas_renderer,
            bond_renderer=bond_renderer,
            bold_outward=bold_outward,
        )
    if order == 2 and style in PLAIN_DOUBLE_STYLES:
        segments = tuple(
            bond_renderer.parallel_bond_segments(
                start.x(), start.y(), end.x(), end.y(), order, a_id, b_id
            )
        )
        updated_segments = plain_double_preview_segments(
            segments,
            normalized_plain_double_style(style, order),
        )
        return _set_line_segments(items, updated_segments)
    if order >= 2:
        segments = tuple(
            bond_renderer.parallel_bond_segments(
                start.x(), start.y(), end.x(), end.y(), order, a_id, b_id
            )
        )
        return _set_line_segments(items, segments)
    return _set_line_segments(items, ((start.x(), start.y(), end.x(), end.y()),))


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


__all__ = [
    "add_bond_preview_items",
    "build_bond_preview_items",
    "clear_bond_preview_items",
    "update_bond_preview_items",
]
