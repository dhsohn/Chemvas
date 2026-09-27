from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
)

# The accent a handle is outlined with, and the fill of one that has taken
# hold of another item's endpoint.
HANDLE_ACCENT_COLOR = "#0d9488"
# Handles are an input affordance, so their size is a distance on screen
# rather than in the document: a corner or endpoint handle is this wide at
# any zoom, and an edge-midpoint resize handle is the smaller one.
HANDLE_SCREEN_PX = 8.0
EDGE_HANDLE_SCREEN_PX = 6.0
# The rotation knob sits this far above its selection frame, on a stem.
ROTATION_HANDLE_STEM_PX = 14.0
ROTATION_HANDLE_TYPE = "selection_rotate"

_EDGE_HANDLE_TYPES = frozenset({"shape_n", "shape_e", "shape_s", "shape_w"})
# A curved arrow's control handle keeps the curve's midpoint within this
# fraction of its chord from the chord's midpoint.
_CURVE_MIDPOINT_REACH_RATIO = 0.8


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


def rotation_drag_angle(
    center: QPointF,
    start: QPointF,
    pos: QPointF,
    *,
    snap_step: float | None = None,
) -> float:
    """Degrees the pointer has swept around ``center`` since ``start``.

    Positive is clockwise on screen (y grows downward). ``snap_step``
    rounds the sweep to that many degrees, for a Shift-constrained drag.
    """
    start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
    angle = math.atan2(pos.y() - center.y(), pos.x() - center.x())
    sweep = math.degrees(angle - start_angle)
    sweep = (sweep + 180.0) % 360.0 - 180.0
    if snap_step:
        sweep = round(sweep / snap_step) * snap_step
    return sweep


def selection_frame_applies(atom_count: int, rotatable_item_count: int) -> bool:
    """Whether a selection gets a frame with a rotation handle.

    Rotation only means something for two or more atoms, or for an item
    that turns about its own centre; a lone atom has nothing to rotate.
    """
    return atom_count >= 2 or rotatable_item_count >= 1


def shape_resize_handle_positions(rect: QRectF) -> list[tuple[str, QPointF]]:
    """Eight resize handles (corners + edge midpoints) around ``rect``."""
    bounds = QRectF(rect).normalized()
    left, top, right, bottom = (
        bounds.left(),
        bounds.top(),
        bounds.right(),
        bounds.bottom(),
    )
    cx, cy = bounds.center().x(), bounds.center().y()
    return [
        ("shape_nw", QPointF(left, top)),
        ("shape_n", QPointF(cx, top)),
        ("shape_ne", QPointF(right, top)),
        ("shape_e", QPointF(right, cy)),
        ("shape_se", QPointF(right, bottom)),
        ("shape_s", QPointF(cx, bottom)),
        ("shape_sw", QPointF(left, bottom)),
        ("shape_w", QPointF(left, cy)),
    ]


def resized_shape_rect(
    rect: QRectF, anchor: str, pos: QPointF, *, min_size: float = 8.0
) -> QRectF:
    """Return ``rect`` with the edge/corner named by ``anchor`` moved to ``pos``."""
    bounds = QRectF(rect).normalized()
    left, top, right, bottom = (
        bounds.left(),
        bounds.top(),
        bounds.right(),
        bounds.bottom(),
    )
    direction = anchor.removeprefix("shape_")
    if "w" in direction:
        left = min(pos.x(), right - min_size)
    if "e" in direction:
        right = max(pos.x(), left + min_size)
    if "n" in direction:
        top = min(pos.y(), bottom - min_size)
    if "s" in direction:
        bottom = max(pos.y(), top + min_size)
    return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()


def orbital_handle_positions(
    center: QPointF, base_dist: float
) -> tuple[QPointF, QPointF]:
    return (
        QPointF(center.x() + base_dist, center.y()),
        QPointF(center.x(), center.y() - base_dist),
    )


def orbital_scale_factor(
    center: QPointF,
    pos: QPointF,
    base_dist: float,
    *,
    minimum_scale: float = 0.2,
) -> float:
    safe_base_dist = max(float(base_dist), 1e-6)
    dist = math.hypot(pos.x() - center.x(), pos.y() - center.y())
    return max(minimum_scale, dist / safe_base_dist)


def orbital_rotation_angle(
    center: QPointF,
    pos: QPointF,
    *,
    snap_enabled: bool,
    snap_step: int,
) -> float:
    angle = math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()))
    if snap_enabled:
        step = max(1, int(snap_step))
        angle = round(angle / step) * step
    return angle


def default_curved_control(start: QPointF, end: QPointF) -> QPointF:
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    return QPointF(
        start.x() + dx * 0.5 + nx * length * 0.3,
        start.y() + dy * 0.5 + ny * length * 0.3,
    )


