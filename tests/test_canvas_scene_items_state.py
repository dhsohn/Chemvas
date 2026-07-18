from types import SimpleNamespace

from chemvas.ui.canvas_scene_items_state import (
    CanvasSceneItemsState,
    add_selected_note_for,
    append_scene_item_for,
    clear_scene_item_collections_for,
    mark_items_for,
    remove_scene_item_from_collection_for,
    remove_selected_note_for,
    ring_items_for,
    scene_items_state_for,
    selected_notes_for,
    set_scene_item_collection_for,
)


def test_scene_items_state_for_uses_runtime_state() -> None:
    runtime_state = SimpleNamespace(
        scene_items_state=CanvasSceneItemsState(
            ring_items=["ring"], note_items=["note"]
        )
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert scene_items_state_for(canvas) is runtime_state.scene_items_state
    assert scene_items_state_for(canvas).ring_items == ["ring"]
    assert scene_items_state_for(canvas).note_items == ["note"]


def test_scene_items_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    notes = ["selected"]
    rings = ["ring"]
    marks = ["mark"]
    canvas = SimpleNamespace(selected_notes=notes, ring_items=rings, mark_items=marks)

    state = scene_items_state_for(canvas)

    assert state.selected_notes == []
    assert state.ring_items == []
    assert state.mark_items == []
    assert state.selected_notes is not notes
    assert state.ring_items is not rings
    assert state.mark_items is not marks
    assert selected_notes_for(canvas) == []
    assert ring_items_for(canvas) == []
    assert mark_items_for(canvas) == []


def test_scene_item_collection_setters_update_state_without_canvas_attr_mirror() -> (
    None
):
    canvas = SimpleNamespace()

    set_scene_item_collection_for(canvas, "note_items", ["note"])
    append_scene_item_for(canvas, "ring_items", "ring")
    append_scene_item_for(canvas, "mark_items", "mark")
    append_scene_item_for(canvas, "mark_items", "mark")
    add_selected_note_for(canvas, "selected")

    assert scene_items_state_for(canvas).note_items == ["note"]
    assert ring_items_for(canvas) == ["ring"]
    assert mark_items_for(canvas) == ["mark"]
    assert selected_notes_for(canvas) == ["selected"]
    assert not hasattr(canvas, "note_items")
    assert not hasattr(canvas, "ring_items")
    assert not hasattr(canvas, "mark_items")
    assert not hasattr(canvas, "selected_notes")

    assert remove_scene_item_from_collection_for(canvas, "mark_items", "mark") is True
    assert (
        remove_scene_item_from_collection_for(canvas, "mark_items", "missing") is False
    )
    assert remove_selected_note_for(canvas, "selected") is True
    assert mark_items_for(canvas) == []
    assert selected_notes_for(canvas) == []


def test_clear_scene_item_collections_for_updates_state_without_canvas_attr_mirror() -> (
    None
):
    canvas = SimpleNamespace(
        selected_notes=["selected"],
        ring_items=["ring"],
        note_items=["note"],
        mark_items=["mark"],
        arrow_items=["arrow"],
        ts_bracket_items=["ts"],
        orbital_items=["orbital"],
    )

    clear_scene_item_collections_for(canvas)

    assert selected_notes_for(canvas) == []
    assert ring_items_for(canvas) == []
    assert scene_items_state_for(canvas).note_items == []
    assert mark_items_for(canvas) == []
    assert scene_items_state_for(canvas).arrow_items == []
    assert scene_items_state_for(canvas).ts_bracket_items == []
    assert scene_items_state_for(canvas).orbital_items == []
    assert canvas.selected_notes == ["selected"]
    assert canvas.ring_items == ["ring"]
    assert canvas.note_items == ["note"]
    assert canvas.mark_items == ["mark"]
    assert canvas.arrow_items == ["arrow"]
    assert canvas.ts_bracket_items == ["ts"]
    assert canvas.orbital_items == ["orbital"]
