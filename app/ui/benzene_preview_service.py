from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from ui.benzene_preview_renderer import clear_benzene_preview, rebuild_benzene_preview
from core.model import Atom

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class BenzenePreviewService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def clear_preview(self) -> None:
        self.canvas._benzene_preview_items = clear_benzene_preview(
            self.canvas.scene(),
            self.canvas._benzene_preview_items,
        )

    def render_preview(
        self,
        pos: QPointF,
        *,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
    ) -> None:
        self.clear_preview()
        result = self.canvas._structure_build_service.benzene_ring_points(
            pos,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
        )
        if result is None:
            return
        points, _ = result
        self.canvas._benzene_preview_items = rebuild_benzene_preview(
            self.canvas.scene(),
            points,
            base_pen=self.canvas.renderer.bond_pen(),
            atom_radius=max(0.6, self.canvas.renderer.style.bond_line_width * 0.6),
            create_inner_bond_item=self._create_inner_bond_item,
        )

    def _create_inner_bond_item(
        self,
        start: QPointF,
        end: QPointF,
        center: QPointF,
    ) -> QGraphicsItem | None:
        items = self.canvas._draw_ring_double_bond(
            Atom("C", start.x(), start.y()),
            Atom("C", end.x(), end.y()),
            center,
        )
        if len(items) < 2:
            return None
        return items[1]


__all__ = ["BenzenePreviewService"]
