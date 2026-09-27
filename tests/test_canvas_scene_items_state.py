from types import SimpleNamespace

import pytest

from chemvas.domain.document import AnnotationCollection
from chemvas.domain.document.marks import Mark
from chemvas.ui.canvas.canvas_scene_items_state import CanvasSceneItemsState
from tests.note_support import seed_note_items
from tests.ring_support import seed_ring_items
from tests.runtime_state import canvas_runtime_state


def test_scene_item_collection_setters_update_state_without_canvas_attr_mirror() -> (
    None
):
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(scene_items_state=CanvasSceneItemsState())
    )

    with pytest.raises(RuntimeError, match="without a record"):
        canvas.runtime_state.append_scene_item(
            "note_items", SimpleNamespace(data=lambda key: None)
        )

    class TextDouble(str):
        pass

    seed_note_items(canvas, [TextDouble("note")])

    class MarkItemDouble(SimpleNamespace):
        pass

    mark = MarkItemDouble(data=lambda key: 42 if key == 3 else None)
    missing = SimpleNamespace(data=lambda key: 43 if key == 3 else None)
    canvas.runtime_state.mark_state = AnnotationCollection(records={42: Mark()})
    seed_ring_items(canvas, [TextDouble("ring")])
    canvas.runtime_state.append_scene_item("mark_items", mark)
    canvas.runtime_state.append_scene_item("mark_items", mark)
    canvas.runtime_state.selection_state.add_selected_note("selected")

    assert canvas.runtime_state.note_items() == ["note"]
    assert canvas.runtime_state.ring_items() == ["ring"]
    assert canvas.runtime_state.mark_items() == [mark]
    assert canvas.runtime_state.selection_state.selected_notes == ["selected"]
    assert not hasattr(canvas, "note_items")
    assert not hasattr(canvas, "ring_items")
    assert not hasattr(canvas, "mark_items")
    assert not hasattr(canvas, "selected_notes")

    assert canvas.runtime_state.remove_scene_item("mark_items", mark) is True
    assert canvas.runtime_state.remove_scene_item("mark_items", missing) is False
    assert canvas.runtime_state.selection_state.remove_selected_note("selected") is True
    assert canvas.runtime_state.mark_items() == []
    assert canvas.runtime_state.selection_state.selected_notes == []


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
        runtime_state=canvas_runtime_state(scene_items_state=CanvasSceneItemsState()),
    )

    canvas.runtime_state.clear_scene_items()

    assert canvas.runtime_state.selection_state.selected_notes == []
    assert canvas.runtime_state.ring_items() == []
    assert canvas.runtime_state.scene_items_state.note_items == {}
    assert canvas.runtime_state.mark_items() == []
    assert canvas.runtime_state.scene_items_state.arrow_items == {}
    assert canvas.runtime_state.scene_items_state.ts_bracket_items == {}
    assert canvas.runtime_state.scene_items_state.orbital_items == {}
    assert canvas.selected_notes == ["selected"]
    assert canvas.ring_items == ["ring"]
    assert canvas.note_items == ["note"]
    assert canvas.mark_items == ["mark"]
    assert canvas.arrow_items == ["arrow"]
    assert canvas.ts_bracket_items == ["ts"]
    assert canvas.orbital_items == ["orbital"]
