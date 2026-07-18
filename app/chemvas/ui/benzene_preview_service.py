from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.domain.document import Atom
from chemvas.ui.benzene_preview_scene_access import (
    clear_benzene_preview_for_canvas,
    rebuild_benzene_preview_for_canvas,
)
from chemvas.ui.bond_graphics_access import draw_ring_double_bond_for
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.renderer_style_access import bond_line_width_for, bond_pen_for

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


class BenzenePreviewService:
    def __init__(self, canvas: CanvasView, *, structure_build_service=None) -> None:
        self.canvas = canvas
        self.insert_state = insert_state_for(canvas)
        self.structure_build_service = structure_build_service

    def clear_preview(self) -> None:
        self.insert_state.benzene_preview_items = clear_benzene_preview_for_canvas(
            self.canvas,
            self.insert_state.benzene_preview_items,
        )

    def render_preview(
        self,
        pos: QPointF,
        *,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
    ) -> None:
        if self.structure_build_service is None:
            return
        self.clear_preview()
        result = self.structure_build_service.benzene_ring_points(
            pos,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
        )
        if result is None:
            return
        points, _ = result
        self.insert_state.benzene_preview_items = rebuild_benzene_preview_for_canvas(
            self.canvas,
            points,
            base_pen=bond_pen_for(self.canvas),
            atom_radius=max(0.6, bond_line_width_for(self.canvas) * 0.6),
            create_inner_bond_item=self._create_inner_bond_item,
        )

    def _create_inner_bond_item(
        self,
        start: QPointF,
        end: QPointF,
        center: QPointF,
    ) -> QGraphicsItem | None:
        items = draw_ring_double_bond_for(
            self.canvas,
            Atom("C", start.x(), start.y()),
            Atom("C", end.x(), end.y()),
            center,
        )
        if len(items) < 2:
            return None
        return items[1]


__all__ = ["BenzenePreviewService"]
