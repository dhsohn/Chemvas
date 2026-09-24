from types import SimpleNamespace

from chemvas.ui.canvas.canvas_bond_graphics_state import (
    CanvasBondGraphicsState,
    clear_bond_graphics_for,
    pop_bond_items_for,
    set_bond_items_for,
    set_bond_items_for_id,
)
from tests.runtime_state import canvas_runtime_state


def test_bond_graphics_state_for_uses_runtime_state() -> None:
    runtime_state = canvas_runtime_state(
        bond_graphics_state=CanvasBondGraphicsState(bond_items={1: ["bond"]})
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert canvas.runtime_state.bond_graphics_state is runtime_state.bond_graphics_state
    assert canvas.runtime_state.bond_graphics_state.bond_items == {1: ["bond"]}


def test_bond_graphics_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    items = {1: ["bond"]}
    canvas = SimpleNamespace(
        bond_items=items,
        runtime_state=canvas_runtime_state(
            bond_graphics_state=CanvasBondGraphicsState()
        ),
    )

    state = canvas.runtime_state.bond_graphics_state

    assert state.bond_items == {}
    assert state.bond_items is not items
    assert canvas.runtime_state.bond_graphics_state.bond_items == {}
    assert canvas.runtime_state.bond_graphics_state.bond_items.get(1, []) == []


def test_bond_graphics_state_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            bond_graphics_state=CanvasBondGraphicsState()
        )
    )

    set_bond_items_for(canvas, {1: ["bond-a"]})
    set_bond_items_for_id(canvas, 2, ["bond-b"])

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
