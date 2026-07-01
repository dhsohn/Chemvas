from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QInputDialog

from ui.atom_label_access import uses_compact_label_hit_shape_for
from ui.atom_label_history_recorder import AtomLabelHistoryRecorder
from ui.atom_label_merge_service import AtomLabelMergeService
from ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    pop_atom_dot_for,
    pop_atom_item_for,
    set_atom_dot_for,
    set_atom_item_for,
    visible_atom_item_for,
)
from ui.canvas_hover_state import hover_state_for
from ui.canvas_model_access import (
    atom_for_id,
    required_atom_for,
)
from ui.canvas_smiles_input_state import (
    clear_last_smiles_input_for,
    last_smiles_input_for,
)
from ui.graphics_items import AtomDotItem, AtomLabelItem
from ui.label_layout_logic import hydride_display_text, split_hydride_label
from ui.pick_radius_access import atom_pick_radius_for
from ui.renderer_style_access import (
    atom_color_for,
    atom_font_for,
    atom_label_offset_px_for,
    bond_length_px_for,
    bond_line_width_for,
)
from ui.scene_item_access import (
    add_item_to_canvas_scene,
    remove_item_from_canvas_scene,
)
from ui.scene_selectability import make_item_selectable
from ui.structure_geometry_access import (
    connected_atom_unit_vectors_for,
    default_bond_angle_for_vectors,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class AtomLabelService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        move_controller=None,
        graph_service,
        history_service=None,
        hover_refresh: Callable[[], None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.history = history_service
        self.move_controller = move_controller
        self.graph_service = graph_service
        self._hover_refresh = hover_refresh or (lambda: None)
        self._history_recorder = AtomLabelHistoryRecorder(
            canvas,
            history_service=history_service,
        )
        self.merge_service = AtomLabelMergeService(
            canvas,
            graph_service=graph_service,
        )

    def atom_item_for_id(self, atom_id: int):
        return visible_atom_item_for(self.canvas, atom_id)

    def implicit_carbon_dot_brush(self):
        return QColor(0, 0, 0, 0)

    def ensure_carbon_dot(self, atom_id: int) -> None:
        if atom_id in atom_dots_for(self.canvas):
            return
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        radius = max(0.6, bond_line_width_for(self.canvas) * 0.6)
        pick_radius = atom_pick_radius_for(self.canvas)
        dot = AtomDotItem(
            -radius,
            -radius,
            radius * 2.0,
            radius * 2.0,
            hit_padding=max(0.0, pick_radius - radius),
        )
        dot.setBrush(self.implicit_carbon_dot_brush())
        dot.setPen(QPen(Qt.PenStyle.NoPen))
        dot.setZValue(3)
        dot.setData(0, "atom")
        dot.setData(1, atom_id)
        make_item_selectable(dot)
        dot.setPos(atom.x, atom.y)
        add_item_to_canvas_scene(self.canvas, dot)
        set_atom_dot_for(self.canvas, atom_id, dot)

    def remove_carbon_dot(self, atom_id: int) -> None:
        dot = pop_atom_dot_for(self.canvas, atom_id)
        if dot is not None:
            remove_item_from_canvas_scene(self.canvas, dot)

    def position_label(self, item, x: float, y: float) -> None:
        offset = atom_label_offset_px_for(self.canvas)
        center = None
        anchor_center = getattr(item, "anchor_center", None)
        if callable(anchor_center):
            center = anchor_center()
        if center is None:
            center = item.boundingRect().center()
        item.setPos(x - center.x() + offset, y - center.y() - offset)

    def _label_faces_left(self, atom_id: int) -> bool:
        # Point the hydrogens where the next single bond would sprout, reusing the
        # exact bond-placement direction logic. Whichever horizontal side that
        # open direction falls on is the side the hydrogens take.
        vectors = connected_atom_unit_vectors_for(self.canvas, atom_id)
        angle = math.radians(default_bond_angle_for_vectors(vectors))
        return math.cos(angle) < 0.0

    def _hydride_layout(self, atom_id: int, text: str) -> tuple[str, str | None, bool]:
        # Element+hydrogen labels ("NH", "OH", "NH2", "CH3") anchor on the element
        # with the hydrogens pointing away from the bonds; everything else keeps
        # its plain centred layout.
        split = split_hydride_label(text)
        if split is None:
            return text, None, False
        element, h_count = split
        if h_count <= 0:
            return text, None, False
        face_left = self._label_faces_left(atom_id)
        display = hydride_display_text(element, h_count, face_left=face_left)
        return display, element, face_left

    def restore_atom_item_interaction(
        self,
        atom_id: int,
        previous_item,
        *,
        was_selected: bool,
        refresh_hover: bool,
    ) -> None:
        replacement_item = self.atom_item_for_id(atom_id)
        if was_selected and replacement_item is not None and replacement_item is not previous_item:
            replacement_item.setSelected(True)
        if refresh_hover:
            self._hover_refresh()

    def record_label_change(
        self,
        atom_id: int,
        before_element: str,
        before_explicit_label: bool,
        before_smiles_input: str | None,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        after_element = atom.element if atom is not None else before_element
        after_explicit_label = atom.explicit_label if atom is not None else before_explicit_label
        self._history_recorder.record_label_change(
            atom_id,
            before_element=before_element,
            after_element=after_element,
            before_explicit_label=before_explicit_label,
            after_explicit_label=after_explicit_label,
            before_smiles_input=before_smiles_input,
            merge_ids=merge_ids,
            merge_info=merge_info,
        )

    def merge_overlapping_atoms(self, atom_id: int) -> tuple[list[int], dict]:
        return self.merge_service.merge_overlapping_atoms(atom_id)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        clear_smiles: bool = True,
        record: bool = True,
        allow_merge: bool = True,
        show_carbon: bool = False,
    ) -> None:
        text = text.strip()
        show_carbon = bool(show_carbon)
        atom = required_atom_for(self.canvas, atom_id)
        before_element = atom.element
        before_explicit_label = atom.explicit_label
        before_smiles_input = last_smiles_input_for(self.canvas)
        previous_atom_item = self.atom_item_for_id(atom_id)
        was_selected = bool(previous_atom_item is not None and previous_atom_item.isSelected())
        refresh_hover = hover_state_for(self.canvas).atom_id == atom_id
        if text:
            atom.element = text
            if clear_smiles:
                clear_last_smiles_input_for(self.canvas)
        existing_item = atom_items_for(self.canvas).get(atom_id)
        show_label = bool(text)
        explicit_label = False
        if atom.element.upper() == "C":
            if show_carbon and show_label:
                explicit_label = True
            else:
                show_label = False
        atom.explicit_label = explicit_label
        if not show_label:
            text = ""

        if not text:
            if existing_item is not None:
                remove_item_from_canvas_scene(self.canvas, existing_item)
                pop_atom_item_for(self.canvas, atom_id)
            if atom.element == "C":
                self.ensure_carbon_dot(atom_id)
            if self.move_controller is not None:
                self.move_controller.redraw_connected_bonds(atom_id)
            self.restore_atom_item_interaction(
                atom_id,
                previous_atom_item,
                was_selected=was_selected,
                refresh_hover=refresh_hover,
            )
            if record:
                self.record_label_change(
                    atom_id,
                    before_element,
                    before_explicit_label,
                    before_smiles_input,
                    [],
                    {},
                )
            return

        label_hit_padding = bond_length_px_for(self.canvas) * 0.12
        label_hit_radius = (
            atom_pick_radius_for(self.canvas)
            if uses_compact_label_hit_shape_for(self.canvas, text)
            else None
        )
        if existing_item is not None and not isinstance(existing_item, AtomLabelItem):
            remove_item_from_canvas_scene(self.canvas, existing_item)
            existing_item = None
            pop_atom_item_for(self.canvas, atom_id)
        if existing_item is None:
            text_item = AtomLabelItem(hit_padding=label_hit_padding, hit_radius=label_hit_radius)
            add_item_to_canvas_scene(self.canvas, text_item)
            set_atom_item_for(self.canvas, atom_id, text_item)
        else:
            text_item = existing_item
            text_item.set_hit_padding(label_hit_padding)
            text_item.set_hit_radius(label_hit_radius)

        text_item.setFont(atom_font_for(self.canvas))
        text_item.setDefaultTextColor(QColor(atom_color_for(self.canvas)))
        text_item.setData(0, "atom")
        text_item.setData(1, atom_id)
        text_item.setZValue(3)
        make_item_selectable(text_item)
        display_text, anchor_element, anchor_at_end = self._hydride_layout(atom_id, text)
        text_item.setPlainText(display_text)
        text_item.set_anchor(anchor_element, at_end=anchor_at_end)
        self.position_label(text_item, atom.x, atom.y)
        self.remove_carbon_dot(atom_id)
        merge_ids, merge_info = self.merge_overlapping_atoms(atom_id) if allow_merge else ([], {})
        if self.move_controller is not None:
            self.move_controller.redraw_connected_bonds(atom_id)
        self.restore_atom_item_interaction(
            atom_id,
            previous_atom_item,
            was_selected=was_selected,
            refresh_hover=refresh_hover,
        )
        if record:
            self.record_label_change(
                atom_id,
                before_element,
                before_explicit_label,
                before_smiles_input,
                merge_ids,
                merge_info,
            )

    def prompt_atom_label(self, atom_id: int) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        initial = "" if atom.element == "C" and not atom.explicit_label else atom.element
        text, ok = QInputDialog.getText(
            self.canvas,
            "Atom Label",
            "Enter atom symbol:",
            text=initial,
        )
        if not ok:
            return
        text = text.strip()
        if not text:
            self.add_or_update_atom_label(atom_id, "C", show_carbon=False)
            return
        self.add_or_update_atom_label(atom_id, text, show_carbon=True)


__all__ = ["AtomLabelService"]
