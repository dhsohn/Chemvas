from __future__ import annotations

from functools import partial

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
)
from chemvas.core.model_commands import (
    SetAtomPositionsCommand,
    SetRingPolygonsCommand,
    UpdateBondLengthCommand,
)
from chemvas.domain.transactions import (
    add_recovery_error_note,
    restore_snapshot,
    run_rollback_step,
)
from chemvas.ui.annotations.state import mark_state_dict_for, scene_item_history_state
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_model_access import (
    atom_for_id,
    rescale_model_for,
)
from chemvas.ui.canvas.canvas_scene_items_state import (
    require_scene_record_id,
    ring_items_for,
)
from chemvas.ui.history.history_atom_position_restore import (
    set_atom_positions_for_history,
)
from chemvas.ui.history.history_commands import (
    SetBondLengthGeometryCommand,
    UpdateSceneItemCommand,
)
from chemvas.ui.history.history_operations import CanvasHistoryOperations
from chemvas.ui.molecule.bond_length_graphics_refresh import (
    refresh_bond_length_graphics_for,
)
from chemvas.ui.transactions.document import DocumentSavepoint


class CanvasGeometryController:
    """Editor commands for changes to molecular geometry."""

    def __init__(
        self, canvas, *, hit_testing_service=None, history_service=None
    ) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.history = history_service

    def set_bond_length(self, length_px: float) -> None:
        old_length = self.canvas.renderer.style.bond_length_px
        if old_length <= 0 or not bool(self.canvas.model.atoms):
            self.canvas.renderer.set_bond_length(length_px)
            return
        scale = length_px / old_length
        if scale == 1.0:
            self.canvas.renderer.set_bond_length(length_px)
            return
        if self.hit_testing_service is None:
            raise RuntimeError(
                "CanvasGeometryController.set_bond_length requires hit_testing_service"
            )
        if self.history is None:
            raise AttributeError(
                "CanvasGeometryController requires an injected history_service"
            )

        before_positions = {
            atom_id: (atom.x, atom.y)
            for atom_id, atom in self.canvas.model.atoms.items()
        }
        before_coords_3d = self._atom_coords_3d_for_positions(before_positions)
        rotation_state = self.canvas.runtime_state.rotation_state
        before_projection_center_3d = rotation_state.projection_center_3d
        before_projection_anchor_2d = rotation_state.projection_anchor_2d
        current_ring_items = list(ring_items_for(self.canvas))
        before_ring_polygons = [
            [(point.x(), point.y()) for point in ring_item.polygon()]
            for ring_item in current_ring_items
        ]
        renderer = self.canvas.renderer
        before_renderer_style = renderer.style
        before_marks = []
        for _atom_id, marks in mark_registry_for(self.canvas).items():
            for item in marks:
                state = scene_item_history_state(
                    item, mark_state_dict_for(self.canvas, item)
                )
                before_marks.append((item, state))
        transaction = DocumentSavepoint.capture(
            self.canvas, history_service=self.history
        )
        try:
            self.canvas.renderer.set_bond_length(length_px)
            center_x, center_y = self._model_center()
            rescale_model_for(self.canvas, scale)
            self._rescale_perspective_state(scale, center_x, center_y)
            for item, state in before_marks:
                data = dict(item.data(1))
                atom_x, atom_y = before_positions[data["atom_id"]]
                data["dx"] = (
                    state["dx"] if state["dx"] is not None else state["x"] - atom_x
                ) * scale
                data["dy"] = (
                    state["dy"] if state["dy"] is not None else state["y"] - atom_y
                ) * scale
                item.setData(1, data)
            self.hit_testing_service.mark_spatial_index_dirty()
            refresh_bond_length_graphics_for(self.canvas)
            after_positions = {
                atom_id: (atom.x, atom.y)
                for atom_id, atom in self.canvas.model.atoms.items()
            }
            after_coords_3d = self._atom_coords_3d_for_positions(after_positions)
            after_projection_center_3d = rotation_state.projection_center_3d
            after_projection_anchor_2d = rotation_state.projection_anchor_2d
            after_ring_polygons = [
                [(point.x(), point.y()) for point in ring_item.polygon()]
                for ring_item in current_ring_items
            ]
            atom_command = SetAtomPositionsCommand(
                before_positions=before_positions,
                after_positions=after_positions,
                before_coords_3d=before_coords_3d or None,
                after_coords_3d=after_coords_3d or None,
                restore_projection_state=bool(
                    before_coords_3d
                    or after_coords_3d
                    or before_projection_center_3d is not None
                    or after_projection_center_3d is not None
                    or before_projection_anchor_2d is not None
                    or after_projection_anchor_2d is not None
                ),
                before_projection_center_3d=before_projection_center_3d,
                after_projection_center_3d=after_projection_center_3d,
                before_projection_anchor_2d=before_projection_anchor_2d,
                after_projection_anchor_2d=after_projection_anchor_2d,
            )
            mark_commands = []
            for item, before_state in before_marks:
                after_state = scene_item_history_state(
                    item, mark_state_dict_for(self.canvas, item)
                )
                mark_commands.append(
                    UpdateSceneItemCommand(
                        require_scene_record_id(item), before_state, after_state
                    )
                )
            commands: list[HistoryCommand] = [
                SetBondLengthGeometryCommand(
                    atom_commands=[atom_command],
                    item_commands=mark_commands,
                    length_command=UpdateBondLengthCommand(
                        before_length=old_length, after_length=length_px
                    ),
                )
            ]
            if current_ring_items:
                commands.append(
                    SetRingPolygonsCommand(
                        ring_ids=[
                            require_scene_record_id(item) for item in current_ring_items
                        ],
                        before_polygons=before_ring_polygons,
                        after_polygons=after_ring_polygons,
                    )
                )
            if (
                self.history.push(CompositeCommand(commands)) is False
                and self.history.is_enabled()
            ):
                raise RuntimeError("Bond-length change did not commit to history")
            transaction.release()
        except Exception as exc:
            self._restore_failed_bond_length_change(
                old_length=old_length,
                renderer=renderer,
                renderer_style=before_renderer_style,
                transaction=transaction,
                original_error=exc,
                positions=before_positions,
                coords_3d=before_coords_3d,
                projection_center_3d=before_projection_center_3d,
                projection_anchor_2d=before_projection_anchor_2d,
                ring_items=current_ring_items,
                ring_polygons=before_ring_polygons,
            )
            raise

    def _restore_failed_bond_length_change(
        self,
        *,
        old_length: float,
        renderer,
        renderer_style,
        transaction,
        original_error: BaseException,
        positions: dict[int, tuple[float, float]],
        coords_3d: dict[int, tuple[float, float, float]],
        projection_center_3d: tuple[float, float, float] | None,
        projection_anchor_2d: tuple[float, float] | None,
        ring_items: list,
        ring_polygons: list[list[tuple[float, float]]],
    ) -> None:
        # Each compensation is independent so one persistently broken graphics
        # item cannot prevent the model, projection, and remaining items from
        # being restored as far as possible.
        run_rollback_step(
            original_error,
            "restoring projection state",
            lambda: CanvasHistoryOperations(
                self.canvas
            ).restore_projection_state_for_history(
                projection_center_3d, projection_anchor_2d
            ),
        )
        run_rollback_step(
            original_error,
            "restoring atom positions",
            lambda: set_atom_positions_for_history(
                self.canvas, positions, coords_3d=coords_3d or None
            ),
        )
        run_rollback_step(
            original_error,
            "restoring ring polygons",
            lambda: CanvasHistoryOperations(self.canvas).set_ring_polygons_for_history(
                [require_scene_record_id(item) for item in ring_items], ring_polygons
            ),
        )
        run_rollback_step(
            original_error,
            "restoring the bond length",
            lambda: CanvasHistoryOperations(
                self.canvas
            ).restore_bond_length_for_history(old_length),
        )
        # Renderer.set_bond_length replaces the immutable style object. Restore
        # the exact original object so external style references remain valid.
        run_rollback_step(
            original_error,
            "restoring the renderer style",
            lambda: setattr(renderer, "style", renderer_style),
        )

        # The transaction snapshot preserves model containers, but Atom objects
        # are mutable leaves. Restore their coordinates directly even when a
        # persistently broken graphics callback interrupted the UI compensation.
        def restore_raw_atom_position(atom_id: int, x: float, y: float) -> None:
            atom = atom_for_id(self.canvas, atom_id)
            if atom is None:
                return
            atom.x = x
            atom.y = y

        for atom_id, (x, y) in positions.items():
            run_rollback_step(
                original_error,
                f"restoring raw atom {atom_id} coordinates",
                partial(restore_raw_atom_position, atom_id, x, y),
            )
        run_rollback_step(
            original_error,
            "reapplying projection state",
            lambda: CanvasHistoryOperations(
                self.canvas
            ).restore_projection_state_for_history(
                projection_center_3d, projection_anchor_2d
            ),
        )
        run_rollback_step(
            original_error,
            "reapplying ring polygons",
            lambda: CanvasHistoryOperations(self.canvas).set_ring_polygons_for_history(
                [require_scene_record_id(item) for item in ring_items], ring_polygons
            ),
        )
        run_rollback_step(
            original_error,
            "refreshing bond-length graphics",
            lambda: refresh_bond_length_graphics_for(self.canvas),
        )
        # The port lookup belongs inside the protected callable: passing
        # ``self.hit_testing_service.mark_spatial_index_dirty`` directly would
        # resolve the attribute before the rollback runner's ``try``, so a
        # failing lookup would escape and mask the primary error.
        run_rollback_step(
            original_error,
            "invalidating the spatial index",
            lambda: self.hit_testing_service.mark_spatial_index_dirty(),
        )
        # Apply the exact container/scene/history snapshot last. In particular,
        # its canonical bond refresh now observes the directly restored Atom
        # coordinates and original renderer style; a persistent failure in the
        # higher-level refresh callback cannot re-corrupt the raw state after
        # this final absolute restore pass.
        restore_result = restore_snapshot(
            lambda: transaction.restore(),
            description="bond-length transaction",
        )
        for rollback_error in restore_result.errors:
            add_recovery_error_note(
                original_error,
                rollback_error,
                phase="restoring the bond-length transaction",
            )

    def _atom_coords_3d_for_positions(
        self, positions: dict[int, tuple[float, float]]
    ) -> dict[int, tuple[float, float, float]]:
        stored_coords = self.canvas.runtime_state.atom_coords_3d_state.atom_coords_3d
        return {
            atom_id: stored_coords[atom_id]
            for atom_id in positions
            if atom_id in stored_coords
        }

    def _model_center(self) -> tuple[float, float]:
        atoms = self.canvas.model.atoms
        center_x = sum(atom.x for atom in atoms.values()) / len(atoms)
        center_y = sum(atom.y for atom in atoms.values()) / len(atoms)
        return center_x, center_y

    @staticmethod
    def _scaled_xy(
        x: float, y: float, scale: float, center_x: float, center_y: float
    ) -> tuple[float, float]:
        return center_x + (x - center_x) * scale, center_y + (y - center_y) * scale

    def _rescale_perspective_state(
        self, scale: float, center_x: float, center_y: float
    ) -> None:
        rotation_state = self.canvas.runtime_state.rotation_state
        projection_center = rotation_state.projection_center_3d
        z_center = projection_center[2] if projection_center is not None else 0.0
        atom_ids = set(self.canvas.model.atoms)
        for atom_id, (x, y, z) in list(
            self.canvas.runtime_state.atom_coords_3d_state.atom_coords_3d.items()
        ):
            if atom_id not in atom_ids:
                continue
            scaled_x, scaled_y = self._scaled_xy(x, y, scale, center_x, center_y)
            self.canvas.runtime_state.atom_coords_3d_state.atom_coords_3d[atom_id] = (
                scaled_x,
                scaled_y,
                z_center + (z - z_center) * scale,
            )
        if projection_center is not None:
            x, y, z = projection_center
            scaled_x, scaled_y = self._scaled_xy(x, y, scale, center_x, center_y)
            rotation_state.projection_center_3d = (scaled_x, scaled_y, z)
        if rotation_state.projection_anchor_2d is not None:
            x, y = rotation_state.projection_anchor_2d
            rotation_state.projection_anchor_2d = self._scaled_xy(
                x, y, scale, center_x, center_y
            )


__all__ = ["CanvasGeometryController"]