def curved_midpoint(start: QPointF, control: QPointF, end: QPointF) -> QPointF:
    return QPointF(
        0.25 * start.x() + 0.5 * control.x() + 0.25 * end.x(),
        0.25 * start.y() + 0.5 * control.y() + 0.25 * end.y(),
    )


def control_from_midpoint(start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
    return QPointF(
        2.0 * mid.x() - 0.5 * (start.x() + end.x()),
        2.0 * mid.y() - 0.5 * (start.y() + end.y()),
    )


def control_with_moved_end(
    anchor: QPointF, pressed_end: QPointF, moved_end: QPointF, control: QPointF
) -> QPointF:
    """``control`` carried along as a chord's free end moves about ``anchor``.

    The chord from ``anchor`` to ``pressed_end`` turns and scales onto the
    chord to ``moved_end``, and the control turns and scales with it, so the
    curve keeps its shape. An unmoved end returns ``control`` bit for bit. A
    chord of zero length has no direction to turn, so its control stays put.

    A file can hold a bulge many times its chord, and scaling that with a
    growing chord would throw the control out by the length ratio. So the
    carried control reaches from the chord's midpoint no further than the
    larger of the reach the control handle allows on the new chord and the
    reach at the press. Every curve the control handle can draw keeps its shape.
    """
    pressed_x = pressed_end.x() - anchor.x()
    pressed_y = pressed_end.y() - anchor.y()
    length_sq = pressed_x * pressed_x + pressed_y * pressed_y
    if length_sq <= 0.0:
        return QPointF(control)
    moved_x = moved_end.x() - anchor.x()
    moved_y = moved_end.y() - anchor.y()
    # moved / pressed as complex numbers: the turn, scaled by the length ratio.
    # For an unmoved end the first numerator repeats ``length_sq`` exactly and
    # the second cancels to zero.
    scaled_cos = (moved_x * pressed_x + moved_y * pressed_y) / length_sq
    scaled_sin = (moved_y * pressed_x - moved_x * pressed_y) / length_sq
    offset_x = control.x() - anchor.x()
    offset_y = control.y() - anchor.y()
    # Add the change to ``control`` instead of rebuilding it from ``anchor``:
    # anchor + (control - anchor) can round away from control.
    carried = QPointF(
        control.x() + (scaled_cos - 1.0) * offset_x - scaled_sin * offset_y,
        control.y() + scaled_sin * offset_x + (scaled_cos - 1.0) * offset_y,
    )
    # The curve's midpoint lies halfway between the chord's midpoint and the
    # control, so the control may reach twice as far as the midpoint. An
    # unmoved end repeats the press-time reach bit for bit and is not limited.
    moved_mid = _chord_midpoint(anchor, moved_end)
    reach = carried - moved_mid
    reach_length = math.hypot(reach.x(), reach.y())
    pressed_reach = control - _chord_midpoint(anchor, pressed_end)
    reach_limit = max(
        2.0 * _CURVE_MIDPOINT_REACH_RATIO * math.hypot(moved_x, moved_y),
        math.hypot(pressed_reach.x(), pressed_reach.y()),
    )
    if reach_length <= reach_limit:
        return carried
    return moved_mid + reach * (reach_limit / reach_length)


def _chord_midpoint(start: QPointF, end: QPointF) -> QPointF:
    return QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)


def clamp_curved_midpoint(
    start: QPointF,
    end: QPointF,
    mid: QPointF,
    *,
    snap_enabled: bool,
    snap_distance: float | None,
) -> QPointF:
    chord_mid = QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    v = QPointF(mid.x() - chord_mid.x(), mid.y() - chord_mid.y())
    offset = v.x() * nx + v.y() * ny
    if snap_enabled and snap_distance is not None and snap_distance > 0:
        offset = round(offset / snap_distance) * snap_distance
    max_offset = length * _CURVE_MIDPOINT_REACH_RATIO
    offset = max(-max_offset, min(max_offset, offset))
    return QPointF(chord_mid.x() + nx * offset, chord_mid.y() + ny * offset)


__all__ = [
    "EDGE_HANDLE_SCREEN_PX",
    "HANDLE_ACCENT_COLOR",
    "HANDLE_SCREEN_PX",
    "ROTATION_HANDLE_STEM_PX",
    "ROTATION_HANDLE_TYPE",
    "clamp_curved_midpoint",
    "control_from_midpoint",
    "control_with_moved_end",
    "create_handle_item",
    "create_rotation_handle_item",
    "curved_midpoint",
    "default_curved_control",
    "mark_handle_snapped",
    "orbital_handle_positions",
    "orbital_rotation_angle",
    "orbital_scale_factor",
    "resized_shape_rect",
    "rotation_drag_angle",
    "selection_frame_applies",
    "shape_resize_handle_positions",
]
