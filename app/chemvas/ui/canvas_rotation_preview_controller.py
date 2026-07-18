from __future__ import annotations

from chemvas.ui.canvas_rotation_preview_state import rotation_preview_state_for
from chemvas.ui.scene_item_access import (
    create_scene_item_group,
    destroy_scene_item_group,
)


class CanvasRotationPreviewController:
    def __init__(self, canvas, *, scene_transform_controller) -> None:
        self.canvas = canvas
        self.scene_transform = scene_transform_controller

    def begin_selection_rotation(self) -> bool:
        state = rotation_preview_state_for(self.canvas)
        if state.group is not None:
            return False
        preview = self.scene_transform.rotation_selection_preview()
        if preview is None:
            return False
        state.group = create_scene_item_group(self.canvas, preview.items)
        state.group.setTransformOriginPoint(preview.center)
        position_items = getattr(preview, "position_items", [])
        if position_items:
            state.position_snapshots = (
                self.scene_transform.rotation_position_preview_snapshots(position_items)
            )
        else:
            state.position_snapshots = []
        state.center = preview.center
        return True

    def update_rotation_preview(self, angle_degrees: float) -> None:
        state = rotation_preview_state_for(self.canvas)
        group = state.group
        if group is None:
            return
        group.setRotation(angle_degrees)
        if state.center is not None and state.position_snapshots:
            self.scene_transform.apply_rotation_position_preview(
                state.position_snapshots,
                center=state.center,
                angle_degrees=angle_degrees,
            )

    def commit_selection_rotation(self) -> None:
        state = rotation_preview_state_for(self.canvas)
        if state.group is None:
            return
        group = state.group
        angle = group.rotation()
        group.setRotation(0.0)
        if state.position_snapshots:
            self.scene_transform.restore_rotation_position_preview(
                state.position_snapshots
            )
        destroy_scene_item_group(self.canvas, group)
        state.group = None
        state.position_snapshots = []
        state.center = None
        if angle:
            self.scene_transform.rotate_selected_items(angle)


__all__ = ["CanvasRotationPreviewController"]
