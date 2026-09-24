from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CanvasAtomGraphicsState:
    atom_items: dict[int, Any] = field(default_factory=dict)
    atom_dots: dict[int, Any] = field(default_factory=dict)


def set_atom_items_for(canvas: Any, items: dict[int, Any]) -> None:
    state = canvas.runtime_state.atom_graphics_state
    state.atom_items = items


def set_atom_dots_for(canvas: Any, dots: dict[int, Any]) -> None:
    state = canvas.runtime_state.atom_graphics_state
    state.atom_dots = dots


def visible_atom_item_for(canvas: Any, atom_id: int):
    return canvas.runtime_state.atom_graphics_state.atom_items.get(
        atom_id
    ) or canvas.runtime_state.atom_graphics_state.atom_dots.get(atom_id)


def set_atom_item_for(canvas: Any, atom_id: int, item: Any) -> None:
    items = canvas.runtime_state.atom_graphics_state.atom_items
    items[atom_id] = item


def set_atom_dot_for(canvas: Any, atom_id: int, item: Any) -> None:
    dots = canvas.runtime_state.atom_graphics_state.atom_dots
    dots[atom_id] = item


def pop_atom_item_for(canvas: Any, atom_id: int):
    items = canvas.runtime_state.atom_graphics_state.atom_items
    item = items.pop(atom_id, None)
    return item


def pop_atom_dot_for(canvas: Any, atom_id: int):
    dots = canvas.runtime_state.atom_graphics_state.atom_dots
    item = dots.pop(atom_id, None)
    return item


def clear_atom_graphics_for(canvas: Any) -> None:
    set_atom_items_for(canvas, {})
    set_atom_dots_for(canvas, {})


__all__ = [
    "CanvasAtomGraphicsState",
    "clear_atom_graphics_for",
    "pop_atom_dot_for",
    "pop_atom_item_for",
    "set_atom_dot_for",
    "set_atom_dots_for",
    "set_atom_item_for",
    "set_atom_items_for",
    "visible_atom_item_for",
]
