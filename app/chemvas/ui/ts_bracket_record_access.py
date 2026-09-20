"""A TS bracket is its record; the graphics item draws it.

Every edit computes a new ``TSBracket`` and hands it to
``set_ts_bracket_record_for``, which stores the canonical record and renders the
item from it. Every read of a bracket's state comes from the record. The item
keeps its identity, because history and recovery hold on to it. A record that
no document could hold cannot be built, so an edit that would produce one fails
before it touches the item. Document values live only in the record; the item
carries its kind and id alongside its rendered path and construction font.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any
from weakref import finalize

from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import QGraphicsPathItem

from chemvas.domain.document import (
    TSBracket,
    normalized_ts_bracket,
    ts_bracket_from_state,
    ts_bracket_to_state,
)
from chemvas.ui.canvas_ts_bracket_state import ts_bracket_state_for
from chemvas.ui.scene_record_ids import new_scene_record_id
from chemvas.ui.scene_render_access import scene_render_context_for

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.ui.canvas_ts_bracket_state import CanvasTSBracketState
    from chemvas.ui.scene_render_context import SceneRenderContext

# Roles 0-2 carry an item's kind and payloads; the bracket id has its own. A
# shape keeps its id under the same role: role 0 says which store an id is for.
TS_BRACKET_ID_ROLE = 3


def _is_deleted(item: Any) -> bool:
    try:
        return sip.isdeleted(item)
    except TypeError:
        # Not a Qt wrapper at all; nothing Qt could have destroyed.
        return False


def _is_ts_bracket_item(item: Any) -> bool:
    return (
        isinstance(item, QGraphicsPathItem)
        and not _is_deleted(item)
        and item.data(0) == "ts_bracket"
    )


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
        finalize(item, _discard_ts_bracket_record, state, ts_bracket_id)
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


def require_attached_ts_bracket_record_for(canvas: Any, item: Any) -> None:
    """An item may join the document's brackets only with its record in place."""
    if _is_ts_bracket_item(item) and ts_bracket_record_for(canvas, item) is None:
        raise RuntimeError("TS bracket item attached without a record")


def ts_bracket_state_from_record_for(canvas: Any, item: Any) -> dict[str, object]:
    return ts_bracket_to_state(require_ts_bracket_record_for(canvas, item))


def clear_ts_bracket_records_for(canvas: Any) -> None:
    """Forget every record. Ids are never reused, so a stray item cannot alias."""
    ts_bracket_state_for(canvas).records = {}


def _discard_ts_bracket_record(state: CanvasTSBracketState, record_id: int) -> None:
    # Rollback can replace the mapping; always resolve the state's current one.
    state.records.pop(record_id, None)


def discard_ts_bracket_record_for(canvas: Any, record_id: int) -> None:
    """Discard the record of a new item whose creation did not complete."""
    _discard_ts_bracket_record(ts_bracket_state_for(canvas), record_id)


__all__ = [
    "TS_BRACKET_ID_ROLE",
    "clear_ts_bracket_records_for",
    "discard_ts_bracket_record_for",
    "moved_ts_bracket",
    "record_ts_bracket_state",
    "render_ts_bracket_item",
    "require_attached_ts_bracket_record_for",
    "require_ts_bracket_record",
    "require_ts_bracket_record_for",
    "set_ts_bracket_record",
    "set_ts_bracket_record_for",
    "ts_bracket_id_for_item",
    "ts_bracket_record",
    "ts_bracket_record_for",
    "ts_bracket_rect_of",
    "ts_bracket_state_from_record_for",
]
