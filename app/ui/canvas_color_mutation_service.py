from __future__ import annotations

from typing import TYPE_CHECKING

from core.history import CompositeCommand, UpdateAtomColorCommand, UpdateBondCommand
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsTextItem

from ui.atom_label_access import implicit_carbon_dot_brush_for
from ui.bond_graphics_access import apply_color_to_bond_item_for
from ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    visible_atom_item_for,
)
from ui.canvas_bond_graphics_state import bond_items_for_id
from ui.canvas_model_access import atom_for_id, bond_for_id
from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.graphics_items import AtomDotItem
from ui.history_commands import UpdateSceneItemCommand
from ui.scene_item_access import item_is_in_canvas_scene
from ui.scene_item_state import (
    bond_state_dict,
    note_state_dict_for,
    ring_state_dict_for,
    shape_state_dict_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class _CollectingHistory:
    """Drop-in for the history service that captures pushed commands instead of
    recording them, so a multi-element mutation can be bundled into one command."""

    def __init__(self, sink) -> None:
        self._sink = sink

    def push(self, command) -> None:
        self._sink(command)


class CanvasColorMutationService:
    def __init__(self, canvas: CanvasView, *, graph_service, history_service=None) -> None:
        self.canvas = canvas
        self.history = history_service
        self.graph_service = graph_service

    def apply_color_to_item(self, item, color: QColor) -> None:
        if item is None or not color.isValid():
            return
        if not item_is_in_canvas_scene(self.canvas, item):
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
            return
        if kind == "note" and isinstance(item, QGraphicsTextItem):
            self._apply_note_color(item, color)
            return
        if kind == "shape":
            self._apply_shape_fill(item, color)

    def _apply_shape_fill(self, item, color: QColor) -> None:
        before_state = shape_state_dict_for(self.canvas, item)
        # Fill with the picked colour as-is so "pick red → shape turns red"; text
        # drawn on top stays readable because it is a separate item above the fill.
        fill = QColor(color)
        if fill.alphaF() <= 0.0:
            fill.setAlphaF(1.0)
        item.setBrush(fill)
        after_state = shape_state_dict_for(self.canvas, item)
        if before_state != after_state and self.history is not None:
            self.history.push(UpdateSceneItemCommand(item, before_state, after_state))

    def apply_ring_fill_color(self, item, color: QColor, alpha: float = 0.25) -> None:
        if item is None or not color.isValid():
            return
        if item.data(0) != "ring":
            return
        before_state = ring_state_dict_for(self.canvas, item)
        fill = QColor(color)
        fill.setAlphaF(max(0.0, min(1.0, float(alpha))))
        item.setBrush(fill)
        after_state = ring_state_dict_for(self.canvas, item)
        if before_state != after_state:
            self.history.push(UpdateSceneItemCommand(item, before_state, after_state))

    def _apply_note_color(self, item, color: QColor) -> None:
        before_state = note_state_dict_for(self.canvas, item)
        document = item.document()
        if document is not None:
            char_format = QTextCharFormat()
            char_format.setForeground(color)
            cursor = item.textCursor()
            if cursor.hasSelection():
                # Recolour only the text the user has selected, so a single note can
                # hold several colours. The selection is kept so it stays visible.
                cursor.mergeCharFormat(char_format)
                item.setTextCursor(cursor)
            else:
                whole = QTextCursor(document)
                whole.select(QTextCursor.SelectionType.Document)
                whole.mergeCharFormat(char_format)
                item.setDefaultTextColor(color)
        after_state = note_state_dict_for(self.canvas, item)
        if before_state != after_state and self.history is not None:
            self.history.push(UpdateSceneItemCommand(item, before_state, after_state))

    def _apply_bond_color(self, item, color: QColor) -> None:
        bond_id = item.data(1)
        if not isinstance(bond_id, int):
            return
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return
        before_state = bond_state_dict(bond)
        bond.color = color.name()
        for bond_item in bond_items_for_id(self.canvas, bond_id):
            apply_color_to_bond_item_for(self.canvas, bond_item, color)
        after_state = bond_state_dict(bond)
        if before_state != after_state:
            self.history.push(
                UpdateBondCommand(
                    bond_id=bond_id,
                    before_state=before_state,
                    after_state=after_state,
                    before_smiles_input=last_smiles_input_for(self.canvas),
                    after_smiles_input=last_smiles_input_for(self.canvas),
                )
            )

    def _apply_atom_color(self, item, color: QColor) -> None:
        atom_id = item.data(1)
        if isinstance(item, QGraphicsTextItem):
            item.setDefaultTextColor(color)
        elif isinstance(item, AtomDotItem):
            item.setBrush(implicit_carbon_dot_brush_for(self.canvas))
        elif isinstance(item, QGraphicsEllipseItem):
            item.setBrush(color)
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        before_color = atom.color
        atom.color = color.name()
        label_item = atom_items_for(self.canvas).get(atom_id)
        if label_item is not None and label_item is not item:
            label_item.setDefaultTextColor(color)
        dot_item = atom_dots_for(self.canvas).get(atom_id)
        if dot_item is not None and dot_item is not item:
            dot_item.setBrush(implicit_carbon_dot_brush_for(self.canvas))
        after_color = atom.color
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
            if isinstance(atom_id, int) and atom_for_id(self.canvas, atom_id) is not None
        }
        if not atom_ids:
            return
        bond_ids, _ = self.graph_service.bond_sets_for_atoms(atom_ids)
        # Coloring a ring touches every ring atom and bond. Collect the per-element
        # commands and push them as a single CompositeCommand so one undo reverts
        # the whole ring rather than peeling off one atom/bond at a time.
        real_history = self.history
        collected: list = []
        self.history = _CollectingHistory(collected.append)
        try:
            for atom_id in sorted(atom_ids):
                atom_item = visible_atom_item_for(self.canvas, atom_id)
                if atom_item is not None:
                    self.apply_color_to_item(atom_item, color)
            for bond_id in sorted(bond_ids):
                bond_items = bond_items_for_id(self.canvas, bond_id)
                if bond_items:
                    self.apply_color_to_item(bond_items[0], color)
        finally:
            self.history = real_history
        if collected:
            self.history.push(CompositeCommand(commands=collected))


__all__ = ["CanvasColorMutationService"]
