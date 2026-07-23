"""Per-gesture rollback guard for the selection-rotation preview.

The preview mutates the document in place on every pointer frame (atom
positions and the persisted 3D coordinates), so the guard keeps the two
failure-path contracts: a failing frame reverts to the last successful
frame, and a failing finalization reverts to the gesture start. The
scene-rect guard pins Qt's automatic scene-rect mode for the gesture.
Affected ring items are discovered once per gesture so frame cost scales
with the selection, not the document.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6 import sip

from chemvas.ui.atom_coords_access import (
    atom_coords_3d_for,
    set_atom_coords_3d_for_id,
)
from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.selection_rotation_access import sync_atom_scene_items_for
from chemvas.ui.transactions.scene_rect import SceneRectSnapshot

if TYPE_CHECKING:
    from chemvas.ui.selection_rotation_controller import SelectionRotationController

Coords3D = tuple[float, float, float]


def _add_rotation_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
) -> None:
    try:
        original_error.add_note(
            f"Rotation preview rollback also failed: {rollback_error!r}"
        )
    except BaseException:
        return


def _ring_item_is_deleted(item: object) -> bool:
    try:
        return sip.isdeleted(item)  # type: ignore[arg-type]
    except TypeError:
        return False


def _affected_ring_items(canvas, atom_ids: set[int]) -> list[object]:
    rings = ring_items_for(canvas)
    affected: list[object] = []
    for ring in rings:
        if _ring_item_is_deleted(ring):
            continue
        ring_atom_ids = ring.data(2)
        if isinstance(ring_atom_ids, list) and not atom_ids.isdisjoint(ring_atom_ids):
            affected.append(ring)
    return affected


@dataclass(slots=True)
class _RotationPreviewAuthority:
    """Gesture-scoped rollback guard published by the rotation controller."""

    controller: SelectionRotationController
    atom_ids: frozenset[int]
    affected_ring_items: tuple[object, ...]
    scene_rect_snapshot: SceneRectSnapshot | None

    def run_update(self, update) -> None:
        """Run one preview frame; on failure revert to the previous frame."""

        canvas = self.controller.canvas
        state = self.controller.rotation
        coords_3d = atom_coords_3d_for(canvas)
        previous_scalars = (state.free_angle_x, state.free_angle_y, state.total_angle)
        previous: dict[int, tuple[tuple[float, float] | None, Coords3D | None]] = {}
        for atom_id in self.atom_ids:
            atom = atom_for_id(canvas, atom_id)
            previous[atom_id] = (
                (atom.x, atom.y) if atom is not None else None,
                coords_3d.get(atom_id),
            )
        try:
            update()
        except BaseException as original_error:
            try:
                state.free_angle_x, state.free_angle_y, state.total_angle = (
                    previous_scalars
                )
                self._reapply_coords(previous)
            except BaseException as rollback_error:
                _add_rotation_rollback_note(original_error, rollback_error)
            raise

    def _reapply_coords(
        self,
        saved: dict[int, tuple[tuple[float, float] | None, Coords3D | None]],
    ) -> None:
        canvas = self.controller.canvas
        for atom_id, (position, coords) in saved.items():
            if position is not None:
                atom = atom_for_id(canvas, atom_id)
                if atom is not None:
                    atom.x, atom.y = position
            if coords is not None:
                set_atom_coords_3d_for_id(canvas, atom_id, coords)
        sync_atom_scene_items_for(canvas, set(self.atom_ids))
        self.controller.refresh_atom_geometry(set(self.atom_ids))

    def restore(self, original_error: BaseException | None = None) -> None:
        """Revert the document to the gesture-start coordinates."""

        canvas = self.controller.canvas
        state = self.controller.rotation
        try:
            for atom_id, position in state.start_positions.items():
                atom = atom_for_id(canvas, atom_id)
                if atom is not None:
                    atom.x, atom.y = position
            for atom_id, coords in state.start_coords_3d.items():
                set_atom_coords_3d_for_id(canvas, atom_id, coords)
            state.projection_center_3d = state.start_projection_center_3d
            state.projection_anchor_2d = state.start_projection_anchor_2d
            restored_ids = set(state.start_positions) | set(state.start_coords_3d)
            sync_atom_scene_items_for(canvas, restored_ids)
            refresh_ids = set(state.atom_ids) or set(self.atom_ids)
            if refresh_ids:
                self.controller.refresh_atom_geometry(refresh_ids)
        finally:
            if self.scene_rect_snapshot is not None:
                self.scene_rect_snapshot.restore()
                self.scene_rect_snapshot = None

    def release(self) -> None:
        if self.scene_rect_snapshot is not None:
            self.scene_rect_snapshot.release()
            self.scene_rect_snapshot = None


def capture_rotation_preview_authority(
    controller: SelectionRotationController,
    atom_ids: set[int],
) -> _RotationPreviewAuthority:
    canvas = controller.canvas
    return _RotationPreviewAuthority(
        controller=controller,
        atom_ids=frozenset(atom_ids),
        affected_ring_items=tuple(_affected_ring_items(canvas, set(atom_ids))),
        scene_rect_snapshot=SceneRectSnapshot.capture(canvas.scene()),
    )


def run_rotation_preview_update(
    controller: SelectionRotationController,
    atom_ids: set[int],
    update,
) -> None:
    preview = controller._rotation_preview_authority
    if not isinstance(preview, _RotationPreviewAuthority) or preview.atom_ids != (
        frozenset(atom_ids)
    ):
        raise RuntimeError(
            "Selection rotation preview update requires a matching active authority"
        )
    preview.run_update(update)


__all__ = [
    "capture_rotation_preview_authority",
    "run_rotation_preview_update",
]
