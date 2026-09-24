from __future__ import annotations

from chemvas.ui.scene.scene_item_access import attached_canvas_scene_items
from chemvas.ui.selection.selection_queries import set_scene_items_selected_for
from chemvas.ui.selection.selection_update_batch import batch_selection_updates


def _all_selectable_scene_items_for(canvas) -> tuple[list, list]:
    items: list = []
    items.extend(
        attached_canvas_scene_items(
            canvas, canvas.runtime_state.atom_graphics_state.atom_items.values()
        )
    )
    # Implicit carbons are drawn as dots rather than labelled atom items.
    items.extend(
        attached_canvas_scene_items(
            canvas, canvas.runtime_state.atom_graphics_state.atom_dots.values()
        )
    )
    for bond_items in canvas.runtime_state.bond_graphics_state.bond_items.values():
        items.extend(attached_canvas_scene_items(canvas, bond_items))
    state = canvas.runtime_state
    for scene_items in (
        state.image_items(),
        state.ring_items(),
        state.mark_items(),
        state.arrow_items(),
        state.ts_bracket_items(),
        state.shape_items(),
        state.orbital_items(),
    ):
        items.extend(attached_canvas_scene_items(canvas, scene_items))
    notes = attached_canvas_scene_items(canvas, canvas.runtime_state.note_items())
    return items, notes


def select_all_scene_items_for(canvas) -> bool:
    items, notes = _all_selectable_scene_items_for(canvas)
    if not items and not notes:
        return False
    with batch_selection_updates(canvas):
        set_scene_items_selected_for(canvas, items, True)
        for note in notes:
            canvas.services.selection.select_note(note, additive=True)
    return True


__all__ = ["select_all_scene_items_for"]
