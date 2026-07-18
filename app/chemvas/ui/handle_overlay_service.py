from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.features.selection import (
    create_handle_item as create_handle_item_helper,
)
from chemvas.features.selection import (
    orbital_handle_positions as orbital_handle_positions_helper,
)
from chemvas.features.selection import (
    shape_resize_handle_positions as shape_resize_handle_positions_helper,
)
from chemvas.ui.handle_mutation_access import (
    curved_midpoint_for,
    default_curved_control_for,
    update_curved_control_for,
)
from chemvas.ui.handle_overlay_scene_access import (
    add_handle_to_canvas_scene,
    clear_handle_items_for_canvas,
)
from chemvas.ui.handle_state import (
    active_handles_for,
    set_active_handles_for,
    set_handle_target_for,
)
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.selection_highlight_styler import selection_highlight_styler_for

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


class HandleOverlayService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def clear_handles(self) -> None:
        set_active_handles_for(
            self.canvas,
            clear_handle_items_for_canvas(self.canvas, active_handles_for(self.canvas)),
        )
        set_handle_target_for(self.canvas, None)
        selection_highlight_styler_for(self.canvas).clear_selection_highlight()

    def show_orbital_handles(self, item) -> None:
        self.clear_handles()
        selection_highlight_styler_for(self.canvas).set_selection_highlight([item])
        data = item.data(1) or {}
        center = data.get("center")
        base_dist = data.get("base_handle_dist", bond_length_px_for(self.canvas) * 0.8)
        if not isinstance(center, QPointF):
            center = item.boundingRect().center()
        scale_pos, rotate_pos = orbital_handle_positions_helper(
            center, float(base_dist)
        )
        set_active_handles_for(
            self.canvas,
            [
                self.create_handle(scale_pos, "orbital_scale", item),
                self.create_handle(rotate_pos, "orbital_rotate", item),
            ],
        )
        set_handle_target_for(self.canvas, item)

    def show_shape_handles(self, item) -> None:
        self.clear_handles()
        selection_highlight_styler_for(self.canvas).set_selection_highlight([item])
        data = item.data(1) or {}
        rect = data.get("rect")
        if rect is None:
            rect = item.sceneBoundingRect()
        handles = [
            self.create_handle(pos, handle_type, item)
            for handle_type, pos in shape_resize_handle_positions_helper(rect)
        ]
        set_active_handles_for(self.canvas, handles)
        set_handle_target_for(self.canvas, item)

    def show_curved_handles(self, item) -> None:
        self.clear_handles()
        selection_highlight_styler_for(self.canvas).set_selection_highlight([item])
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        control = data.get("control")
        if isinstance(start, QPointF) and isinstance(end, QPointF):
            if not isinstance(control, QPointF):
                control = default_curved_control_for(self.canvas, start, end)
            mid = curved_midpoint_for(self.canvas, start, control, end)
            update_curved_control_for(self.canvas, item, mid)
            mid = curved_midpoint_for(
                self.canvas, start, item.data(2).get("control"), end
            )
        else:
            mid = item.boundingRect().center()
        handles = [self.create_handle(mid, "curved_control", item)]
        if isinstance(start, QPointF) and isinstance(end, QPointF):
            handles = [
                self.create_handle(start, "curved_start", item),
                handles[0],
                self.create_handle(end, "curved_end", item),
            ]
        set_active_handles_for(self.canvas, handles)
        set_handle_target_for(self.canvas, item)

    def create_handle(self, pos: QPointF, handle_type: str, target):
        handle = create_handle_item_helper(pos, handle_type, target)
        return add_handle_to_canvas_scene(self.canvas, handle)


__all__ = ["HandleOverlayService"]
