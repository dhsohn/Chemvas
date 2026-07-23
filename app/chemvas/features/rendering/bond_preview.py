from __future__ import annotations

import math
from collections.abc import Sequence

from .bond_style import DOUBLE_STYLE_DEFAULT, DOUBLE_STYLE_OUTER

LineSegment = tuple[float, float, float, float]


def _trim_segment(segment: LineSegment, trim: float) -> LineSegment:
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


def _scale_segment_offset(
    segment: LineSegment, base: LineSegment, scale: float
) -> LineSegment:
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
        return (
            base,
            _trim_segment(_scale_segment_offset(second, base, side_scale), trim),
        )
    if style == DOUBLE_STYLE_OUTER:
        return (
            base,
            _trim_segment(_scale_segment_offset(first, base, side_scale), trim),
        )
    return (
        _scale_segment_offset(first, base, centered_scale),
        _scale_segment_offset(second, base, centered_scale),
    )


__all__ = ["plain_double_preview_segments"]
