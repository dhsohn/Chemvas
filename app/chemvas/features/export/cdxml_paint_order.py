"""Relative paint order for straight strokes overlapping opaque filled rectangles."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET


def _coordinates(value: str, count: int) -> tuple[float, ...]:
    try:
        result = tuple(map(float, value.split()))
    except ValueError as exc:
        raise ValueError("CDXML paint geometry must be numeric") from exc
    if len(result) != count or not all(math.isfinite(n) for n in result):
        raise ValueError("CDXML paint geometry must be finite")
    return result


def line_overlaps_filled_rectangle(
    arrow: ET.Element, rectangle: ET.Element, width: str
) -> bool:
    """Positive-area overlap of the flat-capped stroke and the rectangle fill."""
    tx, ty, _ = _coordinates(arrow.get("Tail3D", ""), 3)
    hx, hy, _ = _coordinates(arrow.get("Head3D", ""), 3)
    stroke = _coordinates(width, 1)[0]
    length = math.hypot(hx - tx, hy - ty)
    if stroke <= 0 or length <= 1e-12:
        return False
    nx, ny = -(hy - ty) * stroke / (2 * length), (hx - tx) * stroke / (2 * length)
    line = [
        (tx + nx, ty + ny),
        (hx + nx, hy + ny),
        (hx - nx, hy - ny),
        (tx - nx, ty - ny),
    ]
    x1, y1, x2, y2 = _coordinates(rectangle.get("BoundingBox", ""), 4)
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    box = [(left, top), (right, top), (right, bottom), (left, bottom)]
    if right <= left or bottom <= top:
        return False
    # Separating-axis test avoids false overlap from a diagonal's bounding box.
    for polygon in (line, box):
        for p, q in zip(polygon, polygon[1:] + polygon[:1], strict=True):
            ax, ay = -(q[1] - p[1]), q[0] - p[0]
            size = math.hypot(ax, ay)
            if size <= 1e-12:
                continue
            ax, ay = ax / size, ay / size
            a = [x * ax + y * ay for x, y in line]
            b = [x * ax + y * ay for x, y in box]
            if min(max(a), max(b)) - max(min(a), min(b)) <= 1e-8:
                return False
    return True


def validate_relative_order(
    source_line: ET.Element,
    source_fill: ET.Element,
    native_line: ET.Element,
    native_fill: ET.Element,
) -> None:
    """Z may be renumbered, but an overlapping pair cannot swap or become tied."""
    try:
        old = int(source_line.get("Z", "0")) - int(source_fill.get("Z", "0"))
        new = int(native_line.get("Z", "0")) - int(native_fill.get("Z", "0"))
    except ValueError as exc:
        raise ValueError("CDXML paint order must use integer Z values") from exc
    if old == 0 or new == 0 or (old > 0) != (new > 0):
        raise ValueError("CDXML consumer reference changed overlapping paint order")
