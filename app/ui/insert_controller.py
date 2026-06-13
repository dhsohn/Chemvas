from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.canvas_insert_state import CanvasInsertState, insert_state_for
from ui.insert_commit_service import InsertCommitService
from ui.insert_mode_logic import InsertSessionState
from ui.insert_smiles_service import InsertSmilesService
from ui.insert_template_service import InsertTemplateService
from ui.sheet_setup_access import scene_pos_in_sheet_for
from ui.template_insert_logic import (
    TemplateInsertRequest,
    TemplatePointResolvers,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class InsertController:
    def __init__(
        self,
        canvas: CanvasView,
        insert_state: CanvasInsertState | None = None,
        *,
        hit_testing_service,
        insert_commit_service: InsertCommitService | None = None,
        graph_service,
        structure_build_service=None,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state if insert_state is not None else insert_state_for(canvas)
        self.hit_testing_service = hit_testing_service
        self.history = history_service
        self.graph_service = graph_service
        self.insert_commit_service = insert_commit_service or InsertCommitService(
            canvas,
            bond_exists=self.graph_service.bond_exists,
        )
        self.structure_build_service = structure_build_service
        self.template_service = InsertTemplateService(
            canvas,
            insert_state=self.insert_state,
            hit_testing_service=self.hit_testing_service,
            insert_commit_service=self.insert_commit_service,
            session_state=self.insert_session_state,
            apply_session_state=self.apply_insert_session_state,
            cancel_smiles_insert=lambda: self.cancel_smiles_insert(),
            render_template_preview=lambda pos: self.render_template_preview(pos),
        )
        self.template_geometry = self.template_service.template_geometry
        self.smiles_service = InsertSmilesService(
            canvas,
            insert_state=self.insert_state,
            insert_commit_service=self.insert_commit_service,
            graph_service=self.graph_service,
            structure_build_service=self.structure_build_service,
            history_service=self.history,
            session_state=self.insert_session_state,
            apply_session_state=self.apply_insert_session_state,
            cancel_template_insert=lambda: self.cancel_template_insert(),
            cancel_smiles_insert=lambda: self.cancel_smiles_insert(),
            clear_smiles_preview=lambda: self.clear_smiles_preview(),
            render_smiles_preview=lambda pos: self.render_smiles_preview(pos),
        )

    def insert_session_state(self) -> InsertSessionState:
        smiles_center = None
        if self.insert_state.smiles_preview_center is not None:
            smiles_center = (
                self.insert_state.smiles_preview_center.x(),
                self.insert_state.smiles_preview_center.y(),
            )
        return InsertSessionState(
            template_active=self.insert_state.template_active,
            template_ring_size=self.insert_state.template_ring_size,
            template_ring_style=self.insert_state.template_ring_style,
            smiles_active=self.insert_state.smiles_active,
            smiles_text=self.insert_state.smiles_preview_smiles,
            smiles_center=smiles_center,
        )

    def apply_insert_session_state(self, state: InsertSessionState) -> None:
        template_was_active = self.insert_state.template_active
        smiles_was_active = self.insert_state.smiles_active
        self.insert_state.template_active = state.template_active
        self.insert_state.template_ring_size = state.template_ring_size
        self.insert_state.template_ring_style = state.template_ring_style
        self.insert_state.smiles_active = state.smiles_active
        self.insert_state.smiles_preview_smiles = state.smiles_text
        self.insert_state.smiles_preview_center = None if state.smiles_center is None else QPointF(*state.smiles_center)
        if template_was_active and not state.template_active:
            self.clear_template_preview()
        if smiles_was_active and not state.smiles_active:
            self.clear_smiles_preview()

    def begin_ring_template_insert(self, ring_size: int, style: str = "regular") -> None:
        self.template_service.begin_ring_template_insert(ring_size, style)

    def load_smiles(self, smiles: str) -> None:
        self.smiles_service.load_smiles(smiles)

    def begin_smiles_insert(self, smiles: str) -> None:
        self.smiles_service.begin_smiles_insert(smiles)

    def cancel_smiles_insert(self) -> None:
        self.smiles_service.cancel_smiles_insert()

    def commit_smiles_insert(self, pos: QPointF) -> None:
        if not scene_pos_in_sheet_for(self.canvas, pos):
            self.clear_smiles_preview()
            return
        self.smiles_service.commit_smiles_insert(pos)

    def clear_smiles_preview(self) -> None:
        self.smiles_service.clear_smiles_preview()

    def smiles_preview_snapshot(self):
        return self.smiles_service.smiles_preview_snapshot()

    def render_smiles_preview(self, pos: QPointF) -> None:
        if not scene_pos_in_sheet_for(self.canvas, pos):
            self.clear_smiles_preview()
            return
        self.smiles_service.render_smiles_preview(pos)

    def cancel_template_insert(self) -> None:
        self.template_service.cancel_template_insert()

    def template_insert_request(self, pos: QPointF) -> TemplateInsertRequest | None:
        return self.template_service.template_insert_request(pos)

    def template_point_resolvers(self) -> TemplatePointResolvers:
        return self.template_service.template_point_resolvers()

    def resolve_ring_points_for_template(
        self,
        center: tuple[float, float],
        n: int,
        radius: float | None,
    ) -> list[tuple[float, float]]:
        return self.template_service.resolve_ring_points_for_template(center, n, radius)

    def resolve_regular_ring_points_for_template_bond(
        self,
        n: int,
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self.template_service.resolve_regular_ring_points_for_template_bond(n, bond_id, center)

    def resolve_chair_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self.template_service.resolve_chair_points_for_template(center)

    def resolve_boat_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self.template_service.resolve_boat_points_for_template(center)

    def resolve_template_points_for_template_bond(
        self,
        points_local: list[tuple[float, float]],
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self.template_service.resolve_template_points_for_template_bond(points_local, bond_id, center)

    def bond_merge_seed(self, bond_id: int | None) -> list[tuple[int, float, float]]:
        return self.insert_commit_service.bond_merge_seed(bond_id)

    def commit_template_insert(self, pos: QPointF) -> None:
        if not scene_pos_in_sheet_for(self.canvas, pos):
            self.clear_template_preview()
            return
        self.template_service.commit_template_request(pos, self.template_insert_request(pos))

    def clear_template_preview(self) -> None:
        self.template_service.clear_template_preview()

    def render_template_preview(self, pos: QPointF) -> None:
        if not scene_pos_in_sheet_for(self.canvas, pos):
            self.clear_template_preview()
            return
        self.template_service.render_template_request_preview(
            pos,
            self.template_insert_request(pos),
            clear_template_preview=lambda: self.clear_template_preview(),
        )


__all__ = ["InsertController"]
