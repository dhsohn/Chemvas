from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.atom_coords_access import (
    atom_coords_3d_for,
    current_atom_coords_3d_for,
)
from ui.canvas_model_access import atom_for_id, atoms_for, bond_for_id, bonds_for
from ui.canvas_rotation_state import rotation_state_for
from ui.history_commands import _restore_scene_runtime_snapshot, _scene_runtime_snapshot
from ui.selection_collection_access import selected_ids_for
from ui.selection_rotation_access import (
    apply_projected_atom_positions_for,
    average_bond_length_for_atoms_for,
    flatten_planar_fragments_for,
    rotate_point_around_axis_for,
    unproject_scene_point_3d_for,
    update_ring_fills_for_atoms_for,
)
from ui.selection_rotation_geometry import (
    axis_rotated_coords,
    dominant_axis_angle_from_drag,
    rigid_rotated_coords,
    rigid_rotation_angles_from_drag,
)
from ui.selection_rotation_history import build_selection_rotation_command
from ui.selection_rotation_session import begin_selection_rotation_session
from ui.selection_scene_access import scene_selected_items_for
from ui.selection_service_access import refresh_selection_outline_for
from ui.selection_style_access import (
    emit_selection_info_for,
    restore_selection_from_ids_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SelectionRotationController:
    def __init__(self, canvas: CanvasView, *, move_controller=None, graph_service, history_service=None) -> None:
        self.canvas = canvas
        self.move_controller = move_controller
        self.graph_service = graph_service
        self.rotation = rotation_state_for(canvas)
        self.history = history_service

    def selected_ids(self):
        return selected_ids_for(self.canvas)

    def selected_scene_items(self):
        return scene_selected_items_for(self.canvas)

    @property
    def atoms(self):
        return atoms_for(self.canvas)

    @property
    def bonds(self):
        return bonds_for(self.canvas)

    def atom(self, atom_id: int):
        return atom_for_id(self.canvas, atom_id)

    def bond(self, bond_id: int):
        return bond_for_id(self.canvas, bond_id)

    def atom_positions(self, atom_ids: set[int]) -> dict[int, tuple[float, float]]:
        positions = {}
        for atom_id in atom_ids:
            atom = self.atom(atom_id)
            if atom is not None:
                positions[atom_id] = (atom.x, atom.y)
        return positions

    def axis_from_rotation_hint(
        self,
        axis_hint: int,
        rotation_atom_ids: set[int],
        *,
        press_pos: QPointF | None = None,
    ):
        return self.graph_service.axis_from_rotation_hint(
            axis_hint,
            rotation_atom_ids,
            press_pos=press_pos,
        )

    def current_atom_coords_3d(self, atom_id: int):
        return current_atom_coords_3d_for(self.canvas, atom_id)

    def flatten_planar_fragments(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> dict[int, tuple[float, float, float]]:
        return flatten_planar_fragments_for(
            self.canvas,
            atom_ids,
            coords,
            bond_in_cycle=self.graph_service.bond_in_cycle,
        )

    def average_bond_length_for_atoms(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> float | None:
        return average_bond_length_for_atoms_for(self.canvas, atom_ids, coords)

    def unproject_scene_point_3d(
        self,
        point: QPointF,
        z: float,
        *,
        center_3d: tuple[float, float, float],
        anchor_2d: tuple[float, float],
    ) -> tuple[float, float, float]:
        return unproject_scene_point_3d_for(
            self.canvas,
            point,
            z,
            center_3d=center_3d,
            anchor_2d=anchor_2d,
        )

    def apply_projected_atom_positions(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> None:
        apply_projected_atom_positions_for(self.canvas, atom_ids, coords)

    def refresh_atom_geometry(self, atom_ids: set[int]) -> None:
        if self.move_controller is not None:
            self.move_controller.redraw_bonds_for_atoms(atom_ids)
        update_ring_fills_for_atoms_for(self.canvas, atom_ids)
        refresh_selection_outline_for(self.canvas)

    def rotate_point_around_axis(self, coords, axis_start, axis_end, angle: float):
        return rotate_point_around_axis_for(self.canvas, coords, axis_start, axis_end, angle)

    def restore_selection_from_ids(self, atom_ids: set[int], bond_ids: set[int]) -> None:
        restore_selection_from_ids_for(self.canvas, atom_ids, bond_ids)

    def emit_selection_info(self) -> None:
        emit_selection_info_for(self.canvas)

    def _history_runtime_rollback(self) -> Callable[[], None]:
        history_service = self.history
        state = getattr(history_service, "state", None)
        history = getattr(state, "history", None)
        redo_stack = getattr(state, "redo_stack", None)
        if state is None or not isinstance(history, list) or not isinstance(redo_stack, list):
            return lambda: None
        history_items = list(history)
        redo_items = list(redo_stack)

        def restore() -> None:
            history[:] = history_items
            redo_stack[:] = redo_items
            state.history = history
            state.redo_stack = redo_stack
            notify_change = getattr(history_service, "notify_change", None)
            if callable(notify_change):
                try:
                    notify_change()
                except Exception:
                    pass

        return restore

    def begin_selection_3d_rotation(
        self,
        axis_hint: int | None = None,
        press_pos: QPointF | None = None,
    ) -> bool:
        return begin_selection_rotation_session(
            self,
            self.rotation,
            axis_hint=axis_hint,
            press_pos=press_pos,
        )

    def update_selection_3d_rotation(self, delta_x: float, delta_y: float) -> None:
        state = self.rotation
        if not state.atom_ids:
            return
        if state.mode == "rigid":
            angle_x, angle_y = rigid_rotation_angles_from_drag(delta_x, delta_y)
            if abs(angle_x) < 1e-9 and abs(angle_y) < 1e-9:
                return
            state.free_angle_x += angle_x
            state.free_angle_y += angle_y
            center = state.center_3d
            if center is None:
                return
            rotated_coords = rigid_rotated_coords(
                state.atom_ids,
                state.base_coords,
                center,
                angle_x=state.free_angle_x,
                angle_y=state.free_angle_y,
            )
            self.apply_projected_atom_positions(state.atom_ids, rotated_coords)
            self.refresh_atom_geometry(state.atom_ids)
            return
        if state.axis_atoms is None:
            return
        angle_delta = dominant_axis_angle_from_drag(delta_x, delta_y)
        if abs(angle_delta) < 1e-9:
            return
        state.total_angle += angle_delta
        axis_a, axis_b = state.axis_atoms
        axis_start = state.base_coords.get(axis_a)
        axis_end = state.base_coords.get(axis_b)
        if axis_start is None or axis_end is None:
            return
        rotated_coords = axis_rotated_coords(
            state.atom_ids,
            state.base_coords,
            axis_start,
            axis_end,
            state.total_angle,
            rotate_point=self.rotate_point_around_axis,
        )
        self.apply_projected_atom_positions(state.atom_ids, rotated_coords)
        self.refresh_atom_geometry(state.atom_ids)

    def end_selection_3d_rotation(self) -> None:
        state = self.rotation
        selection_ids = state.selection_ids
        rotated_atoms = set(state.atom_ids)
        before_positions = dict(state.start_positions)
        before_coords_3d = dict(state.start_coords_3d)
        before_projection_center_3d = state.start_projection_center_3d
        before_projection_anchor_2d = state.start_projection_anchor_2d
        current_coords_3d = atom_coords_3d_for(self.canvas)
        after_coords_3d = {
            atom_id: current_coords_3d[atom_id]
            for atom_id in state.coord_atom_ids
            if atom_id in current_coords_3d
        }
        after_projection_center_3d = state.projection_center_3d
        after_projection_anchor_2d = state.projection_anchor_2d
        after_positions = self.atom_positions(rotated_atoms)
        command = build_selection_rotation_command(
            before_positions=before_positions,
            after_positions=after_positions,
            before_coords_3d=before_coords_3d,
            after_coords_3d=after_coords_3d,
            before_projection_center_3d=before_projection_center_3d,
            after_projection_center_3d=after_projection_center_3d,
            before_projection_anchor_2d=before_projection_anchor_2d,
            after_projection_anchor_2d=after_projection_anchor_2d,
        )
        scene_snapshot = _scene_runtime_snapshot(self.canvas)
        restore_history = self._history_runtime_rollback()
        try:
            if command is not None:
                self.history.push(command)
            if selection_ids is not None:
                self.restore_selection_from_ids(*selection_ids)
            self.emit_selection_info()
        except BaseException as error:
            rollback_errors: list[BaseException] = []
            try:
                restore_history()
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
            try:
                _restore_scene_runtime_snapshot(scene_snapshot)
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
            for cleanup_error in rollback_errors:
                error.add_note(f"Rotation finalization rollback also failed: {cleanup_error!r}")
            raise
        # The session remains the source for a retry until every finalization
        # phase succeeds. Clearing earlier loses the before/after command data
        # when history push or selection/UI refresh fails part-way.
        state.clear_session()


__all__ = ["SelectionRotationController"]
