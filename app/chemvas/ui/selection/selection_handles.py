from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
)

from chemvas.features.rendering import (
    clamp_curved_midpoint as clamp_curved_midpoint_coordinates,
)
from chemvas.features.rendering import (
    control_from_midpoint as control_from_midpoint_coordinates,
)
from chemvas.features.rendering import (
    curved_midpoint as curved_midpoint_coordinates,
)
from chemvas.features.selection import (
    orbital_handle_positions as orbital_handle_coordinates,
)
from chemvas.ui.annotations.shape_geometry import (
    EDGE_HANDLE_SCREEN_PX,
    resized_shape_bounds,
    shape_handle_positions,
)
from chemvas.ui.window.main_window_config import (
    HANDLE_ACCENT_COLOR,
    HANDLE_SCREEN_PX,
    ROTATION_HANDLE_STEM_PX,
    ROTATION_HANDLE_TYPE,
)

_EDGE_HANDLE_TYPES = frozenset({"shape_n", "shape_e", "shape_s", "shape_w"})


def _style_handle(handle: QAbstractGraphicsShapeItem, handle_type: str) -> None:
    handle.setBrush(QBrush(QColor("#ffffff")))
    pen = QPen(QColor(HANDLE_ACCENT_COLOR))
    pen.setWidthF(1.5)
    pen.setCosmetic(True)
    handle.setPen(pen)
    handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
    handle.setData(0, "handle")
    handle.setData(1, handle_type)
    handle.setZValue(30)


def create_handle_item(
    pos: QPointF,
    handle_type: str,
    target: object,
) -> QGraphicsEllipseItem:
    """A hollow circle at ``pos`` that keeps its size on screen at any zoom.

    The item's own geometry is centred on its origin and ignores the view
    transform, so ``pos()`` is the point it grips.
    """
    size = (
        EDGE_HANDLE_SCREEN_PX if handle_type in _EDGE_HANDLE_TYPES else HANDLE_SCREEN_PX
    )
    half = size / 2.0
    handle = QGraphicsEllipseItem(-half, -half, size, size)
    _style_handle(handle, handle_type)
    handle.setData(2, target)
    handle.setPos(pos)
    return handle


def create_rotation_handle_item(anchor: QPointF) -> QGraphicsPathItem:
    """The rotation knob above a selection frame: a stem and a circle.

    ``anchor`` is the frame's top-centre; the knob is drawn in screen
    pixels above it so it never shrinks away at a distant zoom.
    """
    path = QPainterPath(QPointF(0.0, 0.0))
    path.lineTo(0.0, -ROTATION_HANDLE_STEM_PX)
    radius = HANDLE_SCREEN_PX / 2.0
    path.addEllipse(QPointF(0.0, -ROTATION_HANDLE_STEM_PX - radius), radius, radius)
    handle = QGraphicsPathItem(path)
    _style_handle(handle, ROTATION_HANDLE_TYPE)
    handle.setData(2, None)
    handle.setPos(anchor)
    return handle


def mark_handle_snapped(handle: QAbstractGraphicsShapeItem) -> None:
    """Fill a handle that is sitting on another item's endpoint.

    A hollow handle is free, a filled one has taken hold; that is the
    difference a drag needs to see without stopping to look.
    """
    handle.setBrush(QBrush(QColor(HANDLE_ACCENT_COLOR)))


def shape_resize_handle_positions(rect: QRectF) -> list[tuple[str, QPointF]]:
    """Eight resize handles (corners + edge midpoints) around ``rect``."""
    bounds = QRectF(rect).normalized()
    return [
        (name, QPointF(*point))
        for name, point in shape_handle_positions(
            (bounds.left(), bounds.top(), bounds.right(), bounds.bottom())
        )
    ]


def resized_shape_rect(
    rect: QRectF, anchor: str, pos: QPointF, *, min_size: float = 8.0
) -> QRectF:
    """Materialize the shared original resize calculation as a Qt rectangle."""
    bounds = QRectF(rect).normalized()
    left, top, right, bottom = resized_shape_bounds(
        (bounds.left(), bounds.top(), bounds.right(), bounds.bottom()),
        anchor,
        (pos.x(), pos.y()),
        min_size=min_size,
    )
    return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()


def orbital_handle_positions(
    center: QPointF, base_dist: float
) -> tuple[QPointF, QPointF]:
    scale, rotate = orbital_handle_coordinates((center.x(), center.y()), base_dist)
    return QPointF(*scale), QPointF(*rotate)


def curved_midpoint(start: QPointF, control: QPointF, end: QPointF) -> QPointF:
    return QPointF(
        *curved_midpoint_coordinates(
            (start.x(), start.y()), (control.x(), control.y()), (end.x(), end.y())
        )
    )


def control_from_midpoint(start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
    return QPointF(
        *control_from_midpoint_coordinates(
            (start.x(), start.y()), (end.x(), end.y()), (mid.x(), mid.y())
        )
    )


def clamp_curved_midpoint(
    start: QPointF,
    end: QPointF,
    mid: QPointF,
    *,
    snap_enabled: bool,
    snap_distance: float | None,
) -> QPointF:
    return QPointF(
        *clamp_curved_midpoint_coordinates(
            (start.x(), start.y()),
            (end.x(), end.y()),
            (mid.x(), mid.y()),
            snap_enabled=snap_enabled,
            snap_distance=snap_distance,
        )
    )


__all__ = [
    "clamp_curved_midpoint",
    "control_from_midpoint",
    "create_handle_item",
    "create_rotation_handle_item",
    "curved_midpoint",
    "mark_handle_snapped",
    "orbital_handle_positions",
    "resized_shape_rect",
    "shape_resize_handle_positions",
]
