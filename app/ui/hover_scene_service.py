from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from ui.canvas_hover_state import (
    append_hover_item_for,
    extend_hover_items_for,
    hover_state_for,
    set_hover_atom_id_for,
    set_hover_bond_id_for,
    set_hover_items_for,
)
from ui.canvas_model_access import atom_for_id, bond_for_id
from ui.hover_scene_access import (
    add_hover_preview_items_to_scene_for,
    add_hover_scene_item_for,
    clear_hover_items_for,
)
from ui.hover_scene_renderer import (
    build_atom_hover_indicator as build_atom_hover_indicator_helper,
)
from ui.hover_scene_renderer import (
    build_bond_hover_indicator as build_bond_hover_indicator_helper,
)
from ui.renderer_style_access import bond_length_px_for

if TYPE_CHECKING:
    from core.model import Bond

    from ui.canvas_view import CanvasView


class HoverSceneService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def clear_hover_highlight(self) -> None:
        hover_state = hover_state_for(self.canvas)
        set_hover_items_for(self.canvas, clear_hover_items_for(self.canvas, hover_state.items))
        set_hover_atom_id_for(self.canvas, None)
        set_hover_bond_id_for(self.canvas, None)
        hover_state_for(self.canvas).style = None

    def add_hover_preview_items(self, items: Sequence[QGraphicsItem]) -> None:
        if not items:
            return
        extend_hover_items_for(self.canvas, add_hover_preview_items_to_scene_for(self.canvas, items))

    def add_atom_hover_indicator(self, atom_id: int) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        radius = bond_length_px_for(self.canvas) * 0.25
        indicator = build_atom_hover_indicator_helper(QPointF(atom.x, atom.y), radius)
        add_hover_scene_item_for(self.canvas, indicator)
        append_hover_item_for(self.canvas, indicator)

    def add_bond_hover_indicator(self, bond_id: int | None) -> None:
        bond = self._bond_for_id(bond_id)
        if bond is None:
            return
        start_atom = atom_for_id(self.canvas, bond.a)
        end_atom = atom_for_id(self.canvas, bond.b)
        if start_atom is None or end_atom is None:
            return
        radius = bond_length_px_for(self.canvas) * 0.22
        indicator = build_bond_hover_indicator_helper(
            QPointF(start_atom.x, start_atom.y),
            QPointF(end_atom.x, end_atom.y),
            radius,
        )
        add_hover_scene_item_for(self.canvas, indicator)
        append_hover_item_for(self.canvas, indicator)

    def _bond_for_id(self, bond_id: int | None) -> Bond | None:
        return bond_for_id(self.canvas, bond_id)


__all__ = ["HoverSceneService"]
