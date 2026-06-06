from __future__ import annotations

from ui.canvas_model_access import atoms_for, bonds_for
from ui.canvas_rotation_preview_state import rotation_preview_state_for
from ui.scene_item_access import create_scene_item_group, destroy_scene_item_group
from ui.selection_center_logic import center_for_atoms
from ui.selection_collection_access import selected_ids_for
from ui.selection_rotation_access import rotate_selection_for
from ui.selection_rotation_logic import selected_rotation_atom_ids
from ui.selection_scene_access import scene_selected_items_for


class CanvasRotationPreviewController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def begin_selection_rotation(self) -> bool:
        state = rotation_preview_state_for(self.canvas)
        if state.group is not None:
            return False
        items = scene_selected_items_for(self.canvas)
        if not items:
            return False
        atom_ids, bond_ids = selected_ids_for(self.canvas)
        atom_ids = selected_rotation_atom_ids(atom_ids, bond_ids, bonds=bonds_for(self.canvas))
        center = center_for_atoms(atom_ids, atoms=atoms_for(self.canvas))
        if center is None:
            return False
        state.group = create_scene_item_group(self.canvas, items)
        state.group.setTransformOriginPoint(center)
        return True

    def update_rotation_preview(self, angle_degrees: float) -> None:
        group = rotation_preview_state_for(self.canvas).group
        if group is None:
            return
        group.setRotation(angle_degrees)

    def commit_selection_rotation(self) -> None:
        state = rotation_preview_state_for(self.canvas)
        if state.group is None:
            return
        group = state.group
        angle = group.rotation()
        group.setRotation(0.0)
        destroy_scene_item_group(self.canvas, group)
        state.group = None
        if angle:
            rotate_selection_for(self.canvas, angle)


__all__ = ["CanvasRotationPreviewController"]
