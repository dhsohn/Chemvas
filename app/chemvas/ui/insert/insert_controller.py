from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.features.insertion import (
    TemplateInsertRequest,
    TemplateInsertResolution,
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
from chemvas.ui.canvas.pick_radius_access import (
    STRUCTURE_BOND_PICK_RADIUS_RATIO,
    atom_pick_radius_for,
)
from chemvas.ui.canvas.sheet_setup_access import scene_pos_in_sheet_for
from chemvas.ui.insert.insert_commit_service import InsertCommitService
from chemvas.ui.insert.insert_mode_logic import (
    TEMPLATE_BOND_GATE_RATIO,
    InsertSessionState,
    build_template_insert_request,
    clear_insert_session,
)
from chemvas.ui.insert.insert_mode_logic import (
    begin_template_insert as begin_template_insert_state,
)
from chemvas.ui.insert.preview_scene_renderer import (
    apply_template_preview_geometry,
    clear_template_preview,
)
from chemvas.ui.insert.template_geometry_resolver_service import (
    TemplateGeometryResolverService,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene

    from chemvas.ui.canvas.canvas_insert_state import CanvasInsertState
    from chemvas.ui.canvas.canvas_view import CanvasView


class InsertController:
    def __init__(
        self,
        canvas: CanvasView,
        insert_state: CanvasInsertState | None = None,
        *,
        hit_testing_service,
        insert_commit_service: InsertCommitService | None = None,
        graph_service,
    ) -> None:
        self.canvas = canvas
        self.insert_state = (
            insert_state
            if insert_state is not None
            else canvas.runtime_state.insert_state
        )
        self.hit_testing_service = hit_testing_service
        self.graph_service = graph_service
        self.insert_commit_service = insert_commit_service or InsertCommitService(
            canvas,
            bond_exists=self.graph_service.bond_exists,
        )
        self.template_geometry = TemplateGeometryResolverService(canvas)

    def insert_session_state(self) -> InsertSessionState:
        return InsertSessionState(
            template_active=self.insert_state.template_active,
            template_ring_size=self.insert_state.template_ring_size,
            template_ring_style=self.insert_state.template_ring_style,
        )

    def apply_insert_session_state(self, state: InsertSessionState) -> None:
        template_was_active = self.insert_state.template_active
        self.insert_state.template_active = state.template_active
        self.insert_state.template_ring_size = state.template_ring_size
        self.insert_state.template_ring_style = state.template_ring_style
        if template_was_active and not state.template_active:
            self.clear_template_preview()

    def _scene(self) -> QGraphicsScene:
        scene = self.canvas.scene()
        if scene is None:
            raise RuntimeError("Canvas has no scene.")
        return scene

    def begin_ring_template_insert(
        self, ring_size: int, style: str = "regular"
    ) -> None:
        next_state = begin_template_insert_state(ring_size, style)
        if next_state is None:
            return
        self.apply_insert_session_state(next_state)

    def cancel_template_insert(self) -> None:
        self.apply_insert_session_state(clear_insert_session())

    def template_insert_request(self, pos: QPointF) -> TemplateInsertRequest | None:
        atom_id, bond_id = self._template_structure_target_ids(pos)
        return build_template_insert_request(
            self.insert_session_state(),
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
            self.canvas.renderer.style.bond_length_px * TEMPLATE_BOND_GATE_RATIO,
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
            bond_pick_radius=self.canvas.renderer.style.bond_length_px
            * STRUCTURE_BOND_PICK_RADIUS_RATIO,
        )

    def _template_nearby_bond_hit(self, pos: QPointF) -> tuple[int, float] | None:
        find_bond_near = getattr(self.hit_testing_service, "find_bond_near", None)
        if not callable(find_bond_near):
            return None
        gate = self.canvas.renderer.style.bond_length_px * TEMPLATE_BOND_GATE_RATIO
        bond_id = find_bond_near(pos, gate)
        if bond_id is None:
            return None
        distance_point_to_segment = getattr(
            self.hit_testing_service, "distance_point_to_segment", None
        )
        bond = self.canvas.model.bond_for_id(bond_id)
        if bond is None:
            return None
        atom_a = self.canvas.model.atom_for_id(bond.a)
        atom_b = self.canvas.model.atom_for_id(bond.b)
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

    def template_points_from_pairs(
        self,
        points: list[tuple[float, float]] | None,
    ) -> list[QPointF] | None:
        return self.template_geometry.points_from_pairs(points)

    def commit_template_insert(self, pos: QPointF) -> None:
        if not scene_pos_in_sheet_for(self.canvas, pos):
            self.clear_template_preview()
            return
        request = self.template_insert_request(pos)
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
        ) = clear_template_preview(
            self._scene(), self.insert_state.template_preview_items
        )

    def render_template_preview(self, pos: QPointF) -> None:
        if not scene_pos_in_sheet_for(self.canvas, pos):
            self.clear_template_preview()
            return
        request = self.template_insert_request(pos)
        if request is None:
            self.clear_template_preview()
            return
        plan = plan_template_preview(request)
        if plan is None:
            self.clear_template_preview()
            return
        resolution = self.template_geometry.resolve_insert(request, plan)
        if resolution is None:
            self.clear_template_preview()
            return
        points = self.template_points_from_pairs(resolution.points)
        if points is None:
            self.clear_template_preview()
            return
        atom_radius = max(0.6, self.canvas.renderer.style.bond_line_width * 0.6)
        preview_plan = plan_template_preview_update(
            [(point.x(), point.y()) for point in points],
            atom_radius,
            len(self.insert_state.template_preview_lines),
            len(self.insert_state.template_preview_dots),
            aromatic=getattr(plan, "ring_style", None) == "benzene"
            and getattr(plan, "ring_size", None) == 6,
            bond_orders=resolution.bond_orders,
        )
        if preview_plan.action == "clear" or preview_plan.geometry is None:
            self.clear_template_preview()
            return
        (
            self.insert_state.template_preview_items,
            self.insert_state.template_preview_lines,
            self.insert_state.template_preview_dots,
        ) = apply_template_preview_geometry(
            self._scene(),
            preview_plan.geometry,
            base_pen=self.canvas.renderer.bond_pen(),
            existing_items=self.insert_state.template_preview_items,
            existing_lines=self.insert_state.template_preview_lines,
            existing_dots=self.insert_state.template_preview_dots,
            action=preview_plan.action,
        )


__all__ = ["InsertController"]
