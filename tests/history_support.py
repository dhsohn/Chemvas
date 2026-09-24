"""Explicit document IDs for projection doubles used by transaction tests."""

from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.scene_record_ids import new_scene_record_id
from tests.runtime_state import canvas_runtime_state


def history_item_id(canvas, item):
    if not hasattr(canvas, "runtime_state"):
        canvas.runtime_state = canvas_runtime_state()
    if not hasattr(canvas.runtime_state, "scene_items_state"):
        canvas.runtime_state.scene_items_state = CanvasSceneItemsState()
    views = canvas.runtime_state.scene_items_state
    if not hasattr(views, "projections"):
        from weakref import WeakValueDictionary

        views.projections = WeakValueDictionary()
    for name in (
        "ring_items",
        "image_items",
        "note_items",
        "mark_items",
        "arrow_items",
        "ts_bracket_items",
        "shape_items",
        "orbital_items",
    ):
        if not hasattr(views, name):
            setattr(views, name, {})
    record_id = getattr(item, "data", lambda role: None)(3)
    if type(record_id) is not int:
        record_id = getattr(item, "_history_record_id", None)
    if record_id is None:
        record_id = new_scene_record_id()
        if hasattr(item, "setData"):
            item.setData(3, record_id)
        item._history_record_id = record_id
    if not hasattr(canvas, "_test_history_projections"):
        canvas._test_history_projections = {}
    canvas._test_history_projections[record_id] = item
    views.projections[record_id] = item
    return record_id
