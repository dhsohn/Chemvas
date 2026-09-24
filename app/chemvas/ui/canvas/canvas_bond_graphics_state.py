from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CanvasBondGraphicsState:
    bond_items: dict[int, list[Any]] = field(default_factory=dict)


def set_bond_items_for(canvas: Any, items: dict[int, list[Any]]) -> None:
    state = canvas.runtime_state.bond_graphics_state
    state.bond_items = items


def set_bond_items_for_id(canvas: Any, bond_id: int, items: list[Any]) -> None:
    bond_items = canvas.runtime_state.bond_graphics_state.bond_items
    bond_items[bond_id] = items


def pop_bond_items_for(canvas: Any, bond_id: int) -> list[Any] | None:
    bond_items = canvas.runtime_state.bond_graphics_state.bond_items
    items = bond_items.pop(bond_id, None)
    return items


def clear_bond_graphics_for(canvas: Any) -> None:
    set_bond_items_for(canvas, {})


__all__ = [
    "CanvasBondGraphicsState",
    "clear_bond_graphics_for",
    "pop_bond_items_for",
    "set_bond_items_for",
    "set_bond_items_for_id",
]
