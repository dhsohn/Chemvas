from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class MarkHoverPreviewService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def _clear_hover_highlight(self) -> None:
        self.canvas._hover_scene_service.clear_hover_highlight()

    def _add_atom_hover_indicator(self, atom_id: int) -> None:
        self.canvas._hover_scene_service.add_atom_hover_indicator(atom_id)

    def _add_hover_preview_items(self, items) -> None:
        self.canvas._hover_scene_service.add_hover_preview_items(items)

    def add_mark_hover_preview(self, pos: QPointF) -> None:
        atom_id = self.canvas.find_atom_near(
            pos.x(),
            pos.y(),
            self.canvas.renderer.style.bond_length_px * 0.35,
        )
        kind = self.canvas.mark_kind
        center = self.canvas._mark_center_for_pointer(pos, atom_id, kind=kind)
        scope = f"atom:{atom_id}" if atom_id is not None else "free"
        preview_key = f"mark:{kind}:{scope}:{round(center.x(), 1)}:{round(center.y(), 1)}"
        if atom_id == self.canvas.hover_atom_id and preview_key == self.canvas._hover_preview_style:
            return
        self._clear_hover_highlight()
        if atom_id is not None:
            self.canvas.hover_atom_id = atom_id
            self._add_atom_hover_indicator(atom_id)
        item = self.canvas._build_mark_item(kind)
        if item is None:
            return
        self.canvas._set_mark_center(item, center)
        self.canvas._hover_preview_style = preview_key
        self._add_hover_preview_items([item])


__all__ = ["MarkHoverPreviewService"]
