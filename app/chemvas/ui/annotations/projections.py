"""Resolve document IDs at the Qt boundary; history never owns a projection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6 import sip
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.domain.document.arrows import arrow_to_state
from chemvas.domain.document.images import image_to_state
from chemvas.domain.document.marks import mark_to_state
from chemvas.domain.document.notes import note_to_state
from chemvas.domain.document.orbitals import orbital_to_state
from chemvas.domain.document.ring_fills import ring_fill_to_state
from chemvas.domain.document.shapes import shape_to_state
from chemvas.domain.document.ts_brackets import ts_bracket_to_state
from chemvas.ui.annotations.materialize import create_scene_item_from_state
from chemvas.ui.canvas.canvas_scene_items_state import (
    DOCUMENT_COLLECTION_STATES,
    document_collection_for,
)
from chemvas.ui.scene.note_item_access import new_note_item_for
from chemvas.ui.scene.scene_item_access import restore_scene_item
from chemvas.ui.scene.scene_record_ids import (
    bind_scene_record,
    release_scene_record_lease,
)

if TYPE_CHECKING:
    from collections.abc import Callable


_SERIALIZERS: dict[str, Callable[[Any], dict[str, object]]] = {
    "arrow_items": arrow_to_state,
    "image_items": image_to_state,
    "mark_items": mark_to_state,
    "note_items": note_to_state,
    "orbital_items": orbital_to_state,
    "shape_items": shape_to_state,
    "ts_bracket_items": ts_bracket_to_state,
}


def find_projection(canvas, record_id: int):
    views = canvas.runtime_state.scene_items_state
    item = views.projections.get(record_id)
    if item is None:
        for name in DOCUMENT_COLLECTION_STATES:
            item = getattr(views, name).get(record_id)
            if item is not None:
                break
    if isinstance(item, QGraphicsItem) and sip.isdeleted(item):
        release_scene_record_lease(record_id)
        return None
    return item


def resolve_projection(canvas, record_id: int, state: dict | None = None):
    """Reuse a live view or materialize its value under the same document ID.

    Active records are authoritative. A deleted annotation can be restored from
    a command's value after its detached projection and record were released.
    The caller owns attachment and the surrounding mutation transaction.
    """
    item = find_projection(canvas, record_id)
    if item is not None:
        return item
    runtime = canvas.runtime_state
    document = None
    record = None
    for name in DOCUMENT_COLLECTION_STATES:
        candidate = document_collection_for(runtime, name)
        if record_id not in candidate.records:
            continue
        document = candidate
        record = candidate.records[record_id]
        if name == "ring_items":
            state = ring_fill_to_state(record, canvas.model.atoms)
        else:
            state = _SERIALIZERS[name](record)
        break
    if state is None:
        raise RuntimeError(f"annotation {record_id} has no document or history value")
    item = create_scene_item_from_state(
        canvas.render_context,
        {key: value for key, value in state.items() if not key.startswith("_")},
        note_item_factory=lambda: new_note_item_for(canvas),
    )
    if item is None:
        raise ValueError("Cannot restore an unknown annotation kind")
    temporary_id = item.data(3)
    if document is None:
        for name in DOCUMENT_COLLECTION_STATES:
            candidate = document_collection_for(runtime, name)
            if temporary_id in candidate.records:
                document = candidate
                break
    if document is None:
        raise RuntimeError("materialized annotation has no document record")
    new_record = document.records.pop(temporary_id)
    document.records[record_id] = record if record is not None else new_record
    release_scene_record_lease(temporary_id)
    item.setData(3, record_id)
    if hasattr(item, "record_id"):
        item.record_id = record_id
    bind_scene_record(item, document, record_id)
    if state.get("kind") == "mark" and "item_pos" in state:
        item.setPos(*state["item_pos"])
    runtime.scene_items_state.projections[record_id] = item
    return item


def group_projections(canvas, item_ids: list[int]) -> list:
    """Resolve attached group members without making membership depend on Qt."""
    scene = canvas.scene()
    return [
        item
        for record_id in item_ids
        if (item := find_projection(canvas, record_id)) is not None
        and item.scene() is scene
    ]


def restore_active_projection(canvas, record_id: int, state: dict | None = None):
    """Resolve an edited annotation and attach it if the document still owns it."""
    item = resolve_projection(canvas, record_id, state)
    if (
        any(
            record_id in document_collection_for(canvas.runtime_state, name).order
            for name in DOCUMENT_COLLECTION_STATES
        )
        and item.scene() is None
    ):
        restore_scene_item(canvas, item)
    return item
