from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QPointF

from ui.structure_growth_logic import (
    mirrored_local_points,
    other_atom_id_from_bond_result,
)


@dataclass(frozen=True, slots=True)
class StructureGrowthBuildActions:
    atom_point: Callable[[int], QPointF]
    sprout_bond_endpoint: Callable[..., QPointF | None]
    add_bond_between_points: Callable[[QPointF, QPointF, str, int], tuple[int, int] | None]
    add_benzene_ring: Callable[..., object | None]
    has_atom: Callable[[int], bool]
    default_bond_endpoint: Callable[[QPointF, int | None], QPointF]
    add_atom_label: Callable[..., None]
    regular_ring_points_for_atom: Callable[[int, int], object | None]
    regular_ring_points_for_bond: Callable[[int, int, QPointF], object | None]
    cyclohexane_chair_points: Callable[[QPointF], list[QPointF]]
    template_points_for_bond: Callable[[list[QPointF], int, QPointF], object | None]
    add_ring_from_points: Callable[..., list[int]]
    bond_placement_context: Callable[[int], object | None]
    run_recorded_additions_action: Callable[[Callable[[], bool]], bool]


class StructureGrowthBuildService:
    def __init__(self, actions: StructureGrowthBuildActions) -> None:
        self.actions = actions

    def sprout_bond_from_atom(
        self,
        atom_id: int,
        *,
        style: str,
        order: int,
        cyclic: bool = False,
    ) -> tuple[int, int] | None:
        start = self.actions.atom_point(atom_id)
        end = self.actions.sprout_bond_endpoint(atom_id, cyclic=cyclic)
        if end is None:
            return None
        return self.actions.add_bond_between_points(start, end, style, order)

    def sprout_benzene_from_atom(self, atom_id: int) -> object | None:
        return self.actions.add_benzene_ring(self.actions.atom_point(atom_id), attach_atom_id=atom_id)

    def sprout_acetyl_from_atom(self, atom_id: int) -> None:
        start = self.actions.atom_point(atom_id)
        carbon_end = self.actions.sprout_bond_endpoint(atom_id, cyclic=False)
        if carbon_end is None:
            return
        result = self.actions.add_bond_between_points(start, carbon_end, "single", 1)
        carbon_id = other_atom_id_from_bond_result(atom_id, result)
        if carbon_id is None or not self.actions.has_atom(carbon_id):
            return
        carbon_point = self.actions.atom_point(carbon_id)
        oxygen_end = self.actions.default_bond_endpoint(carbon_point, carbon_id)
        result = self.actions.add_bond_between_points(carbon_point, oxygen_end, "double", 2)
        oxygen_id = other_atom_id_from_bond_result(carbon_id, result)
        if oxygen_id is not None and self.actions.has_atom(oxygen_id):
            self.actions.add_atom_label(oxygen_id, "O", show_carbon=True)
        methyl_end = self.actions.default_bond_endpoint(carbon_point, carbon_id)
        self.actions.add_bond_between_points(carbon_point, methyl_end, "single", 1)

    def sprout_regular_ring_from_atom(self, atom_id: int, n: int) -> None:
        def _build() -> bool:
            result = self.actions.regular_ring_points_for_atom(n, atom_id)
            if result is None:
                return False
            points, merge = result
            self.actions.add_ring_from_points(points, merge=merge)
            return True

        self.actions.run_recorded_additions_action(_build)

    def fuse_regular_ring_to_bond(self, bond_id: int, n: int) -> None:
        def _build() -> bool:
            placement = self.actions.bond_placement_context(bond_id)
            if placement is None:
                return False
            result = self.actions.regular_ring_points_for_bond(n, bond_id, placement.midpoint)
            if result is None:
                return False
            points, merge = result
            self.actions.add_ring_from_points(points, merge=merge)
            return True

        self.actions.run_recorded_additions_action(_build)

    def fuse_chair_to_bond(self, bond_id: int, mirrored: bool = False) -> None:
        def _build() -> bool:
            local_center = QPointF(0.0, 0.0)
            points_local = mirrored_local_points(self.actions.cyclohexane_chair_points(local_center), mirrored)
            placement = self.actions.bond_placement_context(bond_id)
            if placement is None:
                return False
            result = self.actions.template_points_for_bond(points_local, bond_id, placement.midpoint)
            if result is None:
                return False
            points, merge = result
            self.actions.add_ring_from_points(points, merge=merge)
            return True

        self.actions.run_recorded_additions_action(_build)

    def fuse_benzene_to_bond(self, bond_id: int) -> object | None:
        placement = self.actions.bond_placement_context(bond_id)
        if placement is None:
            return None
        return self.actions.add_benzene_ring(placement.midpoint, attach_bond_id=bond_id)


__all__ = ["StructureGrowthBuildActions", "StructureGrowthBuildService"]
