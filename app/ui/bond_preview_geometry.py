from __future__ import annotations

import math
from collections.abc import Sequence

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsLineItem

from ui.bond_style_logic import DOUBLE_STYLE_DEFAULT, DOUBLE_STYLE_OUTER

LineSegment = tuple[float, float, float, float]


def expanded_bold_segment(start: QPointF, end: QPointF, bond_length_px: float) -> LineSegment:
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


def trim_segment(segment: LineSegment, trim: float) -> LineSegment:
    if trim <= 1e-6:
        return segment
    x1, y1, x2, y2 = segment
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy) or 1.0
    ratio = min(0.45, trim / length)
    return (
        x1 + dx * ratio,
        y1 + dy * ratio,
        x2 - dx * ratio,
        y2 - dy * ratio,
    )


def scale_segment_offset(segment: LineSegment, base: LineSegment, scale: float) -> LineSegment:
    return (
        base[0] + (segment[0] - base[0]) * scale,
        base[1] + (segment[1] - base[1]) * scale,
        base[2] + (segment[2] - base[2]) * scale,
        base[3] + (segment[3] - base[3]) * scale,
    )


def plain_double_preview_segments(
    segments: Sequence[LineSegment],
    style: str,
) -> tuple[LineSegment, ...]:
    if len(segments) != 2:
        return tuple(segments)
    first, second = segments
    base_length = math.hypot(first[2] - first[0], first[3] - first[1]) or 1.0
    trim = max(1.0, base_length * 0.12)
    base = (
        (first[0] + second[0]) * 0.5,
        (first[1] + second[1]) * 0.5,
        (first[2] + second[2]) * 0.5,
        (first[3] + second[3]) * 0.5,
    )
    centered_scale = 1.1
    side_scale = 2.2
    if style == DOUBLE_STYLE_DEFAULT:
        return (base, trim_segment(scale_segment_offset(second, base, side_scale), trim))
    if style == DOUBLE_STYLE_OUTER:
        return (base, trim_segment(scale_segment_offset(first, base, side_scale), trim))
    return (
        scale_segment_offset(first, base, centered_scale),
        scale_segment_offset(second, base, centered_scale),
    )


def apply_plain_double_preview_variant(items: list, style: str) -> list:
    if len(items) != 2 or not all(isinstance(item, QGraphicsLineItem) for item in items):
        return items
    segments = (
        (
            items[0].line().x1(),
            items[0].line().y1(),
            items[0].line().x2(),
            items[0].line().y2(),
        ),
        (
            items[1].line().x1(),
            items[1].line().y1(),
            items[1].line().x2(),
            items[1].line().y2(),
        ),
    )
    for item, seg in zip(items, plain_double_preview_segments(segments, style), strict=False):
        item.setLine(*seg)
    return items


__all__ = [
    "LineSegment",
    "apply_plain_double_preview_variant",
    "expanded_bold_segment",
    "plain_double_preview_segments",
    "scale_segment_offset",
    "trim_segment",
]
