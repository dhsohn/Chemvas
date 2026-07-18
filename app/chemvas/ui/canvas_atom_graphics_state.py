from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chemvas.ui.canvas_state_lookup import ensure_canvas_state


@dataclass(slots=True)
class CanvasAtomGraphicsState:
    atom_items: dict[int, Any] = field(default_factory=dict)
    atom_dots: dict[int, Any] = field(default_factory=dict)


ATOM_GRAPHICS_ATTRS = ("atom_items", "atom_dots")


def atom_graphics_state_for(canvas: Any) -> CanvasAtomGraphicsState:
    return ensure_canvas_state(canvas, "atom_graphics_state", CanvasAtomGraphicsState)


def atom_items_for(canvas: Any) -> dict[int, Any]:
    return atom_graphics_state_for(canvas).atom_items


def atom_dots_for(canvas: Any) -> dict[int, Any]:
    return atom_graphics_state_for(canvas).atom_dots


def set_atom_items_for(canvas: Any, items: dict[int, Any]) -> None:
    state = atom_graphics_state_for(canvas)
    state.atom_items = items


def set_atom_dots_for(canvas: Any, dots: dict[int, Any]) -> None:
    state = atom_graphics_state_for(canvas)
    state.atom_dots = dots


def visible_atom_item_for(canvas: Any, atom_id: int):
    return atom_items_for(canvas).get(atom_id) or atom_dots_for(canvas).get(atom_id)


def set_atom_item_for(canvas: Any, atom_id: int, item: Any) -> None:
    items = atom_items_for(canvas)
    items[atom_id] = item


def set_atom_dot_for(canvas: Any, atom_id: int, item: Any) -> None:
    dots = atom_dots_for(canvas)
    dots[atom_id] = item


def pop_atom_item_for(canvas: Any, atom_id: int):
    items = atom_items_for(canvas)
    item = items.pop(atom_id, None)
    return item


def pop_atom_dot_for(canvas: Any, atom_id: int):
    dots = atom_dots_for(canvas)
    item = dots.pop(atom_id, None)
    return item


def clear_atom_graphics_for(canvas: Any) -> None:
    set_atom_items_for(canvas, {})
    set_atom_dots_for(canvas, {})


__all__ = [
    "ATOM_GRAPHICS_ATTRS",
    "CanvasAtomGraphicsState",
    "atom_dots_for",
    "atom_graphics_state_for",
    "atom_items_for",
    "clear_atom_graphics_for",
    "pop_atom_dot_for",
    "pop_atom_item_for",
    "set_atom_dot_for",
    "set_atom_dots_for",
    "set_atom_item_for",
    "set_atom_items_for",
    "visible_atom_item_for",
]
