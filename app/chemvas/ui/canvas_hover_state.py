from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chemvas.ui.canvas_state_lookup import ensure_canvas_state


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
    return ensure_canvas_state(canvas, "hover_preview_state", CanvasHoverState)


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
    "HOVER_STATE_ATTR_MAP",
    "CanvasHoverState",
    "HoverPreviewState",
    "append_hover_item_for",
    "extend_hover_items_for",
    "hover_preview_state_for",
    "hover_state_for",
    "set_hover_atom_id_for",
    "set_hover_bond_id_for",
    "set_hover_items_for",
]
