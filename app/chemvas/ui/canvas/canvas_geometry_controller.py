from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
)
from chemvas.core.model_commands import (
    SetAtomPositionsCommand,
    SetRingPolygonsCommand,
    UpdateBondLengthCommand,
)
from chemvas.ui.annotations.state import mark_state_dict_for, scene_item_history_state
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from chemvas.ui.history.history_commands import (
    SetBondLengthGeometryCommand,
    UpdateSceneItemCommand,
)
from chemvas.ui.molecule.bond_length_graphics_refresh import (
    refresh_bond_length_graphics_for,
)
from chemvas.ui.transactions.document import document_transaction


class CanvasGeometryController:
    """Editor commands for changes to molecular geometry."""

    def __init__(
        self, canvas, *, hit_testing_service=None, history_service=None
    ) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.history = history_service

    def set_bond_length(self, length_px: float) -> None:
        """Change the drawing's bond length as one undoable document edit.

        Atoms, ring fills, stored 3D coordinates and atom-bound marks scale
        with it about the atoms' centre; free annotations keep their places.
        """
        old_length = self.canvas.renderer.style.bond_length_px
        if length_px == old_length:
            return
        if self.history is None:
            raise AttributeError(
                "CanvasGeometryController requires an injected history_service"
            )
        if self.hit_testing_service is None:
            raise RuntimeError(
                "CanvasGeometryController.set_bond_length requires hit_testing_service"
            )
        scale = length_px / old_length
        before_positions = {
            atom_id: (atom.x, atom.y)
            for atom_id, atom in self.canvas.model.atoms.items()
        }
        before_coords_3d = self._atom_coords_3d_for_positions(before_positions)
        rotation_state = self.canvas.runtime_state.rotation_state
        before_projection_center_3d = rotation_state.projection_center_3d
        before_projection_anchor_2d = rotation_state.projection_anchor_2d
        current_ring_items = list(self.canvas.runtime_state.ring_items())
        before_ring_polygons = [
            [(point.x(), point.y()) for point in ring_item.polygon()]
            for ring_item in current_ring_items
        ]
        before_marks = []
        for _atom_id, marks in mark_registry_for(self.canvas).items():
            for item in marks:
                state = scene_item_history_state(
                    item, mark_state_dict_for(self.canvas, item)
                )
                before_marks.append((item, state))
        with document_transaction(self.canvas, history_service=self.history):
            self.canvas.renderer.set_bond_length(length_px)
            # Without atoms there is no centre to scale about; only the
            # setting changes.
            if before_positions:
                center_x, center_y = self.canvas.model.center()
                self.canvas.model.scale_about(center_x, center_y, scale)
                self._rescale_ring_polygons(scale, center_x, center_y)
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
            self.history.push(CompositeCommand(commands))

    def _atom_coords_3d_for_positions(
        self, positions: dict[int, tuple[float, float]]
    ) -> dict[int, tuple[float, float, float]]:
        stored_coords = self.canvas.runtime_state.atom_coords_3d_state.atom_coords_3d
        return {
            atom_id: stored_coords[atom_id]
            for atom_id in positions
            if atom_id in stored_coords
        }

    def _rescale_ring_polygons(
        self, scale: float, center_x: float, center_y: float
    ) -> None:
        for ring_item in self.canvas.runtime_state.ring_items():
            scaled = QPolygonF()
            for point in ring_item.polygon():
                scaled.append(
                    QPointF(
                        center_x + (point.x() - center_x) * scale,
                        center_y + (point.y() - center_y) * scale,
                    )
                )
            ring_item.setPolygon(scaled)

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
