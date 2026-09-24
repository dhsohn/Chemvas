"""Geometry helpers for free decorative shapes (circle/ellipse/rounded rect/rect).

A shape is stored as a single ``QGraphicsPathItem`` whose path is rebuilt from a
bounding ``QRectF`` plus a shape kind. Keeping the path math here lets the build,
restore, and resize paths share one source of truth and stay unit-testable.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainterPath

# Order is the order shown in the option bar.
SHAPE_KINDS: tuple[str, ...] = ("circle", "ellipse", "rounded_rect", "rect")
DEFAULT_SHAPE_KIND = "circle"

# "none" removes the outline entirely, for borderless background panels; the
# drag preview substitutes a dashed guide so drawing one stays visible.
STROKE_STYLES: tuple[str, ...] = ("solid", "dashed", "dotted", "none")
DEFAULT_STROKE_STYLE = "solid"

_PEN_STYLE_BY_STROKE: dict[str, Qt.PenStyle] = {
    "solid": Qt.PenStyle.SolidLine,
    "dashed": Qt.PenStyle.DashLine,
    "dotted": Qt.PenStyle.DotLine,
    "none": Qt.PenStyle.NoPen,
}

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
    return _PEN_STYLE_BY_STROKE[normalized_stroke_style(stroke_style)]


def shape_path(rect: QRectF, shape_kind: object) -> QPainterPath:
    """Build the outline path for ``shape_kind`` inside ``rect``."""
    kind = normalized_shape_kind(shape_kind)
    bounds = QRectF(rect).normalized()
    path = QPainterPath()
    if kind == "circle":
        diameter = min(bounds.width(), bounds.height())
        center = bounds.center()
        square = QRectF(
            center.x() - diameter / 2.0,
            center.y() - diameter / 2.0,
            diameter,
            diameter,
        )
        path.addEllipse(square)
    elif kind == "ellipse":
        path.addEllipse(bounds)
    elif kind == "rounded_rect":
        radius = min(
            _ROUNDED_CORNER_MAX,
            min(bounds.width(), bounds.height()) * _ROUNDED_CORNER_FRACTION,
        )
        path.addRoundedRect(bounds, radius, radius)
    else:  # "rect"
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
    "shape_path",
]
