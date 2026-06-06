from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ui.canvas_state_lookup import canvas_state_object


@dataclass(slots=True)
class CanvasHoverState:
    style: str | None = None
    items: list[Any] = field(default_factory=list)
    atom_id: int | None = None
    bond_id: int | None = None


HoverPreviewState = CanvasHoverState

HOVER_STATE_ATTR_MAP = {
    "hover_items": "items",
    "hover_atom_id": "atom_id",
    "hover_bond_id": "bond_id",
}


def hover_state_for(canvas: Any) -> CanvasHoverState:
    state = canvas_state_object(canvas, "hover_preview_state")
    if state is not None:
        return state
    state = CanvasHoverState()
    canvas.hover_preview_state = state
    return state


def hover_preview_state_for(canvas: Any) -> HoverPreviewState:
    return hover_state_for(canvas)


def set_hover_items_for(canvas: Any, items: list[Any]) -> None:
    state = hover_state_for(canvas)
    state.items = items


def append_hover_item_for(canvas: Any, item: Any) -> None:
    state = hover_state_for(canvas)
    state.items.append(item)


def extend_hover_items_for(canvas: Any, items) -> None:
    state = hover_state_for(canvas)
    state.items.extend(items)


def set_hover_atom_id_for(canvas: Any, atom_id: int | None) -> None:
    state = hover_state_for(canvas)
    state.atom_id = atom_id


def set_hover_bond_id_for(canvas: Any, bond_id: int | None) -> None:
    state = hover_state_for(canvas)
    state.bond_id = bond_id


__all__ = [
    "CanvasHoverState",
    "HOVER_STATE_ATTR_MAP",
    "HoverPreviewState",
    "append_hover_item_for",
    "extend_hover_items_for",
    "hover_preview_state_for",
    "hover_state_for",
    "set_hover_atom_id_for",
    "set_hover_bond_id_for",
    "set_hover_items_for",
]
