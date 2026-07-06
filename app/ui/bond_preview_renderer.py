from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
)

from ui.bond_preview_geometry import (
    LineSegment,
    apply_plain_double_preview_variant,
    expanded_bold_segment,
    plain_double_preview_segments,
)
from ui.bond_preview_scene_items import add_bond_preview_items, clear_bond_preview_items
from ui.bond_style_logic import (
    PLAIN_DOUBLE_STYLES,
    normalized_plain_double_style,
)
from ui.graphics_items import NoSelectLineItem


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
    draw_dotted_bond: Callable[[float, float, float, float, int | None, int | None], list]
    draw_parallel_bonds: Callable[[float, float, float, float, int, int | None, int | None], list]
    line_normal: Callable[[float, float, float, float, QPointF | None], tuple[float, float]]
    one_sided_bond_strip: Callable[[float, float, float, float, float, float, float, float], Any]
    bond_pen: Callable[[], QPen]
    dotted_bond_pen: Callable[[], QPen]


@dataclass(frozen=True)
class BondPreviewUpdateResolvers:
    wedge_polygon: Callable[[float, float, float, float, int | None, int | None], QPolygonF]
    hash_segments: Callable[[float, float, float, float, int, int | None, int | None], Sequence[LineSegment]]
    dotted_bond_path: Callable[[float, float, float, float, int | None, int | None], Any]
    parallel_bond_segments: Callable[[float, float, float, float, int, int | None, int | None], Sequence[LineSegment]]
    line_normal: Callable[[float, float, float, float, QPointF | None], tuple[float, float]]
    strip_polygon: Callable[[float, float, float, float, float, float, float, float], QPolygonF]


def _set_line_segments(items: Sequence, segments: Sequence[LineSegment]) -> bool:
    """Apply segments 1:1 onto line items; False on any count/type mismatch."""
    if len(items) != len(segments):
        return False
    for item, segment in zip(items, segments, strict=False):
        if not isinstance(item, QGraphicsLineItem):
            return False
        item.setLine(*segment)
    return True


def _bold_normal(line_normal, segment: LineSegment, bold_outward: bool) -> tuple[float, float]:
    nx, ny = line_normal(segment[0], segment[1], segment[2], segment[3], None)
    if bold_outward:
        return -nx, -ny
    return nx, ny


def _bold_strip_item(
    segment: LineSegment,
    *,
    config: BondPreviewConfig,
    resolvers: BondPreviewBuildResolvers,
    bold_outward: bool,
):
    nx, ny = _bold_normal(resolvers.line_normal, segment, bold_outward)
    return resolvers.one_sided_bond_strip(
        segment[0],
        segment[1],
        segment[2],
        segment[3],
        nx,
        ny,
        config.bond_line_width,
        config.bold_bond_width,
    )


def _update_bold_first_item(
    first,
    segment: LineSegment,
    *,
    config: BondPreviewConfig,
    resolvers: BondPreviewUpdateResolvers,
    bold_outward: bool,
) -> bool:
    x1, y1, x2, y2 = segment
    nx, ny = _bold_normal(resolvers.line_normal, segment, bold_outward)
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
                config.bold_bond_width,
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
    if style == "dotted":
        return resolvers.draw_dotted_bond(start.x(), start.y(), end.x(), end.y(), a_id, b_id)
    if style in {"bold", "bold_in", "bold_out"}:
        bold_outward = style == "bold_out"
        if order >= 2:
            items = resolvers.draw_parallel_bonds(start.x(), start.y(), end.x(), end.y(), order, a_id, b_id)
            if items and isinstance(items[0], QGraphicsLineItem):
                line = items[0].line()
                items[0] = _bold_strip_item(
                    (line.x1(), line.y1(), line.x2(), line.y2()),
                    config=config,
                    resolvers=resolvers,
                    bold_outward=bold_outward,
                )
            return items
        segment = expanded_bold_segment(start, end, config.bond_length_px)
        return [_bold_strip_item(segment, config=config, resolvers=resolvers, bold_outward=bold_outward)]
    if order == 2 and style in PLAIN_DOUBLE_STYLES:
        items = resolvers.draw_parallel_bonds(start.x(), start.y(), end.x(), end.y(), order, a_id, b_id)
        return apply_plain_double_preview_variant(
            items,
            normalized_plain_double_style(style, order),
        )
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
        return _set_line_segments(items, segments)
    if style == "dotted":
        if len(items) != 1 or not isinstance(items[0], QGraphicsPathItem):
            return False
        items[0].setPath(resolvers.dotted_bond_path(start.x(), start.y(), end.x(), end.y(), a_id, b_id))
        return True
    if style in {"bold", "bold_in", "bold_out"}:
        bold_outward = style == "bold_out"
        if order >= 2:
            segments = tuple(resolvers.parallel_bond_segments(start.x(), start.y(), end.x(), end.y(), order, a_id, b_id))
            if not segments or len(items) != len(segments):
                return False
            if not _update_bold_first_item(
                items[0],
                segments[0],
                config=config,
                resolvers=resolvers,
                bold_outward=bold_outward,
            ):
                return False
            return _set_line_segments(items[1:], segments[1:])
        segment = expanded_bold_segment(start, end, config.bond_length_px)
        return _update_bold_first_item(
            items[0],
            segment,
            config=config,
            resolvers=resolvers,
            bold_outward=bold_outward,
        )
    if order == 2 and style in PLAIN_DOUBLE_STYLES:
        segments = tuple(resolvers.parallel_bond_segments(start.x(), start.y(), end.x(), end.y(), order, a_id, b_id))
        updated_segments = plain_double_preview_segments(
            segments,
            normalized_plain_double_style(style, order),
        )
        return _set_line_segments(items, updated_segments)
    if order >= 2:
        segments = tuple(resolvers.parallel_bond_segments(start.x(), start.y(), end.x(), end.y(), order, a_id, b_id))
        return _set_line_segments(items, segments)
    return _set_line_segments(items, ((start.x(), start.y(), end.x(), end.y()),))


__all__ = [
    "BondPreviewBuildResolvers",
    "BondPreviewConfig",
    "BondPreviewUpdateResolvers",
    "add_bond_preview_items",
    "build_bond_preview_items",
    "clear_bond_preview_items",
    "update_bond_preview_items",
]
