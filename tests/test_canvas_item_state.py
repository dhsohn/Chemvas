"""The canvas runtime state owns its atom, bond and scene item graphics and groups."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chemvas.domain.document import AnnotationCollection
from chemvas.domain.document.groups import SceneGroup
from chemvas.domain.document.marks import Mark
from chemvas.ui.canvas.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    clear_atom_graphics_for,
    pop_atom_dot_for,
    pop_atom_item_for,
    set_atom_dots_for,
    set_atom_items_for,
    visible_atom_item_for,
)
from chemvas.ui.canvas.canvas_bond_graphics_state import (
    CanvasBondGraphicsState,
    clear_bond_graphics_for,
    pop_bond_items_for,
    set_bond_items_for,
)
from chemvas.ui.canvas.canvas_group_state import (
    CanvasGroupState,
    clear_groups_for,
    group_ids_for_members_for,
    register_group_for,
    restore_group_for,
)
from chemvas.ui.canvas.canvas_scene_items_state import (
    CanvasSceneItemsState,
    require_scene_record_id,
)
from tests.note_support import seed_note_items
from tests.ring_support import seed_ring_items
from tests.runtime_state import canvas_runtime_state


def test_atom_graphics_state_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            atom_graphics_state=CanvasAtomGraphicsState()
        )
    )

    set_atom_items_for(canvas, {1: "label", 3: "other-label"})
    set_atom_dots_for(canvas, {2: "dot"})

    assert canvas.runtime_state.atom_graphics_state.atom_items == {
        1: "label",
        3: "other-label",
    }
    assert canvas.runtime_state.atom_graphics_state.atom_dots == {2: "dot"}
    assert not hasattr(canvas, "atom_items")
    assert not hasattr(canvas, "atom_dots")
    assert visible_atom_item_for(canvas, 1) == "label"
    assert visible_atom_item_for(canvas, 2) == "dot"

    assert pop_atom_item_for(canvas, 1) == "label"
    assert pop_atom_dot_for(canvas, 2) == "dot"
    assert canvas.runtime_state.atom_graphics_state.atom_items == {3: "other-label"}
    assert canvas.runtime_state.atom_graphics_state.atom_dots == {}


def test_clear_atom_graphics_for_updates_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        atom_items={1: "label"},
        atom_dots={2: "dot"},
        runtime_state=canvas_runtime_state(
            atom_graphics_state=CanvasAtomGraphicsState(
                atom_items={1: "label"}, atom_dots={2: "dot"}
            )
        ),
    )

    clear_atom_graphics_for(canvas)

    assert canvas.runtime_state.atom_graphics_state.atom_items == {}
    assert canvas.runtime_state.atom_graphics_state.atom_dots == {}
    assert canvas.atom_items == {1: "label"}
    assert canvas.atom_dots == {2: "dot"}


def test_bond_graphics_state_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            bond_graphics_state=CanvasBondGraphicsState()
        )
    )

    set_bond_items_for(canvas, {1: ["bond-a"], 2: ["bond-b"]})

    assert canvas.runtime_state.bond_graphics_state.bond_items == {
        1: ["bond-a"],
        2: ["bond-b"],
    }
    assert canvas.runtime_state.bond_graphics_state.bond_items.get(2, []) == ["bond-b"]
    assert not hasattr(canvas, "bond_items")

    assert pop_bond_items_for(canvas, 1) == ["bond-a"]
    assert canvas.runtime_state.bond_graphics_state.bond_items == {2: ["bond-b"]}


def test_clear_bond_graphics_for_updates_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        bond_items={1: ["bond"]},
        runtime_state=canvas_runtime_state(
            bond_graphics_state=CanvasBondGraphicsState(bond_items={1: ["bond"]})
        ),
    )

    clear_bond_graphics_for(canvas)

    assert canvas.runtime_state.bond_graphics_state.bond_items == {}
    assert canvas.bond_items == {1: ["bond"]}


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


def _canvas() -> SimpleNamespace:
    return SimpleNamespace(
        runtime_state=canvas_runtime_state(group_state=CanvasGroupState())
    )


def test_register_group_assigns_incrementing_ids() -> None:
    canvas = _canvas()
    item = SimpleNamespace(data=lambda role: 11 if role == 3 else None)

    first = register_group_for(
        canvas, {1, 2}, [require_scene_record_id(item) for item in [item]]
    )
    second = register_group_for(
        canvas, {3}, [require_scene_record_id(item) for item in []]
    )

    state = canvas.runtime_state.group_state
    assert (first, second) == (1, 2)
    assert state.groups[first].atom_ids == {1, 2}
    assert state.groups[first].item_ids == [11]
    assert state.groups[second].atom_ids == {3}
    assert state.next_group_id == 3


def test_restore_group_reinstates_and_bumps_next_id() -> None:
    canvas = _canvas()

    restore_group_for(canvas, 5, SceneGroup({7}, []))

    state = canvas.runtime_state.group_state
    assert state.groups[5].atom_ids == {7}
    assert state.next_group_id == 6


def test_group_ids_for_members_matches_atoms_and_item_identity() -> None:
    canvas = _canvas()
    item = SimpleNamespace(data=lambda role: 11 if role == 3 else None)
    other_item = SimpleNamespace(data=lambda role: 12 if role == 3 else None)
    atom_group = register_group_for(
        canvas, {1, 2}, [require_scene_record_id(item) for item in []]
    )
    item_group = register_group_for(
        canvas, set(), [require_scene_record_id(item) for item in [item]]
    )

    assert group_ids_for_members_for(canvas, {2}, []) == {atom_group}
    assert group_ids_for_members_for(canvas, set(), [item]) == {item_group}
    assert group_ids_for_members_for(canvas, set(), [other_item]) == set()
    assert group_ids_for_members_for(canvas, {1}, [item]) == {atom_group, item_group}


def test_clear_groups_resets_state() -> None:
    canvas = _canvas()
    register_group_for(canvas, {1}, [require_scene_record_id(item) for item in []])
    state = canvas.runtime_state.group_state
    state.expanding = True

    clear_groups_for(canvas)

    assert state.groups == {}
    assert state.next_group_id == 1
    assert state.expanding is False
