from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt

from ui.canvas_mark_registry import mark_registry_for
from ui.scene_item_restore import (
    create_arrow_item_from_state as create_arrow_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_mark_item_from_state as create_mark_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_note_item_from_state as create_note_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_orbital_item_from_state as create_orbital_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_ring_item_from_state as create_ring_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_scene_item_from_state as create_scene_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_ts_bracket_item_from_state as create_ts_bracket_item_from_state_helper,
)
from ui.scene_item_state import ARROW_KINDS
from ui.scene_item_state import apply_scene_item_state as apply_scene_item_state_helper

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SceneItemController:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas
        self.marks = mark_registry_for(canvas)

    def _restore_ring_from_state(self, ring_state: dict):
        item = create_ring_item_from_state_helper(
            ring_state,
            ring_fill_brush_getter=self.canvas.renderer.ring_fill_brush,
        )
        self.attach_scene_item(item)
        return item

    def _restore_note_from_state(self, note_state: dict):
        item = create_note_item_from_state_helper(
            note_state,
            note_item_factory=self.canvas._new_note_item,
            note_style_applier=self.canvas._apply_note_style,
        )
        self.attach_scene_item(item)
        return item

    def _restore_mark_from_state(self, mark_state: dict):
        item = create_mark_item_from_state_helper(
            mark_state,
            model_atoms=self.canvas.model.atoms,
            build_mark_item=self.canvas._build_mark_item,
            set_mark_center=self.canvas._set_mark_center,
        )
        self.attach_scene_item(item)
        return item

    def _restore_arrow_from_state(self, arrow_state: dict):
        item = create_arrow_item_from_state_helper(
            arrow_state,
            build_arrow_item=self.canvas._build_arrow_item,
            set_curved_arrow_path=self.canvas._set_curved_arrow_path,
        )
        self.attach_scene_item(item)
        return item

    def _restore_ts_bracket_from_state(self, ts_bracket_state: dict):
        item = create_ts_bracket_item_from_state_helper(
            ts_bracket_state,
            build_ts_bracket_item=self.canvas._build_ts_bracket_item,
        )
        self.attach_scene_item(item)
        return item

    def _restore_orbital_from_state(self, orbital_state: dict):
        group = create_orbital_item_from_state_helper(
            orbital_state,
            build_orbital_items=self.canvas._build_orbital_items,
            orbital_base_handle_dist=self.canvas.renderer.style.bond_length_px * 0.8,
        )
        self.attach_scene_item(group)
        return group

    def create_scene_item_from_state(self, state: dict):
        item = create_scene_item_from_state_helper(
            state,
            model_atoms=self.canvas.model.atoms,
            note_item_factory=self.canvas._new_note_item,
            note_style_applier=self.canvas._apply_note_style,
            build_mark_item=self.canvas._build_mark_item,
            set_mark_center=self.canvas._set_mark_center,
            ring_fill_brush_getter=self.canvas.renderer.ring_fill_brush,
            build_arrow_item=self.canvas._build_arrow_item,
            set_curved_arrow_path=self.canvas._set_curved_arrow_path,
            build_ts_bracket_item=self.canvas._build_ts_bracket_item,
            build_orbital_items=self.canvas._build_orbital_items,
            orbital_base_handle_dist=self.canvas.renderer.style.bond_length_px * 0.8,
        )
        if item is not None:
            self.attach_scene_item(item)
            return item
        return None

    def _bond_ids_for_ring_item(self, item) -> set[int]:
        ring_atom_ids = item.data(2)
        if not isinstance(ring_atom_ids, list) or len(ring_atom_ids) < 2:
            return set()
        bond_ids: set[int] = set()
        for index, atom_a in enumerate(ring_atom_ids):
            atom_b = ring_atom_ids[(index + 1) % len(ring_atom_ids)]
            if not isinstance(atom_a, int) or not isinstance(atom_b, int):
                continue
            bond_id = self.canvas._bond_id_between(atom_a, atom_b)
            if bond_id is not None:
                bond_ids.add(bond_id)
        return bond_ids

    def _refresh_bond_geometry_for_ring_item(self, item) -> None:
        for bond_id in self._bond_ids_for_ring_item(item):
            self.canvas.update_bond_geometry(bond_id)

    def attach_scene_item(self, item) -> None:
        if item is None:
            return
        try:
            if item.scene() is self.canvas.scene():
                return
        except RuntimeError:
            return
        kind = item.data(0)
        if kind == "ring":
            if item not in self.canvas.ring_items:
                self.canvas.ring_items.append(item)
        elif kind == "mark":
            if item not in self.canvas.mark_items:
                self.canvas.mark_items.append(item)
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int):
                self.marks.add_for_atom(atom_id, item)
        elif kind == "note":
            item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            if item not in self.canvas.note_items:
                self.canvas.note_items.append(item)
        elif kind in ARROW_KINDS:
            if item not in self.canvas.arrow_items:
                self.canvas.arrow_items.append(item)
        elif kind == "ts_bracket":
            if item not in self.canvas.ts_bracket_items:
                self.canvas.ts_bracket_items.append(item)
        elif kind == "orbital":
            if item not in self.canvas.orbital_items:
                self.canvas.orbital_items.append(item)
        self.canvas._make_selectable(item)
        self.canvas.scene().addItem(item)
        if kind == "ring":
            self._refresh_bond_geometry_for_ring_item(item)

    def restore_scene_item(self, item) -> None:
        self.attach_scene_item(item)

    def remove_scene_item(self, item) -> None:
        if item is None:
            return
        kind = item.data(0)
        if kind == "ring":
            if item in self.canvas.ring_items:
                self.canvas.ring_items.remove(item)
        elif kind == "mark":
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            self.canvas._remove_mark_item(item)
            if isinstance(atom_id, int) and not self.marks.get_for_atom(atom_id):
                self.marks.by_atom.pop(atom_id, None)
            return
        elif kind == "note":
            if item in self.canvas.selected_notes:
                self.canvas.selected_notes.remove(item)
            self.canvas._update_note_selection_box(item)
            if item in self.canvas.note_items:
                self.canvas.note_items.remove(item)
        elif kind in ARROW_KINDS:
            if item in self.canvas.arrow_items:
                self.canvas.arrow_items.remove(item)
        elif kind == "ts_bracket":
            if item in self.canvas.ts_bracket_items:
                self.canvas.ts_bracket_items.remove(item)
        elif kind == "orbital":
            if item in self.canvas.orbital_items:
                self.canvas.orbital_items.remove(item)
        if kind in {"orbital", "curved_single", "curved_double"} and item is self.canvas._handle_target:
            self.canvas.clear_handles()
        try:
            if item.scene() is self.canvas.scene():
                self.canvas.scene().removeItem(item)
        except RuntimeError:
            return
        if kind == "ring":
            self._refresh_bond_geometry_for_ring_item(item)

    def apply_scene_item_state(self, item, state: dict) -> None:
        apply_scene_item_state_helper(
            item,
            state,
            model_atoms=self.canvas.model.atoms,
            note_style_applier=self.canvas._apply_note_style,
            mark_center_setter=self.canvas._set_mark_center,
            ring_fill_brush_getter=self.canvas.renderer.ring_fill_brush,
            ts_bracket_path_builder=self.canvas._ts_bracket_path,
            bond_color=self.canvas.renderer.style.bond_color,
            build_arrow_item=self.canvas._build_arrow_item,
            set_curved_arrow_path=self.canvas._set_curved_arrow_path,
            orbital_base_handle_dist=self.canvas.renderer.style.bond_length_px * 0.8,
        )


__all__ = ["SceneItemController"]
