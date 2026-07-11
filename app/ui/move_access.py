from __future__ import annotations

from ui.canvas_service_ports import move_controller_for_access
from ui.selection_service_access import (
    refresh_selection_outline_for,
    selection_service_from_canvas,
)


def move_service_from_canvas(canvas):
    return move_controller_for_access(canvas)


def move_item_for(canvas, item, dx: float, dy: float, *, update_selection: bool = True) -> None:
    move_service_from_canvas(canvas).move_item(item, dx, dy, update_selection=update_selection)


def move_atoms_for(
    canvas,
    atom_ids: set[int],
    dx: float,
    dy: float,
    *,
    bond_ids: set[int] | None = None,
    redraw_bond_ids: set[int] | None = None,
    update_selection: bool = True,
    affected_ring_items: tuple[object, ...] | None = None,
) -> None:
    move_service = move_service_from_canvas(canvas)
    if affected_ring_items is None:
        move_service.move_atoms(
            atom_ids,
            dx,
            dy,
            bond_ids=bond_ids,
            redraw_bond_ids=redraw_bond_ids,
            update_selection=update_selection,
        )
    else:
        move_service.move_atoms(
            atom_ids,
            dx,
            dy,
            bond_ids=bond_ids,
            redraw_bond_ids=redraw_bond_ids,
            update_selection=update_selection,
            affected_ring_items=affected_ring_items,
        )


def shift_selection_outlines_for(canvas, dx: float, dy: float) -> None:
    selection_service_from_canvas(canvas).shift_selection_outlines(dx, dy)


def refresh_selection_outline_for_canvas(canvas) -> None:
    refresh_selection_outline_for(canvas)


__all__ = [
    "move_atoms_for",
    "move_item_for",
    "move_service_from_canvas",
    "refresh_selection_outline_for_canvas",
    "shift_selection_outlines_for",
]
