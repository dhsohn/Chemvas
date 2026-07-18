from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPointF

from chemvas.features.insertion import (
    TemplateInsertRequest,
    TemplateInsertResolution,
    TemplatePointResolvers,
    plan_template_commit,
    plan_template_preview,
    plan_template_preview_update,
)
from chemvas.features.selection import (
    AtomHitCandidate,
    BondHitCandidate,
    StructureHit,
    choose_preferred_structure_hit,
)
from chemvas.ui.benzene_preview_access import clear_benzene_preview_for
from chemvas.ui.canvas_insert_state import CanvasInsertState
from chemvas.ui.canvas_model_access import atom_for_id, bond_for_id
from chemvas.ui.insert_commit_service import InsertCommitService
from chemvas.ui.insert_mode_logic import (
    InsertSessionState,
    build_template_insert_request,
)
from chemvas.ui.insert_mode_logic import (
    begin_template_insert as begin_template_insert_state,
)
from chemvas.ui.insert_mode_logic import (
    cancel_template_insert as cancel_template_insert_state,
)
from chemvas.ui.pick_radius_access import atom_pick_radius_for, bond_pick_radius_for
from chemvas.ui.preview_scene_access import (
    apply_template_preview_geometry_for as apply_template_preview_geometry_helper,
)
from chemvas.ui.preview_scene_access import (
    clear_template_preview_for as clear_template_preview_helper,
)
from chemvas.ui.renderer_style_access import (
    bond_length_px_for,
    bond_line_width_for,
    bond_pen_for,
)
from chemvas.ui.template_geometry_resolver_service import (
    TemplateGeometryResolverService,
)


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
        template_geometry: TemplateGeometryResolverService | None = None,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state
        self.hit_testing_service = hit_testing_service
        self.insert_commit_service = insert_commit_service
        self.template_geometry = template_geometry or TemplateGeometryResolverService(
            canvas
        )
        self._session_state = session_state
        self._apply_session_state = apply_session_state
        self._cancel_smiles_insert = cancel_smiles_insert

    def begin_ring_template_insert(
        self, ring_size: int, style: str = "regular"
    ) -> None:
        next_state = begin_template_insert_state(
            self._session_state(), ring_size, style
        )
        if next_state is None:
            return
        if self.insert_state.smiles_active:
            self._cancel_smiles_insert()
        clear_benzene_preview_for(self.canvas)
        self._apply_session_state(next_state)

    def cancel_template_insert(self) -> None:
        next_state = cancel_template_insert_state(self._session_state())
        self._apply_session_state(next_state)

    def template_insert_request(self, pos: QPointF) -> TemplateInsertRequest | None:
        atom_id, bond_id = self._template_structure_target_ids(pos)
        return build_template_insert_request(
            self._session_state(),
            cursor_pos=(pos.x(), pos.y()),
            bond_id=bond_id,
            atom_id=atom_id,
        )

    def _template_structure_target_ids(
        self, pos: QPointF
    ) -> tuple[int | None, int | None]:
        direct_hit = self._direct_structure_hit(pos)
        if (
            direct_hit is not None
            and direct_hit.kind == "atom"
            and isinstance(direct_hit.id, int)
        ):
            return direct_hit.id, None

        preferred_hit = self._preferred_nearby_structure_hit(pos)
        if preferred_hit is not None:
            if preferred_hit.kind == "atom" and isinstance(preferred_hit.id, int):
                return preferred_hit.id, None
            if preferred_hit.kind == "bond" and isinstance(preferred_hit.id, int):
                return None, preferred_hit.id

        find_bond_near = getattr(self.hit_testing_service, "find_bond_near", None)
        if not callable(find_bond_near):
            return None, None
        return None, find_bond_near(
            pos,
            bond_length_px_for(self.canvas) * 0.35,
        )

    def _direct_structure_hit(self, pos: QPointF) -> StructureHit | None:
        item_at_scene_pos = getattr(self.hit_testing_service, "item_at_scene_pos", None)
        if not callable(item_at_scene_pos):
            return None
        item = item_at_scene_pos(pos)
        if item is None:
            return None
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if isinstance(atom_id, int):
                return StructureHit(kind="atom", id=atom_id)
        return None

    def _preferred_nearby_structure_hit(self, pos: QPointF) -> StructureHit | None:
        nearest_atom_hit = getattr(self.hit_testing_service, "nearest_atom_hit", None)
        if not callable(nearest_atom_hit):
            return None
        atom_hit = nearest_atom_hit(pos)
        bond_hit = self._template_nearby_bond_hit(pos)
        return choose_preferred_structure_hit(
            AtomHitCandidate(
                atom_id=atom_hit[0],
                distance=atom_hit[1],
            )
            if atom_hit is not None
            else None,
            BondHitCandidate(bond_id=bond_hit[0], distance=bond_hit[1])
            if bond_hit is not None
            else None,
            atom_pick_radius=atom_pick_radius_for(self.canvas),
            bond_pick_radius=bond_pick_radius_for(self.canvas),
        )

    def _template_nearby_bond_hit(self, pos: QPointF) -> tuple[int, float] | None:
        find_bond_near = getattr(self.hit_testing_service, "find_bond_near", None)
        if not callable(find_bond_near):
            return None
        gate = bond_length_px_for(self.canvas) * 0.35
        bond_id = find_bond_near(pos, gate)
        if bond_id is None:
            return None
        distance_point_to_segment = getattr(
            self.hit_testing_service, "distance_point_to_segment", None
        )
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return None
        atom_a = atom_for_id(self.canvas, bond.a)
        atom_b = atom_for_id(self.canvas, bond.b)
        if atom_a is None or atom_b is None:
            return None
        if callable(distance_point_to_segment):
            distance = distance_point_to_segment(
                pos,
                QPointF(atom_a.x, atom_a.y),
                QPointF(atom_b.x, atom_b.y),
            )
        else:
            nearest_bond_hit = getattr(
                self.hit_testing_service, "nearest_bond_hit", None
            )
            nearest_hit = nearest_bond_hit(pos) if callable(nearest_bond_hit) else None
            distance = (
                nearest_hit[1]
                if nearest_hit is not None and nearest_hit[0] == bond_id
                else gate
            )
        return bond_id, distance

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
        return self.template_geometry.resolve_regular_ring_points_for_bond(
            n, bond_id, center
        )

    def resolve_chair_points_for_template(
        self, center: tuple[float, float]
    ) -> list[tuple[float, float]]:
        return self.template_geometry.resolve_chair_points(center)

    def resolve_boat_points_for_template(
        self, center: tuple[float, float]
    ) -> list[tuple[float, float]]:
        return self.template_geometry.resolve_boat_points(center)

    def resolve_template_points_for_template_bond(
        self,
        points_local: list[tuple[float, float]],
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self.template_geometry.resolve_template_points_for_bond(
            points_local, bond_id, center
        )

    def template_points_from_pairs(
        self,
        points: list[tuple[float, float]] | None,
    ) -> list[QPointF] | None:
        return self.template_geometry.points_from_pairs(points)

    def commit_template_insert(self, pos: QPointF) -> None:
        self.commit_template_request(pos, self.template_insert_request(pos))

    def commit_template_request(
        self, pos: QPointF, request: TemplateInsertRequest | None
    ) -> None:
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
        self.clear_template_preview()

    def clear_template_preview(self) -> None:
        (
            self.insert_state.template_preview_items,
            self.insert_state.template_preview_lines,
            self.insert_state.template_preview_dots,
        ) = clear_template_preview_helper(
            self.canvas, self.insert_state.template_preview_items
        )

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
            aromatic=getattr(plan, "ring_style", None) == "benzene"
            and getattr(plan, "ring_size", None) == 6,
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
