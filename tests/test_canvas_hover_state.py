from types import SimpleNamespace

from chemvas.ui.canvas_hover_state import (
    CanvasHoverState,
    append_hover_item_for,
    hover_preview_state_for,
    hover_state_for,
    set_hover_atom_id_for,
    set_hover_bond_id_for,
    set_hover_items_for,
)


def test_hover_state_for_uses_runtime_state() -> None:
    runtime_state = SimpleNamespace(hover_preview_state=CanvasHoverState(style="wedge"))
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert hover_state_for(canvas) is runtime_state.hover_preview_state
    assert hover_preview_state_for(canvas).style == "wedge"


def test_hover_state_for_starts_from_default_state_without_canvas_attr_fallback() -> (
    None
):
    canvas = SimpleNamespace(hover_items=["existing"], hover_atom_id=2, hover_bond_id=3)

    state = hover_state_for(canvas)

    assert state.items == []
    assert state.atom_id is None
    assert state.bond_id is None


def test_hover_state_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace()

    set_hover_items_for(canvas, ["a"])
    append_hover_item_for(canvas, "b")
    set_hover_atom_id_for(canvas, 7)
    set_hover_bond_id_for(canvas, 9)

    assert hover_state_for(canvas).items == ["a", "b"]
    assert hover_state_for(canvas).atom_id == 7
    assert hover_state_for(canvas).bond_id == 9
    assert not hasattr(canvas, "hover_items")
    assert not hasattr(canvas, "hover_atom_id")
    assert not hasattr(canvas, "hover_bond_id")
