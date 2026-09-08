from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF

from chemvas.features.annotations import normalized_shape_kind, shape_path
from chemvas.features.selection import (
    orbital_rotation_angle as orbital_rotation_angle_helper,
)
from chemvas.features.selection import (
    orbital_scale_factor as orbital_scale_factor_helper,
)
from chemvas.features.selection import (
    resized_shape_rect as resized_shape_rect_helper,
)
from chemvas.ui.endpoint_snap_access import snap_drawing_point_for
from chemvas.ui.handle_mutation_access import (
    clamp_curved_midpoint_for,
    control_from_midpoint_for,
    default_curved_control_for,
    orbital_snap_enabled_for,
    orbital_snap_step_for,
)
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_decoration_build_access import (
    apply_arrow_labels_for,
    build_arrow_item_for,
)
from chemvas.ui.selection_service_access import refresh_selection_outline_for

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView

# An endpoint drag stops here rather than collapsing an arrow or line into a
# dot, which renders as a bare arrow head or a wavy blob.
MIN_ARROW_LENGTH_BOND_LENGTHS = 0.1


class HandleMutationService:
    def __init__(self, canvas: CanvasView, *, curved_arrow_path_service=None) -> None:
        self.canvas = canvas
        self.curved_arrow_path_service = curved_arrow_path_service

    def update_orbital_scale(self, item, pos: QPointF) -> None:
        data = item.data(1) or {}
        center = data.get("center")
        base_dist = data.get("base_handle_dist", bond_length_px_for(self.canvas) * 0.8)
        if not isinstance(center, QPointF):
            center = item.boundingRect().center()
        scale = orbital_scale_factor_helper(center, pos, float(base_dist))
        item.setScale(scale)

    def update_shape_resize(self, item, anchor: str, pos: QPointF) -> None:
        data = item.data(1) or {}
        rect = data.get("rect")
        if not isinstance(rect, QRectF):
            rect = item.sceneBoundingRect()
        new_rect = resized_shape_rect_helper(rect, anchor, pos)
        item.setPath(
            shape_path(new_rect, normalized_shape_kind(data.get("shape_kind")))
        )
        updated = dict(data)
        updated["rect"] = new_rect
        item.setData(1, updated)
        refresh_selection_outline_for(self.canvas)

    def update_orbital_rotate(self, item, pos: QPointF) -> None:
        data = item.data(1) or {}
        center = data.get("center")
        if not isinstance(center, QPointF):
            center = item.boundingRect().center()
        angle = orbital_rotation_angle_helper(
            center,
            pos,
            snap_enabled=orbital_snap_enabled_for(self.canvas),
            snap_step=orbital_snap_step_for(self.canvas),
        )
        item.setRotation(angle)

    def update_arrow_endpoint(self, item, pos: QPointF, endpoint: str) -> None:
        """Move one end of a non-curved arrow or line to ``pos``.

        The item is rebuilt from its own kind, so an arc keeps its sweep and an
        equilibrium pair keeps its harpoons. A drag that would shrink the item
        below a usable length is refused rather than leaving a degenerate arrow
        behind.
        """
        if endpoint not in {"start", "end"}:
            return
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        if not isinstance(start, QPointF) or not isinstance(end, QPointF):
            return
        moved = snap_drawing_point_for(self.canvas, pos, exclude=item)
        if endpoint == "start":
            start, anchor = moved, end
        else:
            end, anchor = moved, start
        if math.hypot(moved.x() - anchor.x(), moved.y() - anchor.y()) < (
            bond_length_px_for(self.canvas) * MIN_ARROW_LENGTH_BOND_LENGTHS
        ):
            return
        kind = str(item.data(0) or "arrow")
        rebuilt = build_arrow_item_for(self.canvas, start, end, kind)
        # Arrow geometry is absolute, but a moved item carries its offset in
        # pos(); clear it or the rebuilt path renders shifted by that delta.
        item.setPos(0.0, 0.0)
        item.setPath(rebuilt.path())
        pen = rebuilt.pen()
        if data.get("color"):
            pen.setColor(item.pen().color())
        item.setPen(pen)
        item.setBrush(rebuilt.brush())
        data["start"] = start
        data["end"] = end
        item.setData(2, data)
        if data.get("labels"):
            apply_arrow_labels_for(self.canvas, item, data["labels"])
        refresh_selection_outline_for(self.canvas)

    def update_curved_control(self, item, pos: QPointF) -> None:
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        double = data.get("double", False)
        if not isinstance(start, QPointF) or not isinstance(end, QPointF):
            return
        mid = clamp_curved_midpoint_for(self.canvas, start, end, pos)
        control = control_from_midpoint_for(self.canvas, start, end, mid)
        if self.curved_arrow_path_service is not None:
            self.curved_arrow_path_service.set_curved_arrow_path(
                item, start, end, control, double
            )
        data["control"] = control
        item.setData(2, data)
        if data.get("labels"):
            apply_arrow_labels_for(self.canvas, item, data["labels"])
        refresh_selection_outline_for(self.canvas)

    def update_curved_endpoint(self, item, pos: QPointF, endpoint: str) -> None:
        """Move one end of a curved arrow to ``pos``.

        A curved arrow's ends carry the same kind of handle as every other
        arrow's, so they snap the same way: another item's endpoint first,
        then the grid, and never this item's own far end. A drag that would
        collapse the curve onto that far end is refused, which snapping
        otherwise makes easy to do by accident.
        """
        if endpoint not in {"start", "end"}:
            return
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        control = data.get("control")
        double = data.get("double", False)
        if not isinstance(start, QPointF) or not isinstance(end, QPointF):
            return
        moved = QPointF(snap_drawing_point_for(self.canvas, pos, exclude=item))
        if endpoint == "start":
            start, anchor = moved, end
        else:
            end, anchor = moved, start
        if math.hypot(moved.x() - anchor.x(), moved.y() - anchor.y()) < (
            bond_length_px_for(self.canvas) * MIN_ARROW_LENGTH_BOND_LENGTHS
        ):
            return
        if not isinstance(control, QPointF):
            control = default_curved_control_for(self.canvas, start, end)
        if self.curved_arrow_path_service is not None:
            self.curved_arrow_path_service.set_curved_arrow_path(
                item, start, end, control, double
            )
        data["start"] = start
        data["end"] = end
        data["control"] = control
        item.setData(2, data)
        if data.get("labels"):
            apply_arrow_labels_for(self.canvas, item, data["labels"])
        refresh_selection_outline_for(self.canvas)


__all__ = ["HandleMutationService"]
