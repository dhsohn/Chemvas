from types import SimpleNamespace

from ui.canvas_bond_graphics_state import (
    CanvasBondGraphicsState,
    bond_graphics_state_for,
    bond_items_for,
    bond_items_for_id,
    clear_bond_graphics_for,
    pop_bond_items_for,
    set_bond_items_for,
    set_bond_items_for_id,
)


def test_bond_graphics_state_for_uses_runtime_state() -> None:
    runtime_state = SimpleNamespace(bond_graphics_state=CanvasBondGraphicsState(bond_items={1: ["bond"]}))
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert bond_graphics_state_for(canvas) is runtime_state.bond_graphics_state
    assert bond_items_for(canvas) == {1: ["bond"]}


def test_bond_graphics_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    items = {1: ["bond"]}
    canvas = SimpleNamespace(bond_items=items)

    state = bond_graphics_state_for(canvas)

    assert state.bond_items == {}
    assert state.bond_items is not items
    assert bond_items_for(canvas) == {}
    assert bond_items_for_id(canvas, 1) == []


def test_bond_graphics_state_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace()

    set_bond_items_for(canvas, {1: ["bond-a"]})
    set_bond_items_for_id(canvas, 2, ["bond-b"])

    assert bond_items_for(canvas) == {1: ["bond-a"], 2: ["bond-b"]}
    assert bond_items_for_id(canvas, 2) == ["bond-b"]
    assert not hasattr(canvas, "bond_items")

    assert pop_bond_items_for(canvas, 1) == ["bond-a"]
    assert bond_items_for(canvas) == {2: ["bond-b"]}


def test_clear_bond_graphics_for_updates_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(bond_items={1: ["bond"]})

    clear_bond_graphics_for(canvas)

    assert bond_items_for(canvas) == {}
    assert canvas.bond_items == {1: ["bond"]}
