from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.handle_interaction_logic import (
    clear_handle_items as clear_handle_items_helper,
)
from ui.handle_interaction_logic import (
    create_handle_item as create_handle_item_helper,
)
from ui.handle_interaction_logic import (
    orbital_handle_positions as orbital_handle_positions_helper,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class HandleOverlayService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def clear_handles(self) -> None:
        self.canvas._active_handles = clear_handle_items_helper(self.canvas.scene(), self.canvas._active_handles)
        self.canvas._handle_target = None
        self.canvas._clear_selection_highlight()

    def show_orbital_handles(self, item) -> None:
        self.clear_handles()
        self.canvas._set_selection_highlight([item])
        data = item.data(1) or {}
        center = data.get("center")
        base_dist = data.get("base_handle_dist", self.canvas.renderer.style.bond_length_px * 0.8)
        if not isinstance(center, QPointF):
            center = item.boundingRect().center()
        scale_pos, rotate_pos = orbital_handle_positions_helper(center, float(base_dist))
        self.canvas._active_handles = [
            self.create_handle(scale_pos, "orbital_scale", item),
            self.create_handle(rotate_pos, "orbital_rotate", item),
        ]
        self.canvas._handle_target = item

    def show_curved_handles(self, item) -> None:
        self.clear_handles()
        self.canvas._set_selection_highlight([item])
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        control = data.get("control")
        if isinstance(start, QPointF) and isinstance(end, QPointF):
            if not isinstance(control, QPointF):
                control = self.canvas._default_curved_control(start, end)
            mid = self.canvas._curved_midpoint(start, control, end)
            self.canvas._update_curved_control(item, mid)
            mid = self.canvas._curved_midpoint(start, item.data(2).get("control"), end)
        else:
            mid = item.boundingRect().center()
        handles = [self.create_handle(mid, "curved_control", item)]
        if isinstance(start, QPointF) and isinstance(end, QPointF):
            handles = [
                self.create_handle(start, "curved_start", item),
                handles[0],
                self.create_handle(end, "curved_end", item),
            ]
        self.canvas._active_handles = handles
        self.canvas._handle_target = item

    def create_handle(self, pos: QPointF, handle_type: str, target):
        handle = create_handle_item_helper(pos, handle_type, target)
        self.canvas.scene().addItem(handle)
        return handle


def handle_overlay_service_for(canvas) -> HandleOverlayService:
    return canvas._handle_overlay_service


__all__ = ["HandleOverlayService", "handle_overlay_service_for"]
