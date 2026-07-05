from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QPointF

from ui.renderer_style_access import bond_length_px_for
from ui.structure_build_committer import StructureBuildCommitter
from ui.structure_growth_logic import (
    alternating_ring_bond_specs,
    crown_ether_elements,
    fused_benzene_centers,
)


@dataclass(frozen=True, slots=True)
class StructureFragmentBuildActions:
    viewport_center: Callable[[], QPointF]
    regular_ring_radius: Callable[[int], float]
    ring_points: Callable
    regular_ring_points_for_bond: Callable
    cyclohexane_chair_points: Callable
    cyclohexane_boat_points: Callable
    add_ring_from_points: Callable
    add_linear_chain: Callable
    run_recorded_build: Callable
    latest_bond_id: Callable[[int], int]


class StructureFragmentBuildService:
    def __init__(self, canvas, committer: StructureBuildCommitter) -> None:
        self.canvas = canvas
        self.committer = committer

    def add_regular_ring_template(self, n: int, actions: StructureFragmentBuildActions) -> None:
        center = actions.viewport_center()
        radius = actions.regular_ring_radius(n)
        actions.add_ring_from_points(actions.ring_points(center, n, radius=radius))

    def add_hetero_ring_template(
        self,
        n: int,
        elements: list[str],
        actions: StructureFragmentBuildActions,
        *,
        bond_orders: list[int] | None = None,
    ) -> None:
        center = actions.viewport_center()
        radius = actions.regular_ring_radius(n)
        actions.add_ring_from_points(
            actions.ring_points(center, n, radius=radius),
            elements=elements,
            bond_orders=bond_orders,
        )

    def add_fused_benzenes(self, count: int, mode: str, actions: StructureFragmentBuildActions) -> None:
        center = actions.viewport_center()
        step = bond_length_px_for(self.canvas) * math.sqrt(3.0)
        merge: list = []
        for ring_center in fused_benzene_centers(center, step, count, mode):
            points = actions.ring_points(ring_center, 6)
            bond_orders = [order for _, _, order in alternating_ring_bond_specs(range(len(points)))]
            actions.add_ring_from_points(points, merge=merge, bond_orders=bond_orders)

    def add_crown_ether(self, atoms: int, oxygens: int, actions: StructureFragmentBuildActions) -> None:
        center = actions.viewport_center()
        points = actions.ring_points(center, atoms, radius=bond_length_px_for(self.canvas) * 1.4)
        actions.add_ring_from_points(points, elements=crown_ether_elements(atoms, oxygens))

    def add_cyclohexane_chair(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            actions.add_ring_from_points(actions.cyclohexane_chair_points(center))

        actions.run_recorded_build(_build)

    def add_cyclohexane_boat(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            actions.add_ring_from_points(actions.cyclohexane_boat_points(center))

        actions.run_recorded_build(_build)

    def add_fused_heterocycle_template(
        self,
        *,
        ring_size: int,
        elements: list[str],
        x_scale: float,
        y_scale: float,
        actions: StructureFragmentBuildActions,
    ) -> None:
        center = actions.viewport_center()
        atom_ids = actions.add_ring_from_points(
            actions.ring_points(center, 6),
            bond_orders=_benzene_bond_orders(),
        )
        bond_id = self.committer.bond_id_between(atom_ids[1], atom_ids[2])
        if bond_id is None:
            return
        center_hint = QPointF(
            center.x() + bond_length_px_for(self.canvas) * x_scale,
            center.y() + bond_length_px_for(self.canvas) * y_scale,
        )
        ring_result = actions.regular_ring_points_for_bond(ring_size, bond_id, center_hint)
        if ring_result is None:
            return
        points, merge = ring_result
        ring_elements = _fused_heterocycle_elements(ring_size, elements)
        actions.add_ring_from_points(
            points,
            elements=ring_elements,
            merge=merge,
            bond_orders=_fused_heterocycle_bond_orders(ring_size, ring_elements),
        )

    def add_phenyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            atom_ids = actions.add_ring_from_points(
                actions.ring_points(center, 6),
                bond_orders=_benzene_bond_orders(first_order=1),
            )
            attach = QPointF(center.x() - bond_length_px_for(self.canvas) * 2.0, center.y())
            attach_id = self.committer.add_atom("C", attach.x(), attach.y())
            self.committer.add_bond(atom_ids[0], attach_id)
            self.committer.add_bond_graphics(actions.latest_bond_id(1))

        actions.run_recorded_build(_build)

    def add_benzyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            atom_ids = actions.add_ring_from_points(
                actions.ring_points(center, 6),
                bond_orders=_benzene_bond_orders(first_order=1),
            )
            start = QPointF(center.x() - bond_length_px_for(self.canvas) * 2.0, center.y())
            mid = QPointF(start.x() - bond_length_px_for(self.canvas), start.y())
            chain_ids = actions.add_linear_chain([start, mid], ["C", "C"], [1])
            self.committer.add_bond(atom_ids[0], chain_ids[0])
            self.committer.add_bond_graphics(actions.latest_bond_id(1))

        actions.run_recorded_build(_build)

    def add_vinyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            p1 = QPointF(center.x() - bond_length_px_for(self.canvas), center.y())
            p2 = QPointF(center.x(), center.y())
            actions.add_linear_chain([p1, p2], ["C", "C"], [2])

        actions.run_recorded_build(_build)

    def add_allyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            points = [
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y()),
                QPointF(center.x() + step, center.y()),
            ]
            actions.add_linear_chain(points, ["C", "C", "C"], [2, 1])

        actions.run_recorded_build(_build)

    def add_carboxyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            carbon = QPointF(center.x(), center.y())
            self._add_branched_fragment(
                carbon,
                "C",
                [
                    (QPointF(center.x() + step, center.y() - step * 0.6), "O", 2),
                    (QPointF(center.x() + step, center.y() + step * 0.6), "O", 1),
                ],
            )

        actions.run_recorded_build(_build)

    def add_nitro(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            nitrogen = QPointF(center.x(), center.y())
            self._add_branched_fragment(
                nitrogen,
                "N",
                [
                    (QPointF(center.x() + step, center.y() - step * 0.6), "O", 2),
                    (QPointF(center.x() + step, center.y() + step * 0.6), "O", 2),
                ],
            )

        actions.run_recorded_build(_build)

    def add_sulfonyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            sulfur = QPointF(center.x(), center.y())
            self._add_branched_fragment(
                sulfur,
                "S",
                [
                    (QPointF(center.x() + step, center.y() - step * 0.7), "O", 2),
                    (QPointF(center.x() + step, center.y() + step * 0.7), "O", 2),
                ],
            )

        actions.run_recorded_build(_build)

    def add_carbonyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            carbon = QPointF(center.x(), center.y())
            oxygen = QPointF(center.x() + step, center.y())
            actions.add_linear_chain([carbon, oxygen], ["C", "O"], [2])

        actions.run_recorded_build(_build)

    def add_tbu(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            carbon = QPointF(center.x(), center.y())
            self._add_branched_fragment(
                carbon,
                "C",
                [
                    (QPointF(center.x() + step, center.y()), "C", 1),
                    (QPointF(center.x() - step, center.y()), "C", 1),
                    (QPointF(center.x(), center.y() - step), "C", 1),
                ],
            )

        actions.run_recorded_build(_build)

    def add_ipr(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            carbon = QPointF(center.x(), center.y())
            self._add_branched_fragment(
                carbon,
                "C",
                [
                    (QPointF(center.x() + step, center.y()), "C", 1),
                    (QPointF(center.x(), center.y() - step), "C", 1),
                ],
            )

        actions.run_recorded_build(_build)

    def add_me(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            actions.add_linear_chain([actions.viewport_center()], ["C"], [])

        actions.run_recorded_build(_build)

    def add_et(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            p1 = QPointF(center.x() - step / 2, center.y())
            p2 = QPointF(center.x() + step / 2, center.y())
            actions.add_linear_chain([p1, p2], ["C", "C"], [1])

        actions.run_recorded_build(_build)

    def add_peptide_2(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            points = [
                QPointF(center.x() - step * 2, center.y()),
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y()),
                QPointF(center.x() + step, center.y()),
                QPointF(center.x() + step * 2, center.y()),
                QPointF(center.x() + step * 3, center.y()),
            ]
            chain_ids = actions.add_linear_chain(
                points,
                ["N", "C", "C", "N", "C", "C"],
                [1, 1, 1, 1, 1],
            )
            oxygen_1 = QPointF(points[1].x(), points[1].y() - step * 0.8)
            oxygen_2 = QPointF(points[4].x(), points[4].y() - step * 0.8)
            oxygen_1_id = self.committer.add_atom("O", oxygen_1.x(), oxygen_1.y())
            oxygen_2_id = self.committer.add_atom("O", oxygen_2.x(), oxygen_2.y())
            self.committer.add_bond(chain_ids[1], oxygen_1_id, 2)
            self.committer.add_bond(chain_ids[4], oxygen_2_id, 2)
            self.committer.add_bond_graphics(actions.latest_bond_id(2))
            self.committer.add_bond_graphics(actions.latest_bond_id(1))
            self.committer.add_atom_label(oxygen_1_id, "O", record=False)
            self.committer.add_atom_label(oxygen_2_id, "O", record=False)

        actions.run_recorded_build(_build)

    def _add_branched_fragment(
        self,
        center: QPointF,
        center_element: str,
        branches: list[tuple[QPointF, str, int]],
    ) -> None:
        center_id = self.committer.add_atom(center_element, center.x(), center.y())
        if center_element != "C":
            self.committer.add_atom_label(center_id, center_element, record=False)
        for branch, element, order in branches:
            branch_id = self.committer.add_atom(element, branch.x(), branch.y())
            bond_id = self.committer.add_bond(center_id, branch_id, order)
            self.committer.add_bond_graphics(bond_id)
            if element != "C":
                self.committer.add_atom_label(branch_id, element, record=False)


def _benzene_bond_orders(*, first_order: int = 2) -> list[int]:
    return [order for _, _, order in alternating_ring_bond_specs(range(6), first_order=first_order)]


def _fused_heterocycle_bond_orders(ring_size: int, elements: list[str]) -> list[int] | None:
    if ring_size == 6:
        return _benzene_bond_orders()
    if ring_size != 5:
        return None
    normalized = _fused_heterocycle_elements(ring_size, elements)
    if normalized == ["C", "C", "N", "C", "C"]:
        return [1, 1, 1, 2, 1]
    return [1, 1, 2, 1, 1]


def _fused_heterocycle_elements(ring_size: int, elements: list[str]) -> list[str]:
    if ring_size < 3:
        return elements
    normalized = list(elements[:ring_size])
    if len(normalized) == ring_size and normalized[:2] == ["C", "C"]:
        return normalized
    return ["C", "C", *normalized[: ring_size - 2]]


__all__ = ["StructureFragmentBuildActions", "StructureFragmentBuildService"]
