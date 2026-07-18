from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QPointF

from chemvas.features.insertion import (
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplateInsertResolution,
    TemplatePointResolvers,
    resolve_template_insert,
)
from chemvas.ui.structure_geometry_access import (
    cyclohexane_boat_points_for,
    cyclohexane_chair_flipped_points_for,
    cyclohexane_chair_points_for,
    regular_ring_points_for_atom_for,
    regular_ring_points_for_bond_for,
    regular_ring_radius_for,
    ring_points_for,
    template_points_for_bond_for,
)


class TemplateGeometryResolverService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

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
        return resolve_template_insert(request, plan, self.point_resolvers())

    def resolve_ring_points(
        self,
        center: tuple[float, float],
        n: int,
        radius: float | None,
    ) -> list[tuple[float, float]]:
        points = ring_points_for(self.canvas, QPointF(*center), n, radius=radius)
        return [(point.x(), point.y()) for point in points]

    def resolve_regular_ring_points_for_bond(
        self,
        n: int,
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        result = regular_ring_points_for_bond_for(
            self.canvas, n, bond_id, QPointF(*center)
        )
        if result is None:
            return None
        return [(point.x(), point.y()) for point in result[0]]

    def resolve_regular_ring_points_for_atom(
        self,
        n: int,
        atom_id: int,
    ) -> list[tuple[float, float]] | None:
        result = regular_ring_points_for_atom_for(self.canvas, n, atom_id)
        if result is None:
            return None
        return [(point.x(), point.y()) for point in result[0]]

    def resolve_chair_points(
        self, center: tuple[float, float]
    ) -> list[tuple[float, float]]:
        points = cyclohexane_chair_points_for(self.canvas, QPointF(*center))
        return [(point.x(), point.y()) for point in points]

    def resolve_chair_flipped_points(
        self, center: tuple[float, float]
    ) -> list[tuple[float, float]]:
        points = cyclohexane_chair_flipped_points_for(self.canvas, QPointF(*center))
        return [(point.x(), point.y()) for point in points]

    def resolve_boat_points(
        self, center: tuple[float, float]
    ) -> list[tuple[float, float]]:
        points = cyclohexane_boat_points_for(self.canvas, QPointF(*center))
        return [(point.x(), point.y()) for point in points]

    def resolve_template_points_for_bond(
        self,
        points_local: Sequence[tuple[float, float]],
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        result = template_points_for_bond_for(
            self.canvas,
            [QPointF(x, y) for x, y in points_local],
            bond_id,
            QPointF(*center),
        )
        if result is None:
            return None
        return [(point.x(), point.y()) for point in result[0]]

    @staticmethod
    def points_from_pairs(
        points: list[tuple[float, float]] | None,
    ) -> list[QPointF] | None:
        if points is None:
            return None
        return [QPointF(x, y) for x, y in points]


__all__ = ["TemplateGeometryResolverService"]
