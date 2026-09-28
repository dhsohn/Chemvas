"""Geometry helpers for free decorative shapes (circle/ellipse/rounded rect/rect).

A shape is stored as a single ``QGraphicsPathItem`` whose path is rebuilt from a
bounding ``QRectF`` plus a shape kind. Keeping the path math here lets the build,
restore, and resize paths share one source of truth and stay unit-testable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QPainterPath

# Order is the order shown in the option bar.
SHAPE_KINDS: tuple[str, ...] = ("circle", "ellipse", "rounded_rect", "rect")
DEFAULT_SHAPE_KIND = "circle"

# "none" removes the outline entirely, for borderless background panels; the
# drag preview substitutes a dashed guide so drawing one stays visible.
STROKE_STYLES: tuple[str, ...] = ("solid", "dashed", "dotted", "none")
DEFAULT_STROKE_STYLE = "solid"

# Corner radius of a rounded rectangle as a fraction of its shorter side.
_ROUNDED_CORNER_FRACTION = 0.28
_ROUNDED_CORNER_MAX = 18.0


def normalized_shape_kind(value: object, *, default: str = DEFAULT_SHAPE_KIND) -> str:
    return value if isinstance(value, str) and value in SHAPE_KINDS else default


def normalized_stroke_style(
    value: object, *, default: str = DEFAULT_STROKE_STYLE
) -> str:
    return value if isinstance(value, str) and value in STROKE_STYLES else default


def pen_style_for_stroke(stroke_style: object) -> Qt.PenStyle:
    from PyQt6.QtCore import Qt

    return {
        "solid": Qt.PenStyle.SolidLine,
        "dashed": Qt.PenStyle.DashLine,
        "dotted": Qt.PenStyle.DotLine,
        "none": Qt.PenStyle.NoPen,
    }[normalized_stroke_style(stroke_style)]


def shape_rect_from_points(
    start: tuple[float, float], end: tuple[float, float], bond_length: float
) -> tuple[float, float, float, float]:
    left, right = sorted((start[0], end[0]))
    top, bottom = sorted((start[1], end[1]))
    width, height = right - left, bottom - top
    min_size = bond_length * 1.2
    if width < 4.0 and height < 4.0:
        return start[0] - min_size / 2, start[1] - min_size / 2, min_size, min_size
    return left, top, width, height


def shape_outline(
    x: float, y: float, width: float, height: float, shape_kind: object
) -> tuple[str, float, float, float, float, float]:
    """Original outline geometry; Qt/SVG only materialize its ellipse or rectangle."""
    kind = normalized_shape_kind(shape_kind)
    radius = 0.0
    if kind == "circle":
        diameter = min(width, height)
        x, y = x + width / 2 - diameter / 2, y + height / 2 - diameter / 2
        width = height = diameter
        kind = "ellipse"
    elif kind == "rounded_rect":
        radius = min(_ROUNDED_CORNER_MAX, min(width, height) * _ROUNDED_CORNER_FRACTION)
        kind = "rect"
    return kind, x, y, width, height, radius


def shape_stroke_width(bond_line_width: float) -> float:
    return max(1.4, bond_line_width)


def shape_path(rect: QRectF, shape_kind: object) -> QPainterPath:
    """Build the outline path for ``shape_kind`` inside ``rect``."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPainterPath

    bounds = QRectF(rect).normalized()
    kind, x, y, width, height, radius = shape_outline(
        bounds.x(), bounds.y(), bounds.width(), bounds.height(), shape_kind
    )
    bounds = QRectF(x, y, width, height)
    path = QPainterPath()
    if kind == "ellipse":
        path.addEllipse(bounds)
    elif radius:
        path.addRoundedRect(bounds, radius, radius)
    else:
        path.addRect(bounds)
    return path


__all__ = [
    "DEFAULT_SHAPE_KIND",
    "DEFAULT_STROKE_STYLE",
    "SHAPE_KINDS",
    "STROKE_STYLES",
    "normalized_shape_kind",
    "normalized_stroke_style",
    "pen_style_for_stroke",
    "shape_outline",
    "shape_path",
    "shape_rect_from_points",
    "shape_stroke_width",
]
