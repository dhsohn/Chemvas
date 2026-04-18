from __future__ import annotations

from ui.selection_center_logic import center_for_atoms
from ui.selection_rotation_logic import selected_rotation_atom_ids


class CanvasRotationPreviewController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def begin_selection_rotation(self) -> bool:
        if self.canvas._rotation_group is not None:
            return False
        items = self.canvas.scene().selectedItems()
        if not items:
            return False
        atom_ids, bond_ids = self.canvas._selected_ids()
        atom_ids = selected_rotation_atom_ids(atom_ids, bond_ids, bonds=self.canvas.model.bonds)
        center = center_for_atoms(atom_ids, atoms=self.canvas.model.atoms)
        if center is None:
            return False
        self.canvas._rotation_group = self.canvas.scene().createItemGroup(items)
        self.canvas._rotation_group.setTransformOriginPoint(center)
        return True

    def update_rotation_preview(self, angle_degrees: float) -> None:
        if self.canvas._rotation_group is None:
            return
        self.canvas._rotation_group.setRotation(angle_degrees)

    def commit_selection_rotation(self) -> None:
        if self.canvas._rotation_group is None:
            return
        angle = self.canvas._rotation_group.rotation()
        self.canvas._rotation_group.setRotation(0.0)
        self.canvas.scene().destroyItemGroup(self.canvas._rotation_group)
        self.canvas._rotation_group = None
        if angle:
            self.canvas.rotate_selection(angle)


__all__ = ["CanvasRotationPreviewController"]
