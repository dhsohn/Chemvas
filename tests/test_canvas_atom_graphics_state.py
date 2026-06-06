from types import SimpleNamespace

from ui.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    atom_dots_for,
    atom_graphics_state_for,
    atom_items_for,
    clear_atom_graphics_for,
    pop_atom_dot_for,
    pop_atom_item_for,
    set_atom_dot_for,
    set_atom_item_for,
    set_atom_items_for,
    visible_atom_item_for,
)


def test_atom_graphics_state_for_uses_runtime_state() -> None:
    runtime_state = SimpleNamespace(atom_graphics_state=CanvasAtomGraphicsState(atom_items={1: "label"}))
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert atom_graphics_state_for(canvas) is runtime_state.atom_graphics_state
    assert atom_items_for(canvas) == {1: "label"}


def test_atom_graphics_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    labels = {1: "label"}
    dots = {2: "dot"}
    canvas = SimpleNamespace(atom_items=labels, atom_dots=dots)

    state = atom_graphics_state_for(canvas)

    assert state.atom_items == {}
    assert state.atom_dots == {}
    assert state.atom_items is not labels
    assert state.atom_dots is not dots
    assert atom_items_for(canvas) == {}
    assert atom_dots_for(canvas) == {}


def test_atom_graphics_state_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace()

    set_atom_items_for(canvas, {1: "label"})
    set_atom_dot_for(canvas, 2, "dot")
    set_atom_item_for(canvas, 3, "other-label")

    assert atom_items_for(canvas) == {1: "label", 3: "other-label"}
    assert atom_dots_for(canvas) == {2: "dot"}
    assert not hasattr(canvas, "atom_items")
    assert not hasattr(canvas, "atom_dots")
    assert visible_atom_item_for(canvas, 1) == "label"
    assert visible_atom_item_for(canvas, 2) == "dot"

    assert pop_atom_item_for(canvas, 1) == "label"
    assert pop_atom_dot_for(canvas, 2) == "dot"
    assert atom_items_for(canvas) == {3: "other-label"}
    assert atom_dots_for(canvas) == {}


def test_clear_atom_graphics_for_updates_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(atom_items={1: "label"}, atom_dots={2: "dot"})

    clear_atom_graphics_for(canvas)

    assert atom_items_for(canvas) == {}
    assert atom_dots_for(canvas) == {}
    assert canvas.atom_items == {1: "label"}
    assert canvas.atom_dots == {2: "dot"}
