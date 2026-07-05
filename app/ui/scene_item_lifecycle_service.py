from __future__ import annotations

from contextlib import suppress

from PyQt6.QtCore import Qt

from ui.canvas_bond_renderer_state import update_bond_geometry_for
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
        self._refresh_bond_geometry_for_bond_ids(self.bond_ids_for_ring_item(item))

    def _refresh_bond_geometry_for_bond_ids(self, bond_ids: set[int]) -> None:
        for bond_id in bond_ids:
            update_bond_geometry_for(self.canvas, bond_id)

    def _refresh_bond_geometry_best_effort(self, bond_ids: set[int]) -> None:
        for bond_id in bond_ids:
            with suppress(Exception):
                update_bond_geometry_for(self.canvas, bond_id)

    def attach_scene_item(self, item) -> None:
        if not item_can_be_added_to_canvas_scene(self.canvas, item):
            return
        kind = item.data(0)
        try:
            self._register_scene_item(item, kind)
            make_item_selectable(item)
            add_item_to_canvas_scene(self.canvas, item)
            if kind == "ring":
                self.refresh_bond_geometry_for_ring_item(item)
        except Exception:
            self._rollback_failed_attach(item, kind)
            raise

    def _register_scene_item(self, item, kind) -> None:
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
        elif kind == "shape":
            append_scene_item_for(self.canvas, "shape_items", item)
        elif kind == "orbital":
            append_scene_item_for(self.canvas, "orbital_items", item)

    def _rollback_failed_attach(self, item, kind) -> None:
        ring_bond_ids: set[int] = set()
        if kind == "ring":
            with suppress(Exception):
                ring_bond_ids = self.bond_ids_for_ring_item(item)
        with suppress(Exception):
            self._remove_scene_item_registration(item, kind)
        with suppress(Exception):
            remove_attached_item_from_canvas_scene(self.canvas, item)
        if ring_bond_ids:
            self._refresh_bond_geometry_best_effort(ring_bond_ids)

    def _remove_scene_item_registration(self, item, kind) -> None:
        if kind == "ring":
            remove_scene_item_from_collection_for(self.canvas, "ring_items", item)
        elif kind == "mark":
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            remove_scene_item_from_collection_for(self.canvas, "mark_items", item)
            if isinstance(atom_id, int):
                marks = self.marks.get_for_atom(atom_id)
                if marks is not None and item in marks:
                    marks.remove(item)
                if not marks:
                    self.marks.by_atom.pop(atom_id, None)
        elif kind == "note":
            remove_selected_note_for(self.canvas, item)
            remove_scene_item_from_collection_for(self.canvas, "note_items", item)
        elif kind in ARROW_KINDS:
            remove_scene_item_from_collection_for(self.canvas, "arrow_items", item)
        elif kind == "ts_bracket":
            remove_scene_item_from_collection_for(self.canvas, "ts_bracket_items", item)
        elif kind == "shape":
            remove_scene_item_from_collection_for(self.canvas, "shape_items", item)
        elif kind == "orbital":
            remove_scene_item_from_collection_for(self.canvas, "orbital_items", item)

    def restore_scene_item(self, item) -> None:
        self.attach_scene_item(item)

    def remove_scene_item(self, item) -> None:
        if item is None:
            return
        kind = item.data(0)
        if kind == "mark":
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            remove_mark_item_for(self.canvas, item)
            if isinstance(atom_id, int) and not self.marks.get_for_atom(atom_id):
                self.marks.by_atom.pop(atom_id, None)
            return
        self._remove_scene_item_registration(item, kind)
        if kind == "note":
            update_note_selection_box_for(self.canvas, item)
        if kind in {"shape", "orbital", "curved_single", "curved_double"} and item is handle_target_for(self.canvas):
            clear_handles_for(self.canvas)
        if remove_attached_item_from_canvas_scene(self.canvas, item) is None:
            return
        if kind == "ring":
            self.refresh_bond_geometry_for_ring_item(item)


__all__ = ["SceneItemLifecycleService"]
