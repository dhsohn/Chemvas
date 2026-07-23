from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.features.selection import (
    axis_rotated_coords,
    dominant_axis_angle_from_drag,
    rigid_rotated_coords,
    rigid_rotation_angles_from_drag,
)
from chemvas.ui.atom_coords_access import (
    atom_coords_3d_for,
    current_atom_coords_3d_for,
)
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    atoms_for,
    bond_for_id,
    bonds_for,
)
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.selection_collection_access import selected_ids_for
from chemvas.ui.selection_rotation_access import (
    apply_projected_atom_positions_for,
    average_bond_length_for_atoms_for,
    flatten_planar_fragments_for,
    rotate_point_around_axis_for,
    unproject_scene_point_3d_for,
    update_ring_fills_for_atoms_for,
)
from chemvas.ui.selection_rotation_history import build_selection_rotation_command
from chemvas.ui.selection_rotation_preview_transaction import (
    _RotationPreviewAuthority,
    capture_rotation_preview_authority,
    run_rotation_preview_update,
)
from chemvas.ui.selection_rotation_session import begin_selection_rotation_session
from chemvas.ui.selection_scene_access import scene_selected_items_for
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.selection_style_access import (
    emit_selection_info_for,
    restore_selection_from_ids_for,
)

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


def _add_rotation_finalization_rollback_note(
    original_error: BaseException,
    cleanup_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(f"Rotation finalization rollback also failed: {cleanup_error!r}")
    except BaseException:
        return


class SelectionRotationController:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        move_controller=None,
        graph_service,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.move_controller = move_controller
        self.graph_service = graph_service
        self.rotation = rotation_state_for(canvas)
        self.history = history_service
        self._rotation_preview_authority: _RotationPreviewAuthority | None = None

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
            update_geometries = getattr(
                self.move_controller,
                "update_bond_geometries_for_atoms",
                None,
            )
            if callable(update_geometries):
                # Rotation never changes bond topology.  Updating the existing
                # primitives in place preserves scene membership/stacking and
                # avoids allocate-remove-add churn on every pointer frame.
                update_geometries(atom_ids)
            else:
                self.move_controller.redraw_bonds_for_atoms(atom_ids)
        preview = self._rotation_preview_authority
        if isinstance(
            preview, _RotationPreviewAuthority
        ) and preview.atom_ids == frozenset(atom_ids):
            update_ring_fills_for_atoms_for(
                self.canvas,
                atom_ids,
                ring_items=preview.affected_ring_items,
            )
        else:
            update_ring_fills_for_atoms_for(self.canvas, atom_ids)
        refresh_selection_outline_for(self.canvas)

    def rotate_point_around_axis(self, coords, axis_start, axis_end, angle: float):
        return rotate_point_around_axis_for(
            self.canvas, coords, axis_start, axis_end, angle
        )

    def restore_selection_from_ids(
        self, atom_ids: set[int], bond_ids: set[int]
    ) -> None:
        restore_selection_from_ids_for(self.canvas, atom_ids, bond_ids)

    def emit_selection_info(self) -> None:
        emit_selection_info_for(self.canvas)

    def begin_selection_3d_rotation(
        self,
        axis_hint: int | None = None,
        press_pos: QPointF | None = None,
    ) -> bool:
        if self._rotation_preview_authority is not None:
            raise RuntimeError("A selection rotation transaction is already active")

        def publish_preview() -> None:
            self._rotation_preview_authority = capture_rotation_preview_authority(
                self,
                set(self.rotation.atom_ids),
            )

        try:
            rotating = begin_selection_rotation_session(
                self,
                self.rotation,
                axis_hint=axis_hint,
                press_pos=press_pos,
                on_session_started=publish_preview,
            )
        except BaseException:
            preview = self._rotation_preview_authority
            self._rotation_preview_authority = None
            if preview is not None:
                preview.release()
            raise
        return rotating

    def update_selection_3d_rotation(self, delta_x: float, delta_y: float) -> None:
        state = self.rotation
        if not state.atom_ids:
            return
        if state.mode == "rigid":
            angle_x, angle_y = rigid_rotation_angles_from_drag(delta_x, delta_y)
            if abs(angle_x) < 1e-9 and abs(angle_y) < 1e-9:
                return
            center = state.center_3d
            if center is None:
                return
            next_angle_x = state.free_angle_x + angle_x
            next_angle_y = state.free_angle_y + angle_y

            def update_rigid_preview() -> None:
                state.free_angle_x = next_angle_x
                state.free_angle_y = next_angle_y
                rotated_coords = rigid_rotated_coords(
                    state.atom_ids,
                    state.base_coords,
                    center,
                    angle_x=next_angle_x,
                    angle_y=next_angle_y,
                )
                self.apply_projected_atom_positions(state.atom_ids, rotated_coords)
                self.refresh_atom_geometry(state.atom_ids)

            run_rotation_preview_update(
                self,
                set(state.atom_ids),
                update_rigid_preview,
            )
            return
        if state.axis_atoms is None:
            return
        angle_delta = dominant_axis_angle_from_drag(delta_x, delta_y)
        if abs(angle_delta) < 1e-9:
            return
        axis_a, axis_b = state.axis_atoms
        axis_start = state.base_coords.get(axis_a)
        axis_end = state.base_coords.get(axis_b)
        if axis_start is None or axis_end is None:
            return
        next_total_angle = state.total_angle + angle_delta

        def update_axis_preview() -> None:
            state.total_angle = next_total_angle
            rotated_coords = axis_rotated_coords(
                state.atom_ids,
                state.base_coords,
                axis_start,
                axis_end,
                next_total_angle,
                rotate_point=self.rotate_point_around_axis,
            )
            self.apply_projected_atom_positions(state.atom_ids, rotated_coords)
            self.refresh_atom_geometry(state.atom_ids)

        run_rotation_preview_update(
            self,
            set(state.atom_ids),
            update_axis_preview,
        )

    def end_selection_3d_rotation(self) -> None:
        preview = self._rotation_preview_authority
        if preview is None:
            return
        state = self.rotation
        pushed = False
        try:
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
            if command is not None:
                if self.history.push(command) is False:
                    raise RuntimeError(
                        "Selection rotation history push did not commit its command"
                    )
                pushed = True
            if selection_ids is not None:
                self.restore_selection_from_ids(*selection_ids)
            self.emit_selection_info()
            state.clear_session()
            preview.release()
            self._rotation_preview_authority = None
        except BaseException as original_error:
            # Fail closed: close the session and surface the error. Before the
            # push commits, revert the document to the gesture start (the
            # history service owns its own stack consistency for a failed
            # push). After a successful push the stack top describes the
            # rotated document, so the document must stay rotated.
            self._rotation_preview_authority = None
            try:
                if pushed:
                    preview.release()
                else:
                    preview.restore(original_error)
                state.clear_session()
            except BaseException as cleanup_error:
                _add_rotation_finalization_rollback_note(
                    original_error,
                    cleanup_error,
                )
            raise
