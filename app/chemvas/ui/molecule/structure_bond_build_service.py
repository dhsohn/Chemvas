from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chemvas.features.rendering import (
    BOLD_BOND_STYLES,
    DOTTED_DOUBLE_STYLE_DEFAULT,
    DOTTED_DOUBLE_STYLE_OUTER,
    DOUBLE_STYLE_CENTER,
    DOUBLE_STYLE_OUTER,
    style_for_existing_bond_overlay,
)
from chemvas.ui.canvas.canvas_window_access import notify_error_for

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF

    from chemvas.ui.molecule.structure_build_committer import StructureBuildCommitter


class StructureBondBuildService:
    def __init__(
        self,
        canvas,
        committer: StructureBuildCommitter,
        *,
        hit_testing_service,
        move_controller,
        graph_service,
        connection_allowed=None,
    ) -> None:
        self.canvas = canvas
        self.committer = committer
        self.hit_testing_service = hit_testing_service
        self.move_controller = move_controller
        self.graph_service = graph_service
        self.connection_allowed = connection_allowed

    def add_bond_between_points(
        self,
        start: QPointF,
        end: QPointF,
        style: str,
        order: int,
        *,
        record: bool = True,
    ) -> tuple[int, int] | None:
        """Build through the same rules; an unrecorded caller owns its transaction."""
        snap_tol = self.canvas.renderer.style.bond_length_px * 0.1
        if (
            start == end
            or math.hypot(start.x() - end.x(), start.y() - end.y()) <= snap_tol
        ):
            return None
        start_id = self.hit_testing_service.find_atom_near(
            start.x(), start.y(), snap_tol
        )
        end_id = self.hit_testing_service.find_atom_near(end.x(), end.y(), snap_tol)
        if start_id is not None and start_id == end_id:
            return None
        existing_bond_id = None
        if start_id is not None and end_id is not None:
            # bond_id_between only ever returns ids whose bond slot is live
            # (tombstones fail its atom-match check), so no stale-id guard is
            # needed here; a missing bond simply means "draw a new one".
            existing_bond_id = self.graph_service.bond_id_between(start_id, end_id)
        existing_bond = self.canvas.model.bond_for_id(existing_bond_id)
        if (
            existing_bond is not None
            and existing_bond.style == "double_either"
            and style
            in {
                *BOLD_BOND_STYLES,
                DOTTED_DOUBLE_STYLE_DEFAULT,
                DOTTED_DOUBLE_STYLE_OUTER,
                "dotted",
                DOUBLE_STYLE_CENTER,
                DOUBLE_STYLE_OUTER,
            }
        ):
            notify_error_for(
                self.canvas,
                "This appearance change would erase unknown double-bond stereo. "
                "Choose Double (2) first to clear it explicitly.",
            )
            return None
        anchors = {atom_id for atom_id in (start_id, end_id) if atom_id is not None}
        if existing_bond_id is None and anchors:
            if self.connection_allowed is None:
                from chemvas.ui.scene.scene_group_operations import (
                    group_connection_allowed_for,
                )

                allowed = group_connection_allowed_for(self.canvas, anchors)
            else:
                allowed = self.connection_allowed(anchors)
            if not allowed:
                return None
        snapshot = self.committer.begin_recorded_change() if record else None
        try:
            if start_id is None:
                start_id = self.committer.add_atom("C", start.x(), start.y())
            if end_id is None:
                end_id = self.committer.add_atom("C", end.x(), end.y())
            if existing_bond_id is None:
                existing_bond_id = self.graph_service.bond_id_between(start_id, end_id)
            if existing_bond_id is not None:
                result = self._update_existing_bond(
                    existing_bond_id,
                    style,
                    order,
                    start_id,
                    end_id,
                    record=record,
                )
                if snapshot is not None:
                    if result is None:
                        self.committer.abort_recorded_change(snapshot)
                    else:
                        self.committer.release_recorded_change(snapshot)
                return result
            return self._add_new_bond(snapshot, start_id, end_id, style, order)
        except Exception as error:
            if snapshot is not None:
                self.committer.abort_recorded_change(snapshot, original_error=error)
            raise

    def _update_existing_bond(
        self,
        bond_id: int,
        style: str,
        order: int,
        start_id: int,
        end_id: int,
        *,
        record: bool = True,
    ) -> tuple[int, int] | None:
        bond = self.canvas.model.bond_for_id(bond_id)
        if bond is None:
            return None
        if record:
            from chemvas.ui.annotations.state import bond_state_dict

            before_state = bond_state_dict(bond)
        next_style, next_order = style_for_existing_bond_overlay(
            bond.style,
            bond.order,
            style,
            order,
        )
        bond.style = next_style
        bond.order = next_order
        self.move_controller.redraw_bond(bond_id)
        self.move_controller.redraw_connected_bonds(bond.a, skip_bond_id=bond_id)
        self.move_controller.redraw_connected_bonds(bond.b, skip_bond_id=bond_id)
        if record:
            after_state = bond_state_dict(bond)
            self.canvas.services.canvas_history_recording_service.record_bond_update(
                bond_id,
                before_state,
                after_state,
            )
        return start_id, end_id

    def _add_new_bond(
        self,
        snapshot,
        start_id: int,
        end_id: int,
        style: str,
        order: int,
    ) -> tuple[int, int] | None:
        bond_id = self.committer.add_bond(start_id, end_id, order)
        bond = self.canvas.model.bond_for_id(bond_id)
        if bond is None:
            if snapshot is not None:
                self.committer.abort_recorded_change(snapshot)
            return None
        bond.style = style
        self.committer.add_bond_graphics(bond_id)
        self.move_controller.redraw_connected_bonds(start_id, skip_bond_id=bond_id)
        self.move_controller.redraw_connected_bonds(end_id, skip_bond_id=bond_id)
        if snapshot is not None:
            self.committer.record_additions(snapshot)
        return start_id, end_id


__all__ = ["StructureBondBuildService"]
