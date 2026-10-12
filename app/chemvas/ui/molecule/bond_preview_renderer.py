from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
)

from chemvas.domain.document import Atom, Bond
from chemvas.features.rendering import (
    BOLD_BOND_STYLES,
    LineSegment,
    is_plain_double_bond_style,
)
from chemvas.ui.canvas.graphics_items import NoSelectLineItem

if TYPE_CHECKING:
    from collections.abc import Sequence


def _set_line_segments(items: Sequence, segments: Sequence[LineSegment]) -> bool:
    """Apply segments 1:1 onto line items; False on count/type mismatch."""
    if len(items) != len(segments):
        return False
    for item, segment in zip(items, segments, strict=False):
        if not isinstance(item, QGraphicsLineItem):
            return False
        item.setLine(*segment)
    return True


def _planned_preview(start, end, style, order, a_id, b_id, bond_renderer):
    # A preview uses the same geometry owner as a committed bond. Temporary
    # endpoint identities cannot accidentally acquire an existing atom's label.
    temporary = min(bond_renderer.context.model.atoms, default=0) - 1
    bond = Bond(
        a_id if a_id is not None else temporary,
        b_id if b_id is not None else temporary - 1,
        order,
        style,
    )
    return bond_renderer.geometry_planner.primitives_for_bond(
        bond, Atom("C", start.x(), start.y()), Atom("C", end.x(), end.y())
    )


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
    if (
        style in BOLD_BOND_STYLES
        or is_plain_double_bond_style(style, order)
        or (style == "single" and order == 1)
    ):
        primitives = _planned_preview(
            start, end, style, order, a_id, b_id, bond_renderer
        )
        return [
            bond_renderer.graphics_builder._item_for_primitive(p) for p in primitives
        ]
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
    if (
        style in BOLD_BOND_STYLES
        or is_plain_double_bond_style(style, order)
        or (style == "single" and order == 1)
    ):
        primitives = _planned_preview(
            start, end, style, order, a_id, b_id, bond_renderer
        )
        updater = bond_renderer.geometry_updater
        try:
            updater._validate_topology(items, primitives)
        except (ValueError, TypeError):
            return False
        for item, primitive in zip(items, primitives, strict=True):
            updater._apply_primitive(item, primitive)
        return True
    if order >= 2:
        segments = tuple(
            bond_renderer.parallel_bond_segments(
                start.x(), start.y(), end.x(), end.y(), order, a_id, b_id
            )
        )
        return _set_line_segments(items, segments)
    return _set_line_segments(items, ((start.x(), start.y(), end.x(), end.y()),))


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
            pen_item = cast("Any", item)
            pen = QPen(pen_item.pen())
            pen.setColor(preview_color)
            pen_item.setPen(pen)
        if hasattr(item, "brush"):
            brush_item = cast("Any", item)
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
    "update_bond_preview_items",
]
