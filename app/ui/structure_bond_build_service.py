from __future__ import annotations

from PyQt6.QtCore import QPointF

from ui.bond_style_logic import style_for_existing_bond_overlay
from ui.canvas_model_access import bond_for_id
from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.history_recording_access import record_bond_update_for
from ui.renderer_style_access import bond_length_px_for
from ui.scene_item_state import bond_state_dict
from ui.structure_build_committer import StructureBuildCommitter


class StructureBondBuildService:
    def __init__(
        self,
        canvas,
        committer: StructureBuildCommitter,
        *,
        hit_testing_service,
        move_controller,
        graph_service,
    ) -> None:
        self.canvas = canvas
        self.committer = committer
        self.hit_testing_service = hit_testing_service
        self.move_controller = move_controller
        self.graph_service = graph_service

    def add_bond_between_points(
        self,
        start: QPointF,
        end: QPointF,
        style: str,
        order: int,
    ) -> tuple[int, int] | None:
        snap_tol = bond_length_px_for(self.canvas) * 0.1
        if start == end or (start - end).manhattanLength() <= snap_tol:
            return None
        start_id = self.hit_testing_service.find_atom_near(start.x(), start.y(), snap_tol)
        end_id = self.hit_testing_service.find_atom_near(end.x(), end.y(), snap_tol)
        if start_id is not None and start_id == end_id:
            return None
        snapshot = self.committer.begin_recorded_change()
        before_smiles_input = snapshot.before_smiles_input
        if start_id is None:
            start_id = self.committer.add_atom("C", start.x(), start.y())
        if end_id is None:
            end_id = self.committer.add_atom("C", end.x(), end.y())
        existing_bond_id = self.graph_service.bond_id_between(start_id, end_id)
        if existing_bond_id is not None:
            return self._update_existing_bond(
                existing_bond_id,
                style,
                order,
                before_smiles_input,
                start_id,
                end_id,
            )
        return self._add_new_bond(snapshot, start_id, end_id, style, order)

    def _update_existing_bond(
        self,
        bond_id: int,
        style: str,
        order: int,
        before_smiles_input: str | None,
        start_id: int,
        end_id: int,
    ) -> tuple[int, int] | None:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return None
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
        after_state = bond_state_dict(bond)
        record_bond_update_for(
            self.canvas,
            bond_id,
            before_state,
            after_state,
            before_smiles_input,
            last_smiles_input_for(self.canvas),
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
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return None
        bond.style = style
        self.committer.add_bond_graphics(bond_id)
        self.move_controller.redraw_connected_bonds(start_id, skip_bond_id=bond_id)
        self.move_controller.redraw_connected_bonds(end_id, skip_bond_id=bond_id)
        self.committer.record_additions(snapshot)
        return start_id, end_id


__all__ = ["StructureBondBuildService"]
