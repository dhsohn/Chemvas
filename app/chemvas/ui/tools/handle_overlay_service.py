from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.ui.annotations.records import require_shape_record_for, shape_rect_of
from chemvas.ui.insert.preview_scene_renderer import clear_scene_items
from chemvas.ui.scene.scene_item_access import add_item_to_canvas_scene
from chemvas.ui.selection.selection_handles import (
    create_handle_item as create_handle_item_helper,
)
from chemvas.ui.selection.selection_handles import (
    curved_midpoint,
)
from chemvas.ui.selection.selection_handles import (
    mark_handle_snapped as mark_handle_snapped_helper,
)
from chemvas.ui.selection.selection_handles import (
    orbital_handle_positions as orbital_handle_positions_helper,
)
from chemvas.ui.selection.selection_handles import (
    shape_resize_handle_positions as shape_resize_handle_positions_helper,
)
from chemvas.ui.tools.endpoint_snap_access import snapped_points_among_for
from chemvas.ui.tools.handle_state import (
    set_active_handles_for,
    set_handle_target_for,
)

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_view import CanvasView


class HandleOverlayService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def clear_handles(self) -> None:
        scene = self.canvas.scene()
        if scene is None:
            return
        set_active_handles_for(
            self.canvas,
            clear_scene_items(
                scene, self.canvas.runtime_state.handle_state.active_handles
            ),
        )
        set_handle_target_for(self.canvas, None)

    def show_orbital_handles(self, item) -> None:
        self.clear_handles()
        data = item.data(1) or {}
        center = data.get("center")
        base_dist = data.get(
            "base_handle_dist", self.canvas.renderer.style.bond_length_px * 0.8
        )
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
        rect = shape_rect_of(require_shape_record_for(self.canvas, item))
        handles = [
            self.create_handle(pos, handle_type, item)
            for handle_type, pos in shape_resize_handle_positions_helper(rect)
        ]
        set_active_handles_for(self.canvas, handles)
        set_handle_target_for(self.canvas, item)

    def show_endpoint_handles(self, item) -> None:
        """Two handles, one per end, for an arrow or line without a control."""
        record = self.canvas.render_context.arrows.record(item)
        start, end = QPointF(*record.start), QPointF(*record.end)
        self.clear_handles()
        handles = [
            self.create_handle(start, "arrow_start", item),
            self.create_handle(end, "arrow_end", item),
        ]
        self.mark_snapped_handles(item, handles, (start, end))
        set_active_handles_for(self.canvas, handles)
        set_handle_target_for(self.canvas, item)

    def show_curved_handles(self, item) -> None:
        self.clear_handles()
        record = self.canvas.render_context.arrows.record(item)
        # ArrowRenderer.set_record gives every curved record its control.
        assert record.control is not None
        start, end = QPointF(*record.start), QPointF(*record.end)
        mid = curved_midpoint(start, QPointF(*record.control), end)
        control_handle = self.create_handle(mid, "curved_control", item)
        handles = [
            self.create_handle(start, "curved_start", item),
            control_handle,
            self.create_handle(end, "curved_end", item),
        ]
        self.mark_snapped_handles(item, [handles[0], handles[2]], (start, end))
        set_active_handles_for(self.canvas, handles)
        set_handle_target_for(self.canvas, item)

    def mark_snapped_handles(self, item, handles, points) -> None:
        """Fill the handles whose point has taken another item's endpoint."""
        caught = {
            (point.x(), point.y())
            for point in snapped_points_among_for(self.canvas, points, exclude=item)
        }
        for handle, point in zip(handles, points, strict=True):
            if (point.x(), point.y()) in caught:
                mark_handle_snapped_helper(handle)

    def create_handle(self, pos: QPointF, handle_type: str, target):
        handle = create_handle_item_helper(pos, handle_type, target)
        return add_item_to_canvas_scene(self.canvas, handle)


__all__ = ["HandleOverlayService"]
