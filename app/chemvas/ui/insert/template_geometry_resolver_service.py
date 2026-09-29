from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.features.groups import connection_allowed, growth_anchors
from chemvas.features.insertion import (
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplateInsertResolution,
    TemplatePointResolvers,
    resolve_template_insert,
)
from chemvas.ui.molecule.structure_geometry_access import (
    cyclohexane_boat_points_for,
    cyclohexane_chair_flipped_points_for,
    cyclohexane_chair_points_for,
    regular_ring_points_for_atom_for,
    regular_ring_points_for_bond_for,
    regular_ring_radius_for,
    ring_points_for,
    template_points_for_bond_for,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PyQt6.QtCore import QPointF


class TemplateGeometryResolverService:
    def __init__(self, canvas, *, point_factory=None) -> None:
        self.canvas = canvas
        if point_factory is None:
            from PyQt6.QtCore import QPointF

            point_factory = QPointF
        # The browser adapter resolves templates with its own point type.
        self.point_factory = point_factory

    def point_resolvers(self) -> TemplatePointResolvers:
        return TemplatePointResolvers(
            regular_ring_radius=lambda n: regular_ring_radius_for(self.canvas, n),
            ring_points=self.resolve_ring_points,
            regular_ring_points_for_atom=self.resolve_regular_ring_points_for_atom,
            regular_ring_points_for_bond=self.resolve_regular_ring_points_for_bond,
            chair_points=self.resolve_chair_points,
            chair_flipped_points=self.resolve_chair_flipped_points,
            boat_points=self.resolve_boat_points,
            template_points_for_bond=self.resolve_template_points_for_bond,
        )

    def resolve_insert(
        self,
        request: TemplateInsertRequest,
        plan: TemplateInsertPlan,
    ) -> TemplateInsertResolution | None:
        if plan.generator == "benzene":
            anchors = growth_anchors(
                self.canvas.model.bonds, atom_id=plan.atom_id, bond_id=plan.bond_id
            )
            if not connection_allowed(
                self.canvas.runtime_state.group_state.groups,
                self.canvas.model.bonds,
                anchors,
            ):
                return None
            builder = self.canvas.services.structure_build_service
            placement = builder.benzene_builder.plan_placement(
                self.point_factory(*request.cursor_pos),
                plan.atom_id,
                plan.bond_id,
                benzene_ring_points=builder.benzene_ring_points,
            )
            if placement is None:
                return None
            return TemplateInsertResolution(
                plan=plan,
                points=[(point.x(), point.y()) for point in placement.points],
                bond_orders=placement.bond_orders,
            )
        return resolve_template_insert(request, plan, self.point_resolvers())

    def resolve_ring_points(
        self,
        center: tuple[float, float],
        n: int,
        radius: float | None,
    ) -> list[tuple[float, float]]:
        points = ring_points_for(
            self.canvas,
            self.point_factory(*center),
            n,
            radius=radius,
            point_factory=self.point_factory,
        )
        return [(point.x(), point.y()) for point in points]

    def resolve_regular_ring_points_for_bond(
        self,
        n: int,
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        result = regular_ring_points_for_bond_for(
            self.canvas,
            n,
            bond_id,
            self.point_factory(*center),
            point_factory=self.point_factory,
        )
        if result is None:
            return None
        return [(point.x(), point.y()) for point in result[0]]

    def resolve_regular_ring_points_for_atom(
        self,
        n: int,
        atom_id: int,
    ) -> list[tuple[float, float]] | None:
        result = regular_ring_points_for_atom_for(
            self.canvas, n, atom_id, point_factory=self.point_factory
        )
        if result is None:
            return None
        return [(point.x(), point.y()) for point in result[0]]

    def resolve_chair_points(
        self, center: tuple[float, float]
    ) -> list[tuple[float, float]]:
        points = cyclohexane_chair_points_for(
            self.canvas, self.point_factory(*center), point_factory=self.point_factory
        )
        return [(point.x(), point.y()) for point in points]

    def resolve_chair_flipped_points(
        self, center: tuple[float, float]
    ) -> list[tuple[float, float]]:
        points = cyclohexane_chair_flipped_points_for(
            self.canvas, self.point_factory(*center), point_factory=self.point_factory
        )
        return [(point.x(), point.y()) for point in points]

    def resolve_boat_points(
        self, center: tuple[float, float]
    ) -> list[tuple[float, float]]:
        points = cyclohexane_boat_points_for(
            self.canvas, self.point_factory(*center), point_factory=self.point_factory
        )
        return [(point.x(), point.y()) for point in points]

    def resolve_template_points_for_bond(
        self,
        points_local: Sequence[tuple[float, float]],
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        result = template_points_for_bond_for(
            self.canvas,
            [self.point_factory(x, y) for x, y in points_local],
            bond_id,
            self.point_factory(*center),
            point_factory=self.point_factory,
        )
        if result is None:
            return None
        return [(point.x(), point.y()) for point in result[0]]

    def points_from_pairs(
        self,
        points: list[tuple[float, float]] | None,
    ) -> list[QPointF] | None:
        if points is None:
            return None
        return [self.point_factory(x, y) for x, y in points]


__all__ = ["TemplateGeometryResolverService"]
