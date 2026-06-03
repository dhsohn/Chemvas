from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from ui.hover_scene_renderer import (
    add_hover_preview_items as add_hover_preview_items_helper,
)
from ui.hover_scene_renderer import (
    build_atom_hover_indicator as build_atom_hover_indicator_helper,
)
from ui.hover_scene_renderer import (
    build_bond_hover_indicator as build_bond_hover_indicator_helper,
)
from ui.hover_scene_renderer import (
    clear_hover_items as clear_hover_items_helper,
)

if TYPE_CHECKING:
    from core.model import Bond

    from ui.canvas_view import CanvasView


class HoverSceneService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def clear_hover_highlight(self) -> None:
        self.canvas.hover_items = clear_hover_items_helper(self.canvas.scene(), self.canvas.hover_items)
        self.canvas.hover_atom_id = None
        self.canvas.hover_bond_id = None
        self.canvas._hover_preview_style = None

    def add_hover_preview_items(self, items: Sequence[QGraphicsItem]) -> None:
        if not items:
            return
        self.canvas.hover_items.extend(add_hover_preview_items_helper(self.canvas.scene(), items))

    def add_atom_hover_indicator(self, atom_id: int) -> None:
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return
        radius = self.canvas.renderer.style.bond_length_px * 0.25
        indicator = build_atom_hover_indicator_helper(QPointF(atom.x, atom.y), radius)
        self.canvas.scene().addItem(indicator)
        self.canvas.hover_items.append(indicator)

    def add_bond_hover_indicator(self, bond_id: int | None) -> None:
        bond = self._bond_for_id(bond_id)
        if bond is None:
            return
        start_atom = self.canvas.model.atoms.get(bond.a)
        end_atom = self.canvas.model.atoms.get(bond.b)
        if start_atom is None or end_atom is None:
            return
        radius = self.canvas.renderer.style.bond_length_px * 0.22
        indicator = build_bond_hover_indicator_helper(
            QPointF(start_atom.x, start_atom.y),
            QPointF(end_atom.x, end_atom.y),
            radius,
        )
        self.canvas.scene().addItem(indicator)
        self.canvas.hover_items.append(indicator)

    def _bond_for_id(self, bond_id: int | None) -> Bond | None:
        if bond_id is None or bond_id < 0:
            return None
        try:
            return self.canvas.model.bonds[bond_id]
        except (IndexError, KeyError, TypeError):
            return None


__all__ = ["HoverSceneService"]
