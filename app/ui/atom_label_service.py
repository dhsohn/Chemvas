from __future__ import annotations

from typing import TYPE_CHECKING

from core.history import (
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    UpdateBondCommand,
)
from core.model import Bond
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen

from ui.bond_style_logic import STANDARD_BOND_STYLES
from ui.canvas_history_service import history_service_for
from ui.graphics_items import AtomDotItem, AtomLabelItem
from ui.history_commands import ChangeAtomLabelCommand

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class AtomLabelService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas
        self.history = history_service_for(canvas)

    def atom_item_for_id(self, atom_id: int):
        return self.canvas.atom_items.get(atom_id) or self.canvas.atom_dots.get(atom_id)

    def ensure_carbon_dot(self, atom_id: int) -> None:
        if atom_id in self.canvas.atom_dots:
            return
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return
        radius = max(0.6, self.canvas.renderer.style.bond_line_width * 0.6)
        pick_radius = self.canvas._atom_pick_radius()
        dot = AtomDotItem(
            -radius,
            -radius,
            radius * 2.0,
            radius * 2.0,
            hit_padding=max(0.0, pick_radius - radius),
        )
        dot.setBrush(self.canvas._implicit_carbon_dot_brush())
        dot.setPen(QPen(Qt.PenStyle.NoPen))
        dot.setZValue(3)
        dot.setData(0, "atom")
        dot.setData(1, atom_id)
        self.canvas._make_selectable(dot)
        dot.setPos(atom.x, atom.y)
        self.canvas.scene().addItem(dot)
        self.canvas.atom_dots[atom_id] = dot

    def remove_carbon_dot(self, atom_id: int) -> None:
        dot = self.canvas.atom_dots.pop(atom_id, None)
        if dot is not None:
            self.canvas.scene().removeItem(dot)

    def position_label(self, item, x: float, y: float) -> None:
        rect = item.boundingRect()
        offset = self.canvas.renderer.style.atom_label_offset_px
        item.setPos(x - rect.center().x() + offset, y - rect.center().y() - offset)

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
            self.canvas._refresh_hover_from_cursor()

    def record_label_change(
        self,
        atom_id: int,
        before_element: str,
        before_explicit_label: bool,
        before_smiles_input: str | None,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        if not self.history.is_enabled():
            return
        atom = self.canvas.model.atoms.get(atom_id)
        after_element = atom.element if atom is not None else before_element
        after_explicit_label = atom.explicit_label if atom is not None else before_explicit_label
        after_smiles_input = self.canvas.last_smiles_input
        commands = []
        if (
            before_element != after_element
            or before_explicit_label != after_explicit_label
            or before_smiles_input != after_smiles_input
        ):
            commands.append(
                ChangeAtomLabelCommand(
                    atom_id=atom_id,
                    before_element=before_element,
                    after_element=after_element,
                    before_explicit_label=before_explicit_label,
                    after_explicit_label=after_explicit_label,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        if merge_ids:
            bond_before_states = merge_info.get("bond_before_states", {})
            deleted_bond_ids = set(merge_info.get("deleted_bond_ids", []))
            for bond_id, before_state in bond_before_states.items():
                if bond_id in deleted_bond_ids:
                    commands.append(
                        DeleteBondCommand(
                            bond_id=bond_id,
                            bond_state=before_state,
                            before_smiles_input=before_smiles_input,
                            after_smiles_input=after_smiles_input,
                        )
                    )
                    continue
                bond = self.canvas.model.bonds[bond_id]
                if bond is None:
                    continue
                after_state = self.canvas._bond_state_dict(bond)
                if before_state != after_state:
                    commands.append(
                        UpdateBondCommand(
                            bond_id=bond_id,
                            before_state=before_state,
                            after_state=after_state,
                            before_smiles_input=before_smiles_input,
                            after_smiles_input=after_smiles_input,
                        )
                    )
            atom_states = merge_info.get("atom_states", {})
            if atom_states:
                commands.append(
                    DeleteAtomsCommand(
                        atom_states=atom_states,
                        mark_states=[],
                        before_next_atom_id=self.canvas.model.next_atom_id,
                        after_next_atom_id=self.canvas.model.next_atom_id,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=after_smiles_input,
                        remove_marks=False,
                    )
                )
        if not commands:
            return
        if len(commands) == 1:
            self.history.push(commands[0])
            return
        self.history.push(CompositeCommand(commands))

    def merge_overlapping_atoms(self, atom_id: int) -> tuple[list[int], dict]:
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return [], {}
        tol = max(0.5, self.canvas.renderer.style.bond_length_px * 0.05)
        tol_sq = tol * tol
        merge_ids = []
        for other_id, other in self.canvas.model.atoms.items():
            if other_id == atom_id:
                continue
            dx = other.x - atom.x
            dy = other.y - atom.y
            if dx * dx + dy * dy <= tol_sq:
                merge_ids.append(other_id)
        if not merge_ids:
            return [], {}
        merge_info = {
            "atom_states": {mid: self.canvas._atom_state_dict(mid) for mid in merge_ids},
            "bond_before_states": {},
            "deleted_bond_ids": [],
        }
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            if bond.a in merge_ids or bond.b in merge_ids:
                merge_info["bond_before_states"][bond_id] = self.canvas._bond_state_dict(bond)
        for other_id in merge_ids:
            label = self.canvas.atom_items.pop(other_id, None)
            if label is not None:
                self.canvas.scene().removeItem(label)
            dot = self.canvas.atom_dots.pop(other_id, None)
            if dot is not None:
                self.canvas.scene().removeItem(dot)
        for bond in self.canvas.model.bonds:
            if bond is None:
                continue
            if bond.a in merge_ids:
                bond.a = atom_id
            if bond.b in merge_ids:
                bond.b = atom_id
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            if bond.a == bond.b:
                for item in self.canvas.bond_items.get(bond_id, []):
                    self.canvas.scene().removeItem(item)
                self.canvas.bond_items.pop(bond_id, None)
                self.canvas.model.bonds[bond_id] = None
                merge_info["deleted_bond_ids"].append(bond_id)

        def bond_rank(bond: Bond, bond_id: int) -> tuple[int, int, int]:
            order = int(bond.order or 1)
            special_style = 1 if bond.style not in STANDARD_BOND_STYLES else 0
            return (order, special_style, -bond_id)

        pair_keep: dict[tuple[int, int], int] = {}
        duplicate_ids: set[int] = set()
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            key = (bond.a, bond.b) if bond.a <= bond.b else (bond.b, bond.a)
            keep_id = pair_keep.get(key)
            if keep_id is None:
                pair_keep[key] = bond_id
                continue
            keep_bond = self.canvas.model.bonds[keep_id]
            if bond_rank(bond, bond_id) > bond_rank(keep_bond, keep_id):
                duplicate_ids.add(keep_id)
                pair_keep[key] = bond_id
            else:
                duplicate_ids.add(bond_id)
        for bond_id in sorted(duplicate_ids):
            bond = self.canvas.model.bonds[bond_id]
            if bond_id not in merge_info["bond_before_states"]:
                merge_info["bond_before_states"][bond_id] = self.canvas._bond_state_dict(bond)
            for item in self.canvas.bond_items.get(bond_id, []):
                self.canvas.scene().removeItem(item)
            self.canvas.bond_items.pop(bond_id, None)
            self.canvas.model.bonds[bond_id] = None
            merge_info["deleted_bond_ids"].append(bond_id)
        for other_id in merge_ids:
            self.canvas.model.atoms.pop(other_id, None)
        self.canvas._rebuild_bond_adjacency()
        return merge_ids, merge_info

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
        atom = self.canvas.model.atoms[atom_id]
        before_element = atom.element
        before_explicit_label = atom.explicit_label
        before_smiles_input = self.canvas.last_smiles_input
        previous_atom_item = self.atom_item_for_id(atom_id)
        was_selected = bool(previous_atom_item is not None and previous_atom_item.isSelected())
        refresh_hover = self.canvas.hover_atom_id == atom_id
        if text:
            atom.element = text
            if clear_smiles:
                self.canvas.last_smiles_input = None
        existing_item = self.canvas.atom_items.get(atom_id)
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
                self.canvas.scene().removeItem(existing_item)
                self.canvas.atom_items.pop(atom_id, None)
            if atom.element == "C":
                self.ensure_carbon_dot(atom_id)
            self.canvas._redraw_connected_bonds(atom_id)
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

        label_hit_padding = self.canvas.renderer.style.bond_length_px * 0.12
        label_hit_radius = (
            self.canvas._atom_pick_radius()
            if self.canvas._uses_compact_label_hit_shape(text)
            else None
        )
        if existing_item is not None and not isinstance(existing_item, AtomLabelItem):
            self.canvas.scene().removeItem(existing_item)
            existing_item = None
            self.canvas.atom_items.pop(atom_id, None)
        if existing_item is None:
            text_item = AtomLabelItem(hit_padding=label_hit_padding, hit_radius=label_hit_radius)
            self.canvas.scene().addItem(text_item)
            self.canvas.atom_items[atom_id] = text_item
        else:
            text_item = existing_item
            text_item.set_hit_padding(label_hit_padding)
            text_item.set_hit_radius(label_hit_radius)

        text_item.setFont(self.canvas.renderer.atom_font())
        text_item.setDefaultTextColor(QColor(self.canvas.renderer.style.atom_color))
        text_item.setData(0, "atom")
        text_item.setData(1, atom_id)
        text_item.setZValue(3)
        self.canvas._make_selectable(text_item)
        text_item.setPlainText(text)
        self.position_label(text_item, atom.x, atom.y)
        self.remove_carbon_dot(atom_id)
        merge_ids, merge_info = self.merge_overlapping_atoms(atom_id) if allow_merge else ([], {})
        self.canvas._redraw_connected_bonds(atom_id)
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


__all__ = ["AtomLabelService"]
