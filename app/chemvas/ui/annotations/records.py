"""Shared annotation records owned by the Qt rendering boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen

from chemvas.domain.document import (
    Shape,
    TSBracket,
    normalized_shape,
    normalized_ts_bracket,
    shape_from_state,
    shape_to_state,
    ts_bracket_from_state,
    ts_bracket_to_state,
)
from chemvas.features.annotations import shape_path
from chemvas.ui.scene_record_ids import (
    bind_scene_record,
    new_scene_record_id,
)
from chemvas.ui.scene_render_access import scene_render_context_for

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.domain.document import AnnotationCollection
    from chemvas.ui.scene_render_context import SceneRenderContext

# Roles 0-2 carry an item's kind and payloads; the shape id has its own.
SHAPE_ID_ROLE = 3


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
    item.setZValue(-10.0 if shape.z is None else shape.z)


def set_shape_record(context: SceneRenderContext, item: Any, shape: Shape) -> Shape:
    """Store the canonical form of ``shape`` for ``item`` and draw it."""
    record = normalized_shape(shape)
    state = context.state.shape_state
    shape_id = shape_id_for_item(item)
    new_record = shape_id is None
    if shape_id is None:
        shape_id = new_scene_record_id()
        item.setData(SHAPE_ID_ROLE, shape_id)
        bind_scene_record(item, state, shape_id)
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


def record_shape_state(canvas: Any, item: Any, state: Mapping[str, object]) -> Shape:
    return set_shape_record_for(
        canvas, item, shape_from_state(state, error="Invalid shape.")
    )


def shape_state_from_record_for(canvas: Any, item: Any) -> dict[str, object]:
    return shape_to_state(require_shape_record_for(canvas, item))


def clear_shape_records_for(canvas: Any) -> None:
    """Forget every record. Ids are never reused, so a stray item cannot alias."""
    document = canvas.runtime_state.shape_state
    document.clear()
    document.records.clear()


def _discard_shape_record(state: AnnotationCollection[Shape], shape_id: int) -> None:
    # Finalization releases only detached undo records. Active document shapes
    # survive projection loss; clear/rollback may replace the record mapping.
    state.discard_detached(shape_id)


def discard_shape_record_for(canvas: Any, shape_id: int) -> None:
    """Remove the record created by a failed add, even if its item is still held."""
    _discard_shape_record(canvas.runtime_state.shape_state, shape_id)


# Roles 0-2 carry an item's kind and payloads; the bracket id has its own. A
# shape keeps its id under the same role: role 0 says which store an id is for.
TS_BRACKET_ID_ROLE = 3


def ts_bracket_id_for_item(item: Any) -> int | None:
    ts_bracket_id = item.data(TS_BRACKET_ID_ROLE)
    return ts_bracket_id if type(ts_bracket_id) is int else None


def ts_bracket_record(context: SceneRenderContext, item: Any) -> TSBracket | None:
    ts_bracket_id = ts_bracket_id_for_item(item)
    if ts_bracket_id is None:
        return None
    return context.state.ts_bracket_state.records.get(ts_bracket_id)


def require_ts_bracket_record(context: SceneRenderContext, item: Any) -> TSBracket:
    record = ts_bracket_record(context, item)
    if record is None:
        raise RuntimeError("TS bracket item has no record; its state cannot be read")
    return record


def ts_bracket_rect_of(ts_bracket: TSBracket) -> QRectF:
    return QRectF(
        QPointF(ts_bracket.left, ts_bracket.top),
        QPointF(ts_bracket.right, ts_bracket.bottom),
    )


def moved_ts_bracket(ts_bracket: TSBracket, dx: float, dy: float) -> TSBracket:
    return replace(
        ts_bracket,
        left=ts_bracket.left + dx,
        top=ts_bracket.top + dy,
        right=ts_bracket.right + dx,
        bottom=ts_bracket.bottom + dy,
    )


def render_ts_bracket_item(
    context: SceneRenderContext, item: Any, ts_bracket: TSBracket
) -> None:
    """Make the item look like ``ts_bracket``.

    Every edit paints through here. The build service paints a new item once
    when it creates it, and an exact rollback snapshot puts the path, brush and
    position back together with the record it captured. The path is in scene
    coordinates, so the item stays at the origin.
    """
    rect = ts_bracket_rect_of(ts_bracket)
    item.setPos(0.0, 0.0)
    item.setPath(context.decorations.ts_bracket_path(rect, ts_bracket.bracket_kind))
    item.setPen(QPen(Qt.PenStyle.NoPen))
    item.setBrush(QBrush(QColor(context.renderer.style.bond_color)))
    item.setData(0, "ts_bracket")


def set_ts_bracket_record(
    context: SceneRenderContext, item: Any, ts_bracket: TSBracket
) -> TSBracket:
    """Store the canonical form of ``ts_bracket`` for ``item`` and draw it."""
    record = normalized_ts_bracket(ts_bracket)
    state = context.state.ts_bracket_state
    ts_bracket_id = ts_bracket_id_for_item(item)
    new_record = ts_bracket_id is None
    if ts_bracket_id is None:
        ts_bracket_id = new_scene_record_id()
        item.setData(TS_BRACKET_ID_ROLE, ts_bracket_id)
        bind_scene_record(item, state, ts_bracket_id)
    state.records[ts_bracket_id] = record
    try:
        render_ts_bracket_item(context, item, record)
    except Exception:
        if new_record:
            _discard_ts_bracket_record(state, ts_bracket_id)
        raise
    return record


def ts_bracket_record_for(canvas: Any, item: Any) -> TSBracket | None:
    return ts_bracket_record(scene_render_context_for(canvas), item)


def require_ts_bracket_record_for(canvas: Any, item: Any) -> TSBracket:
    return require_ts_bracket_record(scene_render_context_for(canvas), item)


def set_ts_bracket_record_for(
    canvas: Any, item: Any, ts_bracket: TSBracket
) -> TSBracket:
    return set_ts_bracket_record(scene_render_context_for(canvas), item, ts_bracket)


def record_ts_bracket_state(
    canvas: Any, item: Any, state: Mapping[str, object]
) -> TSBracket:
    return set_ts_bracket_record_for(
        canvas, item, ts_bracket_from_state(state, error="Invalid TS bracket.")
    )


def ts_bracket_state_from_record_for(canvas: Any, item: Any) -> dict[str, object]:
    return ts_bracket_to_state(require_ts_bracket_record_for(canvas, item))


def clear_ts_bracket_records_for(canvas: Any) -> None:
    """Forget every record. Ids are never reused, so a stray item cannot alias."""
    document = canvas.runtime_state.ts_bracket_state
    document.clear()
    document.records.clear()


def _discard_ts_bracket_record(
    state: AnnotationCollection[TSBracket], record_id: int
) -> None:
    # Finalization releases only inactive records; projection loss is not deletion.
    state.discard_detached(record_id)


def discard_ts_bracket_record_for(canvas: Any, record_id: int) -> None:
    """Discard the record of a new item whose creation did not complete."""
    _discard_ts_bracket_record(canvas.runtime_state.ts_bracket_state, record_id)


__all__ = [
    "SHAPE_ID_ROLE",
    "TS_BRACKET_ID_ROLE",
    "clear_shape_records_for",
    "clear_ts_bracket_records_for",
    "discard_shape_record_for",
    "discard_ts_bracket_record_for",
    "moved_ts_bracket",
    "record_shape_state",
    "record_ts_bracket_state",
    "render_shape_item",
    "render_ts_bracket_item",
    "require_shape_record",
    "require_shape_record_for",
    "require_ts_bracket_record",
    "require_ts_bracket_record_for",
    "set_shape_record",
    "set_shape_record_for",
    "set_ts_bracket_record",
    "set_ts_bracket_record_for",
    "shape_id_for_item",
    "shape_record",
    "shape_record_for",
    "shape_rect_of",
    "shape_state_from_record_for",
    "shape_with_rect",
    "ts_bracket_id_for_item",
    "ts_bracket_record",
    "ts_bracket_record_for",
    "ts_bracket_rect_of",
    "ts_bracket_state_from_record_for",
]
