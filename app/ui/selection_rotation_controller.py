from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from core.history import SetAtomPositionsCommand

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SelectionRotationController:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def begin_selection_3d_rotation(
        self,
        axis_hint: int | None = None,
        press_pos: QPointF | None = None,
    ) -> bool:
        start_projection_center_3d = self.canvas._projection_center_3d
        start_projection_anchor_2d = self.canvas._projection_anchor_2d
        self.canvas._rotation_start_coords_3d = {}
        self.canvas._rotation_coord_atom_ids = set()
        atom_ids, bond_ids = self.canvas._selected_ids()
        explicit_atom_ids = set(atom_ids)
        for item in self.canvas.scene().selectedItems():
            if item.data(0) != "mark":
                continue
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int):
                explicit_atom_ids.add(atom_id)
        rotation_atom_ids = set(explicit_atom_ids)
        for bond_id in bond_ids:
            if not (0 <= bond_id < len(self.canvas.model.bonds)):
                continue
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                continue
            rotation_atom_ids.add(bond.a)
            rotation_atom_ids.add(bond.b)
        if not rotation_atom_ids and not bond_ids:
            return False
        axis = None
        if isinstance(axis_hint, int):
            axis = self.canvas._axis_from_rotation_hint(axis_hint, rotation_atom_ids, press_pos=press_pos)
        if axis is not None:
            bond_id, rotate_ids = axis
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                return False
            axis_a = bond.a
            axis_b = bond.b
            self.canvas._rotation_selection_ids = (set(atom_ids), set(bond_ids))
            self.canvas._rotation_base_coords = {}
            for atom_id in rotate_ids | {axis_a, axis_b}:
                coords = self.canvas._current_atom_coords_3d(atom_id)
                if coords is None:
                    continue
                self.canvas._rotation_base_coords[atom_id] = coords
                self.canvas._rotation_start_coords_3d[atom_id] = coords
            relevant_atom_ids = rotate_ids | {axis_a, axis_b}
            self.canvas._rotation_coord_atom_ids = set(self.canvas._rotation_base_coords)
            self.canvas._rotation_base_coords = self.canvas._flatten_planar_fragments(
                relevant_atom_ids,
                self.canvas._rotation_base_coords,
            )
            for atom_id in relevant_atom_ids:
                coords = self.canvas._rotation_base_coords.get(atom_id)
                if coords is not None:
                    self.canvas.atom_coords_3d[atom_id] = coords
            if not self.canvas._rotation_base_coords:
                return False
            axis_center = (
                (self.canvas._rotation_base_coords[axis_a][0] + self.canvas._rotation_base_coords[axis_b][0]) * 0.5,
                (self.canvas._rotation_base_coords[axis_a][1] + self.canvas._rotation_base_coords[axis_b][1]) * 0.5,
                (self.canvas._rotation_base_coords[axis_a][2] + self.canvas._rotation_base_coords[axis_b][2]) * 0.5,
            )
            self.canvas._rotation_axis_bond_id = bond_id
            self.canvas._rotation_axis_atoms = (axis_a, axis_b)
            self.canvas._rotation_total_angle = 0.0
            self.canvas._rotation_mode = "bond"
            self.canvas._rotation_free_angle_x = 0.0
            self.canvas._rotation_free_angle_y = 0.0
            self.canvas.rotation_atom_ids = set(rotate_ids)
            self.canvas._rotation_start_positions = {
                atom_id: (self.canvas.model.atoms[atom_id].x, self.canvas.model.atoms[atom_id].y)
                for atom_id in self.canvas.rotation_atom_ids
                if atom_id in self.canvas.model.atoms
            }
            self.canvas.rotation_center_3d = axis_center
            self.canvas._projection_center_3d = self.canvas.rotation_center_3d
            atom_a = self.canvas.model.atoms.get(axis_a)
            atom_b = self.canvas.model.atoms.get(axis_b)
            if atom_a is not None and atom_b is not None:
                self.canvas._projection_anchor_2d = (
                    (atom_a.x + atom_b.x) * 0.5,
                    (atom_a.y + atom_b.y) * 0.5,
                )
            else:
                self.canvas._projection_anchor_2d = (axis_center[0], axis_center[1])
            self.canvas._rotation_start_projection_center_3d = start_projection_center_3d
            self.canvas._rotation_start_projection_anchor_2d = start_projection_anchor_2d
            scale_atom_ids = set(self.canvas.rotation_atom_ids)
            scale_atom_ids.update((axis_a, axis_b))
            self.canvas._rotation_base_bond_length = self.canvas._average_bond_length_for_atoms(
                scale_atom_ids,
                self.canvas._rotation_base_coords,
            )
            return True
        self.canvas._rotation_selection_ids = (set(atom_ids), set(bond_ids))
        screen_center = self.canvas._bounding_box_center_for_atoms(rotation_atom_ids)
        if screen_center is None:
            return False
        anchor_2d = (screen_center.x(), screen_center.y())
        raw_coords: dict[int, tuple[float, float, float]] = {}
        for atom_id in rotation_atom_ids:
            coords = self.canvas._current_atom_coords_3d(atom_id)
            if coords is None:
                continue
            raw_coords[atom_id] = coords
        if not raw_coords:
            return False
        self.canvas._rotation_start_coords_3d = dict(raw_coords)
        self.canvas._rotation_coord_atom_ids = set(raw_coords)
        center_z = sum(coords[2] for coords in raw_coords.values()) / len(raw_coords)
        center = (screen_center.x(), screen_center.y(), center_z)
        self.canvas._rotation_base_coords = {}
        for atom_id, coords in raw_coords.items():
            atom = self.canvas.model.atoms.get(atom_id)
            if atom is None:
                continue
            self.canvas._rotation_base_coords[atom_id] = self.canvas._unproject_scene_point_3d(
                QPointF(atom.x, atom.y),
                coords[2],
                center_3d=center,
                anchor_2d=anchor_2d,
            )
        self.canvas._rotation_base_coords = self.canvas._flatten_planar_fragments(
            rotation_atom_ids,
            self.canvas._rotation_base_coords,
        )
        for atom_id, coords in self.canvas._rotation_base_coords.items():
            self.canvas.atom_coords_3d[atom_id] = coords
        self.canvas._rotation_axis_bond_id = None
        self.canvas._rotation_axis_atoms = None
        self.canvas._rotation_total_angle = 0.0
        self.canvas._rotation_mode = "rigid"
        self.canvas._rotation_free_angle_x = 0.0
        self.canvas._rotation_free_angle_y = 0.0
        self.canvas.rotation_atom_ids = set(rotation_atom_ids)
        self.canvas._rotation_start_positions = {
            atom_id: (self.canvas.model.atoms[atom_id].x, self.canvas.model.atoms[atom_id].y)
            for atom_id in self.canvas.rotation_atom_ids
            if atom_id in self.canvas.model.atoms
        }
        self.canvas.rotation_center_3d = center
        self.canvas._projection_center_3d = center
        self.canvas._projection_anchor_2d = anchor_2d
        self.canvas._rotation_start_projection_center_3d = start_projection_center_3d
        self.canvas._rotation_start_projection_anchor_2d = start_projection_anchor_2d
        scale_atom_ids = set(self.canvas.rotation_atom_ids)
        self.canvas._rotation_base_bond_length = self.canvas._average_bond_length_for_atoms(
            scale_atom_ids,
            self.canvas._rotation_base_coords,
        )
        return True

    def update_selection_3d_rotation(self, delta_x: float, delta_y: float) -> None:
        if not self.canvas.rotation_atom_ids:
            return
        sensitivity = 0.005
        if self.canvas._rotation_mode == "rigid":
            angle_x = delta_y * sensitivity
            angle_y = delta_x * sensitivity
            if abs(angle_x) < 1e-9 and abs(angle_y) < 1e-9:
                return
            self.canvas._rotation_free_angle_x += angle_x
            self.canvas._rotation_free_angle_y += angle_y
            center = self.canvas.rotation_center_3d
            if center is None:
                return
            cx, cy, cz = center
            cos_y = math.cos(self.canvas._rotation_free_angle_y)
            sin_y = math.sin(self.canvas._rotation_free_angle_y)
            cos_x = math.cos(self.canvas._rotation_free_angle_x)
            sin_x = math.sin(self.canvas._rotation_free_angle_x)
            rotated_coords: dict[int, tuple[float, float, float]] = {}
            for atom_id in self.canvas.rotation_atom_ids:
                coords = self.canvas._rotation_base_coords.get(atom_id)
                if coords is None:
                    continue
                x, y, z = coords
                x -= cx
                y -= cy
                z -= cz
                rx = x * cos_y + z * sin_y
                rz = -x * sin_y + z * cos_y
                ry = y * cos_x - rz * sin_x
                rz2 = y * sin_x + rz * cos_x
                x = rx + cx
                y = ry + cy
                z = rz2 + cz
                rotated_coords[atom_id] = (x, y, z)
            self.canvas._apply_projected_atom_positions(self.canvas.rotation_atom_ids, rotated_coords)
            self.canvas._redraw_bonds_for_atoms(self.canvas.rotation_atom_ids)
            self.canvas._update_ring_fills_for_atoms(self.canvas.rotation_atom_ids)
            self.canvas._update_selection_outline()
            return
        if self.canvas._rotation_axis_atoms is None:
            return
        angle_delta = delta_x if abs(delta_x) >= abs(delta_y) else delta_y
        angle_delta *= sensitivity
        if abs(angle_delta) < 1e-9:
            return
        self.canvas._rotation_total_angle += angle_delta
        axis_a, axis_b = self.canvas._rotation_axis_atoms
        axis_start = self.canvas._rotation_base_coords.get(axis_a)
        axis_end = self.canvas._rotation_base_coords.get(axis_b)
        if axis_start is None or axis_end is None:
            return
        rotated_coords = {}
        for atom_id in self.canvas.rotation_atom_ids:
            coords = self.canvas._rotation_base_coords.get(atom_id)
            if coords is None:
                continue
            rotated = self.canvas._rotate_point_around_axis(
                coords,
                axis_start,
                axis_end,
                self.canvas._rotation_total_angle,
            )
            rotated_coords[atom_id] = rotated
        self.canvas._apply_projected_atom_positions(self.canvas.rotation_atom_ids, rotated_coords)
        self.canvas._redraw_bonds_for_atoms(self.canvas.rotation_atom_ids)
        self.canvas._update_ring_fills_for_atoms(self.canvas.rotation_atom_ids)
        self.canvas._update_selection_outline()

    def end_selection_3d_rotation(self) -> None:
        selection_ids = self.canvas._rotation_selection_ids
        rotated_atoms = set(self.canvas.rotation_atom_ids)
        before_positions = dict(self.canvas._rotation_start_positions)
        before_coords_3d = dict(self.canvas._rotation_start_coords_3d)
        before_projection_center_3d = self.canvas._rotation_start_projection_center_3d
        before_projection_anchor_2d = self.canvas._rotation_start_projection_anchor_2d
        after_coords_3d = {
            atom_id: self.canvas.atom_coords_3d[atom_id]
            for atom_id in self.canvas._rotation_coord_atom_ids
            if atom_id in self.canvas.atom_coords_3d
        }
        after_projection_center_3d = self.canvas._projection_center_3d
        after_projection_anchor_2d = self.canvas._projection_anchor_2d
        self.canvas.rotation_atom_ids = set()
        self.canvas.rotation_center_3d = None
        self.canvas._rotation_base_coords = {}
        self.canvas._rotation_total_angle = 0.0
        self.canvas._rotation_mode = None
        self.canvas._rotation_free_angle_x = 0.0
        self.canvas._rotation_free_angle_y = 0.0
        self.canvas._rotation_base_bond_length = None
        self.canvas._rotation_selection_ids = None
        self.canvas._rotation_axis_bond_id = None
        self.canvas._rotation_axis_atoms = None
        self.canvas._rotation_start_positions = {}
        self.canvas._rotation_start_coords_3d = {}
        self.canvas._rotation_start_projection_center_3d = None
        self.canvas._rotation_start_projection_anchor_2d = None
        self.canvas._rotation_coord_atom_ids = set()
        after_positions = {
            atom_id: (self.canvas.model.atoms[atom_id].x, self.canvas.model.atoms[atom_id].y)
            for atom_id in rotated_atoms
            if atom_id in self.canvas.model.atoms
        }
        positions_changed = bool(before_positions and after_positions and before_positions != after_positions)
        coords_changed = bool(before_coords_3d and after_coords_3d and before_coords_3d != after_coords_3d)
        if positions_changed or coords_changed:
            command = SetAtomPositionsCommand(
                before_positions=before_positions,
                after_positions=after_positions,
                before_coords_3d=before_coords_3d or None,
                after_coords_3d=after_coords_3d or None,
                restore_projection_state=True,
                before_projection_center_3d=before_projection_center_3d,
                after_projection_center_3d=after_projection_center_3d,
                before_projection_anchor_2d=before_projection_anchor_2d,
                after_projection_anchor_2d=after_projection_anchor_2d,
            )
            self.canvas._push_command(command)
        if selection_ids is not None:
            self.canvas._restore_selection_from_ids(*selection_ids)
        self.canvas._emit_selection_info()


__all__ = ["SelectionRotationController"]
