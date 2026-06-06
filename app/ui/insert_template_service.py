from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPointF

from ui.benzene_preview_access import clear_benzene_preview_for
from ui.canvas_insert_state import CanvasInsertState
from ui.input_view_access import viewport_center_scene_pos_for
from ui.insert_commit_service import InsertCommitService
from ui.insert_mode_logic import (
    InsertSessionState,
    build_template_insert_request,
)
from ui.insert_mode_logic import (
    begin_template_insert as begin_template_insert_state,
)
from ui.insert_mode_logic import (
    cancel_template_insert as cancel_template_insert_state,
)
from ui.preview_scene_access import (
    apply_template_preview_geometry_for as apply_template_preview_geometry_helper,
)
from ui.preview_scene_access import (
    clear_template_preview_for as clear_template_preview_helper,
)
from ui.renderer_style_access import (
    bond_length_px_for,
    bond_line_width_for,
    bond_pen_for,
)
from ui.template_geometry_resolver_service import TemplateGeometryResolverService
from ui.template_insert_logic import (
    TemplateInsertRequest,
    TemplateInsertResolution,
    TemplatePointResolvers,
    plan_template_commit,
    plan_template_preview,
)
from ui.template_preview_logic import plan_template_preview_update


class InsertTemplateService:
    def __init__(
        self,
        canvas,
        *,
        insert_state: CanvasInsertState,
        hit_testing_service,
        insert_commit_service: InsertCommitService,
        session_state: Callable[[], InsertSessionState],
        apply_session_state: Callable[[InsertSessionState], None],
        cancel_smiles_insert: Callable[[], None],
        render_template_preview: Callable[[QPointF], None] | None = None,
        template_geometry: TemplateGeometryResolverService | None = None,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state
        self.hit_testing_service = hit_testing_service
        self.insert_commit_service = insert_commit_service
        self.template_geometry = template_geometry or TemplateGeometryResolverService(canvas)
        self._session_state = session_state
        self._apply_session_state = apply_session_state
        self._cancel_smiles_insert = cancel_smiles_insert
        self._render_template_preview_callback = render_template_preview

    def begin_ring_template_insert(self, ring_size: int, style: str = "regular") -> None:
        next_state = begin_template_insert_state(self._session_state(), ring_size, style)
        if next_state is None:
            return
        if self.insert_state.smiles_active:
            self._cancel_smiles_insert()
        clear_benzene_preview_for(self.canvas)
        self._apply_session_state(next_state)
        self._render_template_preview(viewport_center_scene_pos_for(self.canvas))

    def _render_template_preview(self, pos: QPointF) -> None:
        if self._render_template_preview_callback is not None:
            self._render_template_preview_callback(pos)
            return
        self.render_template_preview(pos)

    def cancel_template_insert(self) -> None:
        next_state = cancel_template_insert_state(self._session_state())
        self._apply_session_state(next_state)

    def template_insert_request(self, pos: QPointF) -> TemplateInsertRequest | None:
        return build_template_insert_request(
            self._session_state(),
            cursor_pos=(pos.x(), pos.y()),
            bond_id=self.hit_testing_service.find_bond_near(
                pos,
                bond_length_px_for(self.canvas) * 0.35,
            ),
        )

    def template_point_resolvers(self) -> TemplatePointResolvers:
        return self.template_geometry.point_resolvers()

    def resolve_ring_points_for_template(
        self,
        center: tuple[float, float],
        n: int,
        radius: float | None,
    ) -> list[tuple[float, float]]:
        return self.template_geometry.resolve_ring_points(center, n, radius)

    def resolve_regular_ring_points_for_template_bond(
        self,
        n: int,
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self.template_geometry.resolve_regular_ring_points_for_bond(n, bond_id, center)

    def resolve_chair_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self.template_geometry.resolve_chair_points(center)

    def resolve_boat_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self.template_geometry.resolve_boat_points(center)

    def resolve_template_points_for_template_bond(
        self,
        points_local: list[tuple[float, float]],
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self.template_geometry.resolve_template_points_for_bond(points_local, bond_id, center)

    def template_points_from_pairs(
        self,
        points: list[tuple[float, float]] | None,
    ) -> list[QPointF] | None:
        return self.template_geometry.points_from_pairs(points)

    def commit_template_insert(self, pos: QPointF) -> None:
        self.commit_template_request(pos, self.template_insert_request(pos))

    def commit_template_request(self, pos: QPointF, request: TemplateInsertRequest | None) -> None:
        if request is None:
            self.cancel_template_insert()
            return
        plan = plan_template_commit(request)
        if plan is None:
            self.cancel_template_insert()
            return
        resolution: TemplateInsertResolution | None = None
        if plan.generator != "benzene":
            resolution = self.template_geometry.resolve_insert(request, plan)
        if not self.insert_commit_service.apply_template_commit(
            pos,
            request=request,
            plan=plan,
            resolution=resolution,
        ):
            self.cancel_template_insert()
            return
        self.cancel_template_insert()

    def clear_template_preview(self) -> None:
        (
            self.insert_state.template_preview_items,
            self.insert_state.template_preview_lines,
            self.insert_state.template_preview_dots,
        ) = clear_template_preview_helper(self.canvas, self.insert_state.template_preview_items)

    def render_template_preview(self, pos: QPointF) -> None:
        self.render_template_request_preview(pos, self.template_insert_request(pos))

    def render_template_request_preview(
        self,
        pos: QPointF,
        request: TemplateInsertRequest | None,
        *,
        clear_template_preview: Callable[[], None] | None = None,
    ) -> None:
        clear_preview = clear_template_preview or self.clear_template_preview
        if request is None:
            clear_preview()
            return
        plan = plan_template_preview(request)
        if plan is None:
            clear_preview()
            return
        resolution = self.template_geometry.resolve_insert(request, plan)
        if resolution is None:
            clear_preview()
            return
        points = self.template_points_from_pairs(resolution.points)
        if points is None:
            clear_preview()
            return
        atom_radius = max(0.6, bond_line_width_for(self.canvas) * 0.6)
        preview_plan = plan_template_preview_update(
            [(point.x(), point.y()) for point in points],
            atom_radius,
            len(self.insert_state.template_preview_lines),
            len(self.insert_state.template_preview_dots),
        )
        if preview_plan.action == "clear" or preview_plan.geometry is None:
            clear_preview()
            return
        (
            self.insert_state.template_preview_items,
            self.insert_state.template_preview_lines,
            self.insert_state.template_preview_dots,
        ) = apply_template_preview_geometry_helper(
            self.canvas,
            preview_plan.geometry,
            base_pen=bond_pen_for(self.canvas),
            existing_items=self.insert_state.template_preview_items,
            existing_lines=self.insert_state.template_preview_lines,
            existing_dots=self.insert_state.template_preview_dots,
            action=preview_plan.action,
        )


__all__ = ["InsertTemplateService"]
