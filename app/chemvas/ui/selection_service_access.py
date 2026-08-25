from __future__ import annotations

from chemvas.features.selection import structure_hit_is_selected
from chemvas.ui.canvas_service_ports import selection_service_for_access
from chemvas.ui.selection_scene_access import (
    clear_scene_selection_for,
    set_scene_items_selected_for,
)


def selection_service_from_canvas(canvas):
    return selection_service_for_access(canvas)


def refresh_selection_outline_for(canvas) -> None:
    selection_service_for_access(canvas).update_selection_outline()


def select_note_for(canvas, item, *, additive: bool = False) -> None:
    selection_service_for_access(canvas).select_note(item, additive=additive)


def toggle_note_selection_for(canvas, item) -> None:
    selection_service_for_access(canvas).toggle_note_selection(item)


def clear_note_selection_for(canvas) -> None:
    selection_service_for_access(canvas).clear_note_selection()


def structure_item_is_selected_for(
    canvas,
    item,
    selected_atom_ids: set[int],
    selected_bond_ids: set[int],
) -> bool:
    hit, bond_atom_ids, ring_atom_ids = selection_service_from_canvas(
        canvas
    ).structure_hit_from_item(item)
    return structure_hit_is_selected(
        hit,
        selected_atom_ids=selected_atom_ids,
        selected_bond_ids=selected_bond_ids,
        bond_atom_ids=bond_atom_ids,
        ring_atom_ids=ring_atom_ids,
        item_is_selected=bool(item is not None and item.isSelected()),
    )


def selection_targets_for_item_for(canvas, item) -> list:
    targets = selection_service_for_access(canvas).selection_targets_for_item(item)
    return [target for target in (targets or []) if target is not None]


def select_single_structure_item_for(canvas, item) -> bool:
    targets = selection_targets_for_item_for(canvas, item)
    if not targets:
        return False
    clear_scene_selection_for(canvas)
    set_scene_items_selected_for(canvas, targets, True, block_signals=False)
    return True


__all__ = [
    "clear_note_selection_for",
    "refresh_selection_outline_for",
    "select_note_for",
    "select_single_structure_item_for",
    "selection_service_from_canvas",
    "selection_targets_for_item_for",
    "structure_item_is_selected_for",
    "toggle_note_selection_for",
]
