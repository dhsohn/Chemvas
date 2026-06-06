from __future__ import annotations

from PyQt6.QtCore import Qt

from ui.bond_renderer import bond_renderer_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_scene_items_state import (
    append_scene_item_for,
    remove_scene_item_from_collection_for,
    remove_selected_note_for,
)
from ui.handle_overlay_access import clear_handles_for
from ui.handle_state import handle_target_for
from ui.mark_item_access import remove_mark_item_for
from ui.note_selection_box import update_note_selection_box_for
from ui.scene_item_access import (
    add_item_to_canvas_scene,
    item_can_be_added_to_canvas_scene,
    remove_attached_item_from_canvas_scene,
)
from ui.scene_item_state import ARROW_KINDS
from ui.scene_selectability import make_item_selectable


class SceneItemLifecycleService:
    def __init__(self, canvas, *, graph_service) -> None:
        self.canvas = canvas
        self.graph_service = graph_service
        self.marks = mark_registry_for(canvas)

    def _update_bond_geometry(self, bond_id: int) -> None:
        renderer = bond_renderer_for(self.canvas)
        update = getattr(renderer, "update_bond_geometry", None)
        if callable(update):
            update(bond_id)

    def bond_ids_for_ring_item(self, item) -> set[int]:
        ring_atom_ids = item.data(2)
        if not isinstance(ring_atom_ids, list) or len(ring_atom_ids) < 2:
            return set()
        bond_ids: set[int] = set()
        for index, atom_a in enumerate(ring_atom_ids):
            atom_b = ring_atom_ids[(index + 1) % len(ring_atom_ids)]
            if not isinstance(atom_a, int) or not isinstance(atom_b, int):
                continue
            bond_id = self.graph_service.bond_id_between(atom_a, atom_b)
            if bond_id is not None:
                bond_ids.add(bond_id)
        return bond_ids

    def refresh_bond_geometry_for_ring_item(self, item) -> None:
        for bond_id in self.bond_ids_for_ring_item(item):
            self._update_bond_geometry(bond_id)

    def attach_scene_item(self, item) -> None:
        if not item_can_be_added_to_canvas_scene(self.canvas, item):
            return
        kind = item.data(0)
        if kind == "ring":
            append_scene_item_for(self.canvas, "ring_items", item)
        elif kind == "mark":
            append_scene_item_for(self.canvas, "mark_items", item)
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int):
                self.marks.add_for_atom(atom_id, item)
        elif kind == "note":
            item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            append_scene_item_for(self.canvas, "note_items", item)
        elif kind in ARROW_KINDS:
            append_scene_item_for(self.canvas, "arrow_items", item)
        elif kind == "ts_bracket":
            append_scene_item_for(self.canvas, "ts_bracket_items", item)
        elif kind == "orbital":
            append_scene_item_for(self.canvas, "orbital_items", item)
        make_item_selectable(item)
        add_item_to_canvas_scene(self.canvas, item)
        if kind == "ring":
            self.refresh_bond_geometry_for_ring_item(item)

    def restore_scene_item(self, item) -> None:
        self.attach_scene_item(item)

    def remove_scene_item(self, item) -> None:
        if item is None:
            return
        kind = item.data(0)
        if kind == "ring":
            remove_scene_item_from_collection_for(self.canvas, "ring_items", item)
        elif kind == "mark":
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            remove_mark_item_for(self.canvas, item)
            if isinstance(atom_id, int) and not self.marks.get_for_atom(atom_id):
                self.marks.by_atom.pop(atom_id, None)
            return
        elif kind == "note":
            remove_selected_note_for(self.canvas, item)
            update_note_selection_box_for(self.canvas, item)
            remove_scene_item_from_collection_for(self.canvas, "note_items", item)
        elif kind in ARROW_KINDS:
            remove_scene_item_from_collection_for(self.canvas, "arrow_items", item)
        elif kind == "ts_bracket":
            remove_scene_item_from_collection_for(self.canvas, "ts_bracket_items", item)
        elif kind == "orbital":
            remove_scene_item_from_collection_for(self.canvas, "orbital_items", item)
        if kind in {"orbital", "curved_single", "curved_double"} and item is handle_target_for(self.canvas):
            clear_handles_for(self.canvas)
        if remove_attached_item_from_canvas_scene(self.canvas, item) is None:
            return
        if kind == "ring":
            self.refresh_bond_geometry_for_ring_item(item)


__all__ = ["SceneItemLifecycleService"]
