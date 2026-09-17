"""A shape is its record; the graphics item draws it.

Every edit computes a new ``Shape`` and hands it to ``set_shape_record_for``,
which stores the canonical record and renders the item from it. Every read of
a shape's state comes from the record. The item keeps its identity, because
history and recovery hold on to it, but it is no longer asked what the shape
is: an attached shape without a valid record is an error, not something to
reconstruct from paint.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QGraphicsPathItem

from chemvas.domain.document import (
    Shape,
    normalized_shape,
    shape_from_state,
    shape_to_state,
)
from chemvas.features.annotations import shape_path
from chemvas.ui.canvas_shape_state import shape_state_for
from chemvas.ui.scene_decoration_build_access import shape_pen_for
from chemvas.ui.scene_item_state_serialization import shape_state_dict

if TYPE_CHECKING:
    from collections.abc import Mapping

# Roles 0-2 carry an item's kind and payloads; the shape id has its own.
SHAPE_ID_ROLE = 3


def _is_deleted(item: Any) -> bool:
    try:
        return sip.isdeleted(item)
    except TypeError:
        # Not a Qt wrapper at all; nothing Qt could have destroyed.
        return False


def _is_shape_item(item: Any) -> bool:
    return (
        isinstance(item, QGraphicsPathItem)
        and not _is_deleted(item)
        and item.data(0) == "shape"
    )


def shape_id_for_item(item: Any) -> int | None:
    shape_id = item.data(SHAPE_ID_ROLE)
    return shape_id if type(shape_id) is int else None


def shape_record_for(canvas: Any, item: Any) -> Shape | None:
    shape_id = shape_id_for_item(item)
    if shape_id is None:
        return None
    return shape_state_for(canvas).records.get(shape_id)


def require_shape_record_for(canvas: Any, item: Any) -> Shape:
    record = shape_record_for(canvas, item)
    if record is None:
        raise RuntimeError("shape item has no record; its state cannot be read")
    return record


def shape_rect_of(shape: Shape) -> QRectF:
    return QRectF(QPointF(shape.left, shape.top), QPointF(shape.right, shape.bottom))


def shape_with_rect(shape: Shape, rect: QRectF) -> Shape:
    return replace(
        shape,
        left=rect.left(),
        top=rect.top(),
        right=rect.right(),
        bottom=rect.bottom(),
    )


def render_shape_item(canvas: Any, item: Any, shape: Shape) -> None:
    """Make the item look like ``shape``.

    Every edit paints through here. The build service paints a new item once
    when it creates it, and an exact rollback snapshot puts paint back together
    with the record it captured.
    """
    rect = shape_rect_of(shape)
    item.setPath(shape_path(rect, shape.shape_kind))
    item.setPen(shape_pen_for(canvas, shape.stroke_style))
    if shape.fill is None:
        # A transparent solid fill keeps the interior clickable while painting
        # nothing.
        fill = QColor(0, 0, 0, 0)
    else:
        fill = QColor(shape.fill)
        fill.setAlphaF(1.0 if shape.fill_alpha is None else shape.fill_alpha)
    item.setBrush(QBrush(fill))
    item.setData(0, "shape")
    # Still mirrored for the few places that read geometry off the item.
    item.setData(
        1,
        {
            "rect": rect,
            "shape_kind": shape.shape_kind,
            "stroke_style": shape.stroke_style,
        },
    )


def set_shape_record_for(canvas: Any, item: Any, shape: Shape) -> Shape:
    """Store the canonical form of ``shape`` for ``item`` and draw it."""
    state = shape_state_for(canvas)
    shape_id = shape_id_for_item(item)
    if shape_id is None:
        shape_id = state.next_shape_id
        state.next_shape_id += 1
        item.setData(SHAPE_ID_ROLE, shape_id)
    else:
        # An item that already carries an id must never meet a fresh one.
        state.next_shape_id = max(state.next_shape_id, shape_id + 1)
    record = normalized_shape(shape)
    state.records[shape_id] = record
    render_shape_item(canvas, item, record)
    return record


def record_shape_state(canvas: Any, item: Any, state: Mapping[str, object]) -> Shape:
    return set_shape_record_for(
        canvas, item, shape_from_state(state, error="Invalid shape.")
    )


def adopt_shape_item_for(canvas: Any, item: Any) -> None:
    """Give a freshly built item its record, once, from what it was built as.

    Items that arrive from a state (open, paste, undo re-creation) already have
    their record. A shape drawn with the tool is built from a rectangle and the
    tool settings, and this is where those become its record. Nothing is
    derived from an item afterwards.
    """
    if not _is_shape_item(item) or shape_record_for(canvas, item) is not None:
        return
    record_shape_state(canvas, item, shape_state_dict(item))


def shape_state_from_record_for(canvas: Any, item: Any) -> dict[str, object]:
    return shape_to_state(require_shape_record_for(canvas, item))


def clear_shape_records_for(canvas: Any) -> None:
    state = shape_state_for(canvas)
    state.records = {}
    state.next_shape_id = 1


__all__ = [
    "SHAPE_ID_ROLE",
    "adopt_shape_item_for",
    "clear_shape_records_for",
    "record_shape_state",
    "render_shape_item",
    "require_shape_record_for",
    "set_shape_record_for",
    "shape_id_for_item",
    "shape_record_for",
    "shape_rect_of",
    "shape_state_from_record_for",
    "shape_with_rect",
]
