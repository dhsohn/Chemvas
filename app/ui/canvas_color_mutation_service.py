from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsTextItem

from core.history import UpdateAtomColorCommand, UpdateBondCommand
from ui.canvas_history_service import history_service_for
from ui.graphics_items import AtomDotItem
from ui.history_commands import UpdateSceneItemCommand

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class CanvasColorMutationService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas
        self.history = history_service_for(canvas)

    def apply_color_to_item(self, item, color: QColor) -> None:
        if item is None or not color.isValid():
            return
        try:
            if item.scene() is not self.canvas.scene():
                return
        except RuntimeError:
            return
        kind = item.data(0)
        if kind == "bond":
            self._apply_bond_color(item, color)
            return
        if kind == "atom":
            self._apply_atom_color(item, color)
            return
        if kind == "ring":
            self._apply_ring_structure_color(item, color)

    def apply_ring_fill_color(self, item, color: QColor, alpha: float = 0.25) -> None:
        if item is None or not color.isValid():
            return
        if item.data(0) != "ring":
            return
        before_state = self.canvas._ring_state_dict(item)
        fill = QColor(color)
        fill.setAlphaF(max(0.0, min(1.0, float(alpha))))
        item.setBrush(fill)
        after_state = self.canvas._ring_state_dict(item)
        if before_state != after_state:
            self.history.push(UpdateSceneItemCommand(item, before_state, after_state))

    def _apply_bond_color(self, item, color: QColor) -> None:
        bond_id = item.data(1)
        if not isinstance(bond_id, int) or not (0 <= bond_id < len(self.canvas.model.bonds)):
            return
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return
        before_state = self.canvas._bond_state_dict(bond)
        bond.color = color.name()
        for bond_item in self.canvas.bond_items.get(bond_id, []):
            self.canvas._apply_color_to_bond_item(bond_item, color)
        after_state = self.canvas._bond_state_dict(bond)
        if before_state != after_state:
            self.history.push(
                UpdateBondCommand(
                    bond_id=bond_id,
                    before_state=before_state,
                    after_state=after_state,
                    before_smiles_input=self.canvas.last_smiles_input,
                    after_smiles_input=self.canvas.last_smiles_input,
                )
            )

    def _apply_atom_color(self, item, color: QColor) -> None:
        atom_id = item.data(1)
        if isinstance(item, QGraphicsTextItem):
            item.setDefaultTextColor(color)
        elif isinstance(item, AtomDotItem):
            item.setBrush(self.canvas._implicit_carbon_dot_brush())
        elif isinstance(item, QGraphicsEllipseItem):
            item.setBrush(color)
        if atom_id not in self.canvas.model.atoms:
            return
        before_color = self.canvas.model.atoms[atom_id].color
        self.canvas.model.atoms[atom_id].color = color.name()
        label_item = self.canvas.atom_items.get(atom_id)
        if label_item is not None and label_item is not item:
            label_item.setDefaultTextColor(color)
        dot_item = self.canvas.atom_dots.get(atom_id)
        if dot_item is not None and dot_item is not item:
            dot_item.setBrush(self.canvas._implicit_carbon_dot_brush())
        after_color = self.canvas.model.atoms[atom_id].color
        if before_color != after_color:
            self.history.push(
                UpdateAtomColorCommand(
                    atom_id=atom_id,
                    before_color=before_color,
                    after_color=after_color,
                )
            )

    def _apply_ring_structure_color(self, item, color: QColor) -> None:
        ring_atom_ids = item.data(2)
        if not isinstance(ring_atom_ids, list):
            return
        atom_ids = {
            atom_id
            for atom_id in ring_atom_ids
            if isinstance(atom_id, int) and atom_id in self.canvas.model.atoms
        }
        if not atom_ids:
            return
        bond_ids, _ = self.canvas.bond_sets_for_atoms(atom_ids)
        for atom_id in sorted(atom_ids):
            atom_item = self.canvas.atom_items.get(atom_id) or self.canvas.atom_dots.get(atom_id)
            if atom_item is not None:
                self.canvas.apply_color_to_item(atom_item, color)
        for bond_id in sorted(bond_ids):
            bond_items = self.canvas.bond_items.get(bond_id, [])
            if bond_items:
                self.canvas.apply_color_to_item(bond_items[0], color)


def canvas_color_mutation_service_for(canvas) -> CanvasColorMutationService:
    return canvas._canvas_color_mutation_service


__all__ = ["CanvasColorMutationService", "canvas_color_mutation_service_for"]
