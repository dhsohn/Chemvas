from types import SimpleNamespace

from chemvas.ui.canvas.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    clear_atom_graphics_for,
    pop_atom_dot_for,
    pop_atom_item_for,
    set_atom_dot_for,
    set_atom_item_for,
    set_atom_items_for,
    visible_atom_item_for,
)
from tests.runtime_state import canvas_runtime_state


def test_atom_graphics_state_for_uses_runtime_state() -> None:
    runtime_state = canvas_runtime_state(
        atom_graphics_state=CanvasAtomGraphicsState(atom_items={1: "label"})
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert canvas.runtime_state.atom_graphics_state is runtime_state.atom_graphics_state
    assert canvas.runtime_state.atom_graphics_state.atom_items == {1: "label"}


def test_atom_graphics_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    labels = {1: "label"}
    dots = {2: "dot"}
    canvas = SimpleNamespace(
        atom_items=labels,
        atom_dots=dots,
        runtime_state=canvas_runtime_state(
            atom_graphics_state=CanvasAtomGraphicsState()
        ),
    )

    state = canvas.runtime_state.atom_graphics_state

    assert state.atom_items == {}
    assert state.atom_dots == {}
    assert state.atom_items is not labels
    assert state.atom_dots is not dots
    assert canvas.runtime_state.atom_graphics_state.atom_items == {}
    assert canvas.runtime_state.atom_graphics_state.atom_dots == {}


def test_atom_graphics_state_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            atom_graphics_state=CanvasAtomGraphicsState()
        )
    )

    set_atom_items_for(canvas, {1: "label"})
    set_atom_dot_for(canvas, 2, "dot")
    set_atom_item_for(canvas, 3, "other-label")

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
