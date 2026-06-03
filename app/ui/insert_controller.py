from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QMessageBox

from ui.canvas_history_service import history_service_for
from ui.canvas_insert_state import CanvasInsertState, insert_state_for
from ui.insert_mode_logic import (
    InsertSessionState,
    begin_smiles_insert as begin_smiles_insert_state,
    begin_template_insert as begin_template_insert_state,
    build_template_insert_request,
    cancel_smiles_insert as cancel_smiles_insert_state,
    cancel_template_insert as cancel_template_insert_state,
)
from ui.insert_commit_service import InsertCommitService
from ui.insert_smiles_transaction import SmilesLoadTransactionBuilder
from ui.preview_scene_renderer import (
    apply_smiles_preview_geometry as apply_smiles_preview_geometry_helper,
    apply_template_preview_geometry as apply_template_preview_geometry_helper,
    clear_smiles_preview as clear_smiles_preview_helper,
    clear_template_preview as clear_template_preview_helper,
    smiles_preview_snapshot as smiles_preview_snapshot_helper,
)
from ui.smiles_insert_logic import SmilesPreviewResolvers, plan_smiles_commit, plan_smiles_preview_update, smiles_preview_center
from ui.template_insert_logic import TemplateInsertRequest, TemplatePointResolvers, plan_template_commit, plan_template_preview, resolve_template_insert
from ui.template_preview_logic import plan_template_preview_update

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class InsertController:
    def __init__(self, canvas: CanvasView, insert_state: CanvasInsertState | None = None) -> None:
        self.canvas = canvas
        self.insert_state = insert_state if insert_state is not None else insert_state_for(canvas)
        self.history = history_service_for(canvas)
        self._insert_commit_service = InsertCommitService(canvas)
        self._smiles_load_transaction_builder = SmilesLoadTransactionBuilder(canvas)

    def _insert_session_state(self) -> InsertSessionState:
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

    def insert_session_state(self) -> InsertSessionState:
        return self._insert_session_state()

    def _apply_insert_session_state(self, state: InsertSessionState) -> None:
        template_was_active = self.insert_state.template_active
        smiles_was_active = self.insert_state.smiles_active
        self.insert_state.template_active = state.template_active
        self.insert_state.template_ring_size = state.template_ring_size
        self.insert_state.template_ring_style = state.template_ring_style
        self.insert_state.smiles_active = state.smiles_active
        self.insert_state.smiles_preview_smiles = state.smiles_text
        self.insert_state.smiles_preview_center = None if state.smiles_center is None else QPointF(*state.smiles_center)
        if template_was_active and not state.template_active:
            self._clear_template_preview()
        if smiles_was_active and not state.smiles_active:
            self._clear_smiles_preview()

    def apply_insert_session_state(self, state: InsertSessionState) -> None:
        self._apply_insert_session_state(state)

    def begin_ring_template_insert(self, ring_size: int, style: str = "regular") -> None:
        next_state = begin_template_insert_state(self._insert_session_state(), ring_size, style)
        if next_state is None:
            return
        if self.insert_state.smiles_active:
            self._cancel_smiles_insert()
        self.canvas._clear_benzene_preview()
        self._apply_insert_session_state(next_state)
        self._render_template_preview(self.canvas.mapToScene(self.canvas.viewport().rect().center()))

    def load_smiles(self, smiles: str) -> None:
        smiles = smiles.strip()
        if not smiles:
            return
        model = self.canvas.rdkit.smiles_to_2d(smiles, scale=self.canvas.renderer.style.bond_length_px)
        if model is None:
            message = self.canvas.rdkit.last_error or "Failed to render SMILES."
            notify_error = getattr(self.canvas, "notify_error", None)
            if not (callable(notify_error) and notify_error(f"SMILES: {message}")):
                QMessageBox.warning(self.canvas, "SMILES Error", message)
            return
        snapshot = self._smiles_load_transaction_builder.capture()
        self.canvas.clear_scene()
        after_clear_next_atom_id = self.canvas.model.next_atom_id
        self.canvas.model = model
        self.canvas._rebuild_bond_adjacency()
        self.canvas.last_smiles_input = smiles
        self.canvas._render_model()
        command = self._smiles_load_transaction_builder.build_command(
            snapshot,
            after_clear_next_atom_id=after_clear_next_atom_id,
            after_smiles_input=smiles,
        )
        if command is not None:
            self.history.push(command)

    def begin_smiles_insert(self, smiles: str) -> None:
        if self.insert_state.template_active:
            self._cancel_template_insert()
        self.canvas._clear_benzene_preview()
        smiles = smiles.strip()
        if not smiles:
            return
        model = self.canvas.rdkit.smiles_to_2d(smiles, scale=self.canvas.renderer.style.bond_length_px)
        if model is None:
            message = self.canvas.rdkit.last_error or "Failed to render SMILES."
            notify_error = getattr(self.canvas, "notify_error", None)
            if not (callable(notify_error) and notify_error(f"SMILES: {message}")):
                QMessageBox.warning(self.canvas, "SMILES Error", message)
            return
        self.insert_state.smiles_preview_model = model
        center_xy = smiles_preview_center(model)
        if center_xy is None:
            self.insert_state.smiles_preview_model = None
            return
        next_state = begin_smiles_insert_state(self._insert_session_state(), smiles, center_xy)
        if next_state is None:
            self.insert_state.smiles_preview_model = None
            return
        self._apply_insert_session_state(next_state)
        self._render_smiles_preview(self.canvas.mapToScene(self.canvas.viewport().rect().center()))

    def _cancel_smiles_insert(self) -> None:
        self.insert_state.smiles_preview_model = None
        next_state = cancel_smiles_insert_state(self._insert_session_state())
        self._apply_insert_session_state(next_state)

    def cancel_smiles_insert(self) -> None:
        self._cancel_smiles_insert()

    def _commit_smiles_insert(self, pos: QPointF) -> None:
        plan = plan_smiles_commit(
            self.insert_state.smiles_preview_model,
            None
            if self.insert_state.smiles_preview_center is None
            else (self.insert_state.smiles_preview_center.x(), self.insert_state.smiles_preview_center.y()),
            (pos.x(), pos.y()),
        )
        if plan is None:
            self._cancel_smiles_insert()
            return
        if not self._insert_commit_service.apply_smiles_commit(
            plan,
            after_smiles_input=self.insert_state.smiles_preview_smiles,
        ):
            self._cancel_smiles_insert()
            return
        self._cancel_smiles_insert()

    def commit_smiles_insert(self, pos: QPointF) -> None:
        self._commit_smiles_insert(pos)

    def _clear_smiles_preview(self) -> None:
        (
            self.insert_state.smiles_preview_items,
            self.insert_state.smiles_preview_bond_items,
            self.insert_state.smiles_preview_atom_items,
        ) = clear_smiles_preview_helper(self.canvas.scene(), self.insert_state.smiles_preview_items)

    def clear_smiles_preview(self) -> None:
        self._clear_smiles_preview()

    def _smiles_preview_snapshot(self):
        return smiles_preview_snapshot_helper(
            self.insert_state.smiles_preview_bond_items,
            self.insert_state.smiles_preview_atom_items,
        )

    def smiles_preview_snapshot(self):
        return self._smiles_preview_snapshot()

    def _render_smiles_preview(self, pos: QPointF) -> None:
        atom_radius = max(0.6, self.canvas.renderer.style.bond_line_width * 0.6)
        preview_plan = plan_smiles_preview_update(
            self.insert_state.smiles_preview_model,
            None
            if self.insert_state.smiles_preview_center is None
            else (self.insert_state.smiles_preview_center.x(), self.insert_state.smiles_preview_center.y()),
            (pos.x(), pos.y()),
            atom_radius,
            self._smiles_preview_snapshot(),
            SmilesPreviewResolvers(parallel_bond_segments=self.canvas._parallel_bond_segments),
        )
        if preview_plan.action == "clear" or preview_plan.geometry is None:
            self._clear_smiles_preview()
            return
        (
            self.insert_state.smiles_preview_items,
            self.insert_state.smiles_preview_bond_items,
            self.insert_state.smiles_preview_atom_items,
        ) = apply_smiles_preview_geometry_helper(
            self.canvas.scene(),
            preview_plan.geometry,
            base_pen=self.canvas.renderer.bond_pen(),
            existing_items=self.insert_state.smiles_preview_items,
            existing_bond_items=self.insert_state.smiles_preview_bond_items,
            existing_atom_items=self.insert_state.smiles_preview_atom_items,
            action=preview_plan.action,
        )

    def render_smiles_preview(self, pos: QPointF) -> None:
        self._render_smiles_preview(pos)

    def _cancel_template_insert(self) -> None:
        next_state = cancel_template_insert_state(self._insert_session_state())
        self._apply_insert_session_state(next_state)

    def cancel_template_insert(self) -> None:
        self._cancel_template_insert()

    def _template_insert_request(self, pos: QPointF) -> TemplateInsertRequest | None:
        return build_template_insert_request(
            self._insert_session_state(),
            cursor_pos=(pos.x(), pos.y()),
            bond_id=self.canvas._find_bond_near(pos, self.canvas.renderer.style.bond_length_px * 0.35),
        )

    def template_insert_request(self, pos: QPointF) -> TemplateInsertRequest | None:
        return self._template_insert_request(pos)

    def _template_point_resolvers(self) -> TemplatePointResolvers:
        return TemplatePointResolvers(
            regular_ring_radius=self.canvas._regular_ring_radius,
            ring_points=self._resolve_ring_points_for_template,
            regular_ring_points_for_bond=self._resolve_regular_ring_points_for_template_bond,
            chair_points=self._resolve_chair_points_for_template,
            boat_points=self._resolve_boat_points_for_template,
            template_points_for_bond=self._resolve_template_points_for_template_bond,
        )

    def template_point_resolvers(self) -> TemplatePointResolvers:
        return self._template_point_resolvers()

    def _resolve_ring_points_for_template(
        self,
        center: tuple[float, float],
        n: int,
        radius: float | None,
    ) -> list[tuple[float, float]]:
        points = self.canvas._ring_points(QPointF(*center), n, radius=radius)
        return [(point.x(), point.y()) for point in points]

    def resolve_ring_points_for_template(
        self,
        center: tuple[float, float],
        n: int,
        radius: float | None,
    ) -> list[tuple[float, float]]:
        return self._resolve_ring_points_for_template(center, n, radius)

    def _resolve_regular_ring_points_for_template_bond(
        self,
        n: int,
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        result = self.canvas._regular_ring_points_for_bond(n, bond_id, QPointF(*center))
        if result is None:
            return None
        return [(point.x(), point.y()) for point in result[0]]

    def resolve_regular_ring_points_for_template_bond(
        self,
        n: int,
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self._resolve_regular_ring_points_for_template_bond(n, bond_id, center)

    def _resolve_chair_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        points = self.canvas._cyclohexane_chair_points(QPointF(*center))
        return [(point.x(), point.y()) for point in points]

    def resolve_chair_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self._resolve_chair_points_for_template(center)

    def _resolve_boat_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        points = self.canvas._cyclohexane_boat_points(QPointF(*center))
        return [(point.x(), point.y()) for point in points]

    def resolve_boat_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self._resolve_boat_points_for_template(center)

    def _resolve_template_points_for_template_bond(
        self,
        points_local: list[tuple[float, float]],
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        result = self.canvas._template_points_for_bond(
            [QPointF(x, y) for x, y in points_local],
            bond_id,
            QPointF(*center),
        )
        if result is None:
            return None
        return [(point.x(), point.y()) for point in result[0]]

    def resolve_template_points_for_template_bond(
        self,
        points_local: list[tuple[float, float]],
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self._resolve_template_points_for_template_bond(points_local, bond_id, center)

    @staticmethod
    def _template_points_from_pairs(
        points: list[tuple[float, float]] | None,
    ) -> list[QPointF] | None:
        if points is None:
            return None
        return [QPointF(x, y) for x, y in points]

    def _bond_merge_seed(self, bond_id: int | None) -> list[tuple[int, float, float]]:
        return self._insert_commit_service._bond_merge_seed(bond_id)

    def bond_merge_seed(self, bond_id: int | None) -> list[tuple[int, float, float]]:
        return self._bond_merge_seed(bond_id)

    def _commit_template_insert(self, pos: QPointF) -> None:
        request = self._template_insert_request(pos)
        if request is None:
            self._cancel_template_insert()
            return
        plan = plan_template_commit(request)
        if plan is None:
            self._cancel_template_insert()
            return
        resolution = None
        if plan.generator != "benzene":
            resolution = resolve_template_insert(request, plan, self._template_point_resolvers())
        if not self._insert_commit_service.apply_template_commit(
            pos,
            request=request,
            plan=plan,
            resolution=resolution,
        ):
            self._cancel_template_insert()
            return
        self._cancel_template_insert()

    def commit_template_insert(self, pos: QPointF) -> None:
        self._commit_template_insert(pos)

    def _clear_template_preview(self) -> None:
        (
            self.insert_state.template_preview_items,
            self.insert_state.template_preview_lines,
            self.insert_state.template_preview_dots,
        ) = clear_template_preview_helper(self.canvas.scene(), self.insert_state.template_preview_items)

    def clear_template_preview(self) -> None:
        self._clear_template_preview()

    def _render_template_preview(self, pos: QPointF) -> None:
        request = self._template_insert_request(pos)
        if request is None:
            self._clear_template_preview()
            return
        plan = plan_template_preview(request)
        if plan is None:
            self._clear_template_preview()
            return
        resolution = resolve_template_insert(request, plan, self._template_point_resolvers())
        if resolution is None:
            self._clear_template_preview()
            return
        points = self._template_points_from_pairs(resolution.points)
        if points is None:
            self._clear_template_preview()
            return
        atom_radius = max(0.6, self.canvas.renderer.style.bond_line_width * 0.6)
        preview_plan = plan_template_preview_update(
            [(point.x(), point.y()) for point in points],
            atom_radius,
            len(self.insert_state.template_preview_lines),
            len(self.insert_state.template_preview_dots),
        )
        if preview_plan.action == "clear" or preview_plan.geometry is None:
            self._clear_template_preview()
            return
        (
            self.insert_state.template_preview_items,
            self.insert_state.template_preview_lines,
            self.insert_state.template_preview_dots,
        ) = apply_template_preview_geometry_helper(
            self.canvas.scene(),
            preview_plan.geometry,
            base_pen=self.canvas.renderer.bond_pen(),
            existing_items=self.insert_state.template_preview_items,
            existing_lines=self.insert_state.template_preview_lines,
            existing_dots=self.insert_state.template_preview_dots,
            action=preview_plan.action,
        )

    def render_template_preview(self, pos: QPointF) -> None:
        self._render_template_preview(pos)


__all__ = ["InsertController"]
