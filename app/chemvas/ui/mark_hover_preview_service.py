from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.ui.canvas_hover_state import hover_state_for, set_hover_atom_id_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.mark_item_access import (
    build_mark_item_for,
    mark_center_for_pointer_for,
    set_mark_center_for,
)
from chemvas.ui.renderer_style_access import bond_length_px_for

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


class MarkHoverPreviewService:
    def __init__(
        self, canvas: CanvasView, *, hit_testing_service, hover_scene_service=None
    ) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.hover_scene_service = hover_scene_service

    def _clear_hover_highlight(self) -> None:
        if self.hover_scene_service is None:
            return
        self.hover_scene_service.clear_hover_highlight()

    def _add_atom_hover_indicator(self, atom_id: int) -> None:
        if self.hover_scene_service is None:
            return
        self.hover_scene_service.add_atom_hover_indicator(atom_id)

    def _add_hover_preview_items(self, items) -> None:
        if self.hover_scene_service is None:
            return
        self.hover_scene_service.add_hover_preview_items(items)

    def add_mark_hover_preview(self, pos: QPointF) -> None:
        if self.hover_scene_service is None:
            return
        atom_id = self.hit_testing_service.find_atom_near(
            pos.x(),
            pos.y(),
            bond_length_px_for(self.canvas) * 0.35,
        )
        kind = tool_settings_state_for(self.canvas).mark_kind
        center = mark_center_for_pointer_for(self.canvas, pos, atom_id, kind=kind)
        scope = f"atom:{atom_id}" if atom_id is not None else "free"
        preview_key = (
            f"mark:{kind}:{scope}:{round(center.x(), 1)}:{round(center.y(), 1)}"
        )
        hover_state = hover_state_for(self.canvas)
        if atom_id == hover_state.atom_id and preview_key == hover_state.style:
            return
        self._clear_hover_highlight()
        if atom_id is not None:
            set_hover_atom_id_for(self.canvas, atom_id)
            self._add_atom_hover_indicator(atom_id)
        item = build_mark_item_for(self.canvas, kind)
        if item is None:
            return
        set_mark_center_for(self.canvas, item, center)
        hover_state_for(self.canvas).style = preview_key
        self._add_hover_preview_items([item])


__all__ = ["MarkHoverPreviewService"]
