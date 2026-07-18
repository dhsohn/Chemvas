from __future__ import annotations

from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for
from chemvas.ui.canvas_scene_items_state import (
    arrow_items_for,
    mark_items_for,
    note_items_for,
    orbital_items_for,
    ring_items_for,
    shape_items_for,
    ts_bracket_items_for,
)
from chemvas.ui.scene_item_access import attached_canvas_scene_items
from chemvas.ui.selection_scene_access import set_scene_items_selected_for
from chemvas.ui.selection_service_access import (
    refresh_selection_outline_for,
    select_note_for,
)


def _all_selectable_scene_items_for(canvas) -> tuple[list, list]:
    items: list = []
    items.extend(attached_canvas_scene_items(canvas, atom_items_for(canvas).values()))
    # Implicit carbons are drawn as dots rather than labelled atom items.
    items.extend(attached_canvas_scene_items(canvas, atom_dots_for(canvas).values()))
    for bond_items in bond_items_for(canvas).values():
        items.extend(attached_canvas_scene_items(canvas, bond_items))
    for items_for in (
        ring_items_for,
        mark_items_for,
        arrow_items_for,
        ts_bracket_items_for,
        shape_items_for,
        orbital_items_for,
    ):
        items.extend(attached_canvas_scene_items(canvas, items_for(canvas)))
    notes = attached_canvas_scene_items(canvas, note_items_for(canvas))
    return items, notes


def select_all_scene_items_for(canvas) -> bool:
    items, notes = _all_selectable_scene_items_for(canvas)
    if not items and not notes:
        return False
    set_scene_items_selected_for(canvas, items, True)
    for note in notes:
        select_note_for(canvas, note, additive=True)
    refresh_selection_outline_for(canvas)
    return True


__all__ = ["select_all_scene_items_for"]
