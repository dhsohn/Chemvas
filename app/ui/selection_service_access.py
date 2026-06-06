from __future__ import annotations

from ui.selection_hit_logic import structure_hit_is_selected
from ui.selection_ports import selection_service_for_access
from ui.selection_scene_access import (
    clear_scene_selection_for,
    set_scene_items_selected_for,
)
from ui.selection_structure_targets import structure_selection_targets_for_item


def selection_service_from_canvas(canvas):
    return selection_service_for_access(canvas)


def optional_selection_service_from_canvas(canvas):
    try:
        return selection_service_from_canvas(canvas)
    except AttributeError:
        return None


def refresh_selection_outline_for(canvas) -> None:
    controller = optional_selection_service_from_canvas(canvas)
    update_selection_outline = getattr(controller, "update_selection_outline", None)
    if callable(update_selection_outline):
        update_selection_outline()


def select_note_for(canvas, item, *, additive: bool = False) -> None:
    controller = optional_selection_service_from_canvas(canvas)
    select_note = getattr(controller, "select_note", None)
    if callable(select_note):
        select_note(item, additive=additive)


def toggle_note_selection_for(canvas, item) -> None:
    controller = optional_selection_service_from_canvas(canvas)
    toggle_note_selection = getattr(controller, "toggle_note_selection", None)
    if callable(toggle_note_selection):
        toggle_note_selection(item)


def clear_note_selection_for(canvas) -> None:
    controller = optional_selection_service_from_canvas(canvas)
    clear_note_selection = getattr(controller, "clear_note_selection", None)
    if callable(clear_note_selection):
        clear_note_selection()


def structure_item_is_selected_for(
    canvas,
    item,
    selected_atom_ids: set[int],
    selected_bond_ids: set[int],
) -> bool:
    hit, bond_atom_ids, ring_atom_ids = selection_service_from_canvas(canvas).structure_hit_from_item(item)
    return structure_hit_is_selected(
        hit,
        selected_atom_ids=selected_atom_ids,
        selected_bond_ids=selected_bond_ids,
        bond_atom_ids=bond_atom_ids,
        ring_atom_ids=ring_atom_ids,
        item_is_selected=bool(item is not None and item.isSelected()),
    )


def _selection_targets_method_for(canvas):
    controller = optional_selection_service_from_canvas(canvas)
    targets_for_item = getattr(controller, "selection_targets_for_item", None)
    return targets_for_item if callable(targets_for_item) else None


def selection_targets_for_item_for(canvas, item) -> list:
    targets_for_item = _selection_targets_method_for(canvas)
    if callable(targets_for_item):
        return [target for target in (targets_for_item(item) or []) if target is not None]
    return structure_selection_targets_for_item(canvas, item)


def select_single_structure_item_for(canvas, item) -> bool:
    uses_controller_targets = _selection_targets_method_for(canvas) is not None
    if not uses_controller_targets and item is not None:
        clear_scene_selection_for(canvas)
    targets = selection_targets_for_item_for(canvas, item)
    if not targets:
        return False
    if uses_controller_targets:
        clear_scene_selection_for(canvas)
    set_scene_items_selected_for(canvas, targets, True, block_signals=False)
    return True


__all__ = [
    "clear_note_selection_for",
    "optional_selection_service_from_canvas",
    "refresh_selection_outline_for",
    "select_note_for",
    "select_single_structure_item_for",
    "selection_service_from_canvas",
    "selection_targets_for_item_for",
    "structure_item_is_selected_for",
    "toggle_note_selection_for",
]
