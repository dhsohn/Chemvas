"""Explicit document records for focused mark projection doubles."""

from chemvas.domain.document.marks import Mark
from chemvas.ui.annotations.marks import MarkItem
from chemvas.ui.scene.scene_record_ids import new_scene_record_id


def bind_mark_double(canvas, item):
    document = canvas.runtime_state.mark_state
    if isinstance(item, MarkItem):
        assert item.marks is document
        return item.record_id
    data = getattr(item, "data", lambda role: None)
    record_id = data(3)
    if type(record_id) is not int or record_id not in document.records:
        if type(record_id) is not int:
            record_id = new_scene_record_id()
        metadata, state = data(1), data(9)
        metadata = metadata if isinstance(metadata, dict) else {}
        state = state if isinstance(state, dict) else {}
        values = {**metadata, **state}
        document.records[record_id] = Mark(
            kind=state.get("mark_kind", metadata.get("kind", "plus")),
            **{
                key: values[key]
                for key in ("text", "atom_id", "dx", "dy", "x", "y", "color")
                if key in values
            },
        )
        setter = getattr(item, "setData", None)
        if callable(setter):
            setter(3, record_id)
        elif hasattr(item, "__dict__"):
            item.data = lambda role: record_id if role == 3 else data(role)
    return record_id


def register_mark_double(canvas, item):
    record_id = bind_mark_double(canvas, item)
    canvas.runtime_state.mark_state.add(record_id)
    canvas.runtime_state.scene_items_state.mark_items[record_id] = item
    if hasattr(canvas.runtime_state.scene_items_state, "projections"):
        canvas.runtime_state.scene_items_state.projections[record_id] = item


def seed_mark_items(canvas, items):
    canvas.runtime_state.scene_items_state.mark_items = {}
    canvas.runtime_state.mark_state.order.clear()
    for item in items:
        register_mark_double(canvas, item)
