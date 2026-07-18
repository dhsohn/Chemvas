from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.ui.bond_preview_access import (
    bond_hover_endpoint_for,
    build_bond_preview_items_for,
)
from chemvas.ui.canvas_hover_state import hover_preview_state_for
from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.renderer_style_access import bond_length_px_for

if TYPE_CHECKING:
    from chemvas.domain.document import Bond
    from chemvas.ui.canvas_view import CanvasView


class BondHoverPreviewService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        hover_scene_service=None,
        active_tool_name_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.hover_scene_service = hover_scene_service
        self._active_tool_name = active_tool_name_provider or (lambda: None)

    def _add_hover_preview_items(self, items) -> None:
        if self.hover_scene_service is None:
            return
        self.hover_scene_service.add_hover_preview_items(items)

    def add_bond_style_hover_preview(self, bond: Bond) -> None:
        if self.hover_scene_service is None:
            return
        if self._active_tool_name() != "bond":
            return
        style = tool_settings_state_for(self.canvas).active_bond_style
        if style not in {"wedge", "hash"}:
            return
        a = atom_for_id(self.canvas, bond.a)
        b = atom_for_id(self.canvas, bond.b)
        if a is None or b is None:
            return
        hover_preview_state_for(self.canvas).style = style
        items = build_bond_preview_items_for(
            self.canvas,
            QPointF(a.x, a.y),
            QPointF(b.x, b.y),
            bond.a,
            bond.b,
        )
        self._add_hover_preview_items(items)

    def add_bond_tool_hover_preview(self, atom_id: int, pos: QPointF) -> None:
        if self.hover_scene_service is None:
            return
        if self._active_tool_name() != "bond":
            return
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        start = QPointF(atom.x, atom.y)
        end = bond_hover_endpoint_for(self.canvas, start, pos, atom_id)
        items = build_bond_preview_items_for(self.canvas, start, end, atom_id, None)
        self._add_hover_preview_items(items)

    def add_free_bond_hover_preview(self, pos: QPointF) -> None:
        if self.hover_scene_service is None:
            return
        start = QPointF(pos.x(), pos.y())
        end = QPointF(pos.x() + bond_length_px_for(self.canvas), pos.y())
        items = build_bond_preview_items_for(self.canvas, start, end)
        self._add_hover_preview_items(items)


__all__ = ["BondHoverPreviewService"]
