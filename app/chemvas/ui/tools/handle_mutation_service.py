from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.features.rendering import arrow_with_moved_endpoint
from chemvas.features.selection import (
    orbital_rotation_angle as orbital_rotation_angle_helper,
)
from chemvas.features.selection import (
    orbital_scale_factor as orbital_scale_factor_helper,
)
from chemvas.ui.annotations.records import (
    require_shape_record_for,
    set_shape_record_for,
    shape_rect_of,
    shape_with_rect,
)
from chemvas.ui.selection.selection_handles import (
    control_from_midpoint,
)
from chemvas.ui.selection.selection_handles import (
    resized_shape_rect as resized_shape_rect_helper,
)
from chemvas.ui.tools.endpoint_snap_access import snap_drawing_point_for
from chemvas.ui.tools.handle_mutation_access import (
    clamp_curved_midpoint_for,
)

if TYPE_CHECKING:
    from chemvas.domain.document import Arrow
    from chemvas.ui.canvas.canvas_view import CanvasView


class HandleMutationService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def update_orbital_scale(self, item, pos: QPointF) -> None:
        center = QPointF(*item.orbital_state()["center"])
        scale = orbital_scale_factor_helper(center, pos, item.base_handle_dist)
        item.apply_orbital_state({"scale": scale})

    def update_shape_resize(self, item, anchor: str, pos: QPointF) -> None:
        shape = require_shape_record_for(self.canvas, item)
        new_rect = resized_shape_rect_helper(shape_rect_of(shape), anchor, pos)
        set_shape_record_for(self.canvas, item, shape_with_rect(shape, new_rect))
        self.canvas.services.selection.update_selection_outline()

    def update_orbital_rotate(self, item, pos: QPointF) -> None:
        center = QPointF(*item.orbital_state()["center"])
        angle = orbital_rotation_angle_helper(
            center,
            pos,
            snap_enabled=self.canvas.runtime_state.tool_settings_state.orbital_snap_enabled,
            snap_step=self.canvas.runtime_state.tool_settings_state.orbital_snap_step,
        )
        item.apply_orbital_state({"rotation": angle})

    def update_arrow_endpoint(
        self, item, pos: QPointF, endpoint: str, *, pressed: Arrow
    ) -> None:
        """Move either endpoint through the same record owner for every arrow kind.

        ``pressed`` is the record when the drag began. Each frame is computed
        from it rather than from the previous frame, so an end returned to its
        original position restores the record exactly.
        """
        if endpoint not in {"start", "end"}:
            return
        arrows = self.canvas.render_context.arrows
        record = arrows.record(item)
        moved = snap_drawing_point_for(self.canvas, pos, exclude=item)
        updated = arrow_with_moved_endpoint(
            record,
            pressed,
            (moved.x(), moved.y()),
            endpoint,
            bond_length=self.canvas.renderer.style.bond_length_px,
        )
        if updated is record:
            return
        arrows.set_record(item, updated)
        self.canvas.services.selection.update_selection_outline()

    def update_curved_control(self, item, pos: QPointF) -> None:
        arrows = self.canvas.render_context.arrows
        record = arrows.record(item)
        start, end = QPointF(*record.start), QPointF(*record.end)
        mid = clamp_curved_midpoint_for(self.canvas, start, end, pos)
        control = control_from_midpoint(start, end, mid)
        arrows.set_record(item, replace(record, control=(control.x(), control.y())))
        self.canvas.services.selection.update_selection_outline()


__all__ = ["HandleMutationService"]
