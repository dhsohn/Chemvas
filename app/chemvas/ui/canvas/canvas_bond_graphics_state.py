from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast


@dataclass(slots=True)
class CanvasBondGraphicsState:
    bond_items: dict[int, list[Any]] = field(default_factory=dict)


def bond_graphics_state_for(canvas: Any) -> CanvasBondGraphicsState:
    return cast("CanvasBondGraphicsState", canvas.runtime_state.bond_graphics_state)


def bond_items_for(canvas: Any) -> dict[int, list[Any]]:
    return bond_graphics_state_for(canvas).bond_items


def set_bond_items_for(canvas: Any, items: dict[int, list[Any]]) -> None:
    state = bond_graphics_state_for(canvas)
    state.bond_items = items


def bond_items_for_id(canvas: Any, bond_id: int) -> list[Any]:
    return bond_items_for(canvas).get(bond_id, [])


def set_bond_items_for_id(canvas: Any, bond_id: int, items: list[Any]) -> None:
    bond_items = bond_items_for(canvas)
    bond_items[bond_id] = items


def pop_bond_items_for(canvas: Any, bond_id: int) -> list[Any] | None:
    bond_items = bond_items_for(canvas)
    items = bond_items.pop(bond_id, None)
    return items


def clear_bond_graphics_for(canvas: Any) -> None:
    set_bond_items_for(canvas, {})


__all__ = [
    "CanvasBondGraphicsState",
    "bond_graphics_state_for",
    "bond_items_for",
    "bond_items_for_id",
    "clear_bond_graphics_for",
    "pop_bond_items_for",
    "set_bond_items_for",
    "set_bond_items_for_id",
]
