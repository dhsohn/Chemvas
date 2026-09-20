"""A shape is its record; the graphics item draws it.

Every edit computes a new ``Shape`` and hands it to ``set_shape_record_for``,
which stores the canonical record and renders the item from it. Every read of
a shape's state comes from the record. The item keeps its identity, because
history and recovery hold on to it, and carries nothing but its kind and its
id: it cannot be asked what the shape is, and an item without a record cannot
join the document's shapes.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any
from weakref import finalize

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
from chemvas.ui.scene_record_ids import new_scene_record_id
from chemvas.ui.scene_render_access import scene_render_context_for

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.ui.canvas_shape_state import CanvasShapeState
    from chemvas.ui.scene_render_context import SceneRenderContext

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


def shape_record(context: SceneRenderContext, item: Any) -> Shape | None:
    shape_id = shape_id_for_item(item)
    if shape_id is None:
        return None
    return context.state.shape_state.records.get(shape_id)


def require_shape_record(context: SceneRenderContext, item: Any) -> Shape:
    record = shape_record(context, item)
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


def render_shape_item(context: SceneRenderContext, item: Any, shape: Shape) -> None:
    """Make the item look like ``shape``.

    Every edit paints through here. The build service paints a new item once
    when it creates it, and an exact rollback snapshot puts paint back together
    with the record it captured.
    """
    rect = shape_rect_of(shape)
    item.setPath(shape_path(rect, shape.shape_kind))
    item.setPen(context.decorations.shape_pen(shape.stroke_style))
    if shape.fill is None:
        # A transparent solid fill keeps the interior clickable while painting
        # nothing.
        fill = QColor(0, 0, 0, 0)
    else:
        fill = QColor(shape.fill)
        fill.setAlphaF(1.0 if shape.fill_alpha is None else shape.fill_alpha)
    item.setBrush(QBrush(fill))
    item.setData(0, "shape")


def set_shape_record(context: SceneRenderContext, item: Any, shape: Shape) -> Shape:
    """Store the canonical form of ``shape`` for ``item`` and draw it."""
    record = normalized_shape(shape)
    state = context.state.shape_state
    shape_id = shape_id_for_item(item)
    new_record = shape_id is None
    if shape_id is None:
        shape_id = new_scene_record_id()
        item.setData(SHAPE_ID_ROLE, shape_id)
        finalize(item, _discard_shape_record, state, shape_id)
    state.records[shape_id] = record
    try:
        render_shape_item(context, item, record)
    except Exception:
        if new_record:
            _discard_shape_record(state, shape_id)
        raise
    return record


def shape_record_for(canvas: Any, item: Any) -> Shape | None:
    return shape_record(scene_render_context_for(canvas), item)


def require_shape_record_for(canvas: Any, item: Any) -> Shape:
    return require_shape_record(scene_render_context_for(canvas), item)


def set_shape_record_for(canvas: Any, item: Any, shape: Shape) -> Shape:
    return set_shape_record(scene_render_context_for(canvas), item, shape)


def require_attached_shape_record_for(canvas: Any, item: Any) -> None:
    """An item may join the document's shapes only with its record in place."""
    if _is_shape_item(item) and shape_record_for(canvas, item) is None:
        raise RuntimeError("shape item attached without a record")


def record_shape_state(canvas: Any, item: Any, state: Mapping[str, object]) -> Shape:
    return set_shape_record_for(
        canvas, item, shape_from_state(state, error="Invalid shape.")
    )


def shape_state_from_record_for(canvas: Any, item: Any) -> dict[str, object]:
    return shape_to_state(require_shape_record_for(canvas, item))


def clear_shape_records_for(canvas: Any) -> None:
    """Forget every record. Ids are never reused, so a stray item cannot alias."""
    shape_state_for(canvas).records = {}


def _discard_shape_record(state: CanvasShapeState, shape_id: int) -> None:
    # Clear and rollback may replace the mapping. Retain the state, never a
    # particular dictionary or the item whose finalizer calls this function.
    state.records.pop(shape_id, None)


def discard_shape_record_for(canvas: Any, shape_id: int) -> None:
    """Remove the record created by a failed add, even if its item is still held."""
    _discard_shape_record(shape_state_for(canvas), shape_id)


__all__ = [
    "SHAPE_ID_ROLE",
    "clear_shape_records_for",
    "discard_shape_record_for",
    "record_shape_state",
    "render_shape_item",
    "require_attached_shape_record_for",
    "require_shape_record",
    "require_shape_record_for",
    "set_shape_record",
    "set_shape_record_for",
    "shape_id_for_item",
    "shape_record",
    "shape_record_for",
    "shape_rect_of",
    "shape_state_from_record_for",
    "shape_with_rect",
]
