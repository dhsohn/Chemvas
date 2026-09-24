"""Explicit document ownership for focused note projection doubles."""

from chemvas.domain.document.notes import Note
from chemvas.ui.annotations.items import NoteItem
from chemvas.ui.scene.scene_record_ids import new_scene_record_id


def bind_note_double(canvas, item):
    document = canvas.runtime_state.note_state
    if isinstance(item, NoteItem):
        assert item.notes is document
        return item.record_id
    data = getattr(item, "data", lambda role: None)
    record_id = data(3)
    if type(record_id) is not int or record_id not in document.records:
        if type(record_id) is not int:
            record_id = new_scene_record_id()
        state = data(9)
        state = state if isinstance(state, dict) else {}
        text = getattr(item, "toPlainText", lambda: "")()
        document.records[record_id] = Note(
            text=state.get("text", text),
            html=state.get("html", ""),
            x=state.get("x", 0.0),
            y=state.get("y", 0.0),
            rotation=state.get("rotation", 0.0),
        )
        setter = getattr(item, "setData", None)
        if callable(setter):
            setter(3, record_id)
    return record_id


def register_note_double(canvas, item):
    record_id = bind_note_double(canvas, item)
    canvas.runtime_state.note_state.add(record_id)
    canvas.runtime_state.scene_items_state.note_items[record_id] = item
    if hasattr(canvas.runtime_state.scene_items_state, "projections"):
        canvas.runtime_state.scene_items_state.projections[record_id] = item


def seed_note_items(canvas, items):
    canvas.runtime_state.scene_items_state.note_items = {}
    canvas.runtime_state.note_state.order.clear()
    for item in items:
        register_note_double(canvas, item)
