from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QPointF

from ui.renderer_style_access import bond_length_px_for
from ui.structure_build_committer import StructureBuildCommitter
from ui.structure_growth_logic import (
    crown_ether_elements,
    fused_benzene_centers,
)


@dataclass(frozen=True, slots=True)
class StructureFragmentBuildActions:
    viewport_center: Callable[[], QPointF]
    regular_ring_radius: Callable[[int], float]
    ring_points: Callable
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

    def add_hetero_ring_template(self, n: int, elements: list[str], actions: StructureFragmentBuildActions) -> None:
        center = actions.viewport_center()
        radius = actions.regular_ring_radius(n)
        actions.add_ring_from_points(actions.ring_points(center, n, radius=radius), elements=elements)

    def add_fused_benzenes(self, count: int, mode: str, actions: StructureFragmentBuildActions) -> None:
        center = actions.viewport_center()
        step = bond_length_px_for(self.canvas) * 1.5
        merge: list = []
        for ring_center in fused_benzene_centers(center, step, count, mode):
            actions.add_ring_from_points(actions.ring_points(ring_center, 6), merge=merge)

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
        merge: list[tuple[int, float, float]] = []
        actions.add_ring_from_points(actions.ring_points(center, 6), merge=merge)
        other_center = QPointF(
            center.x() + bond_length_px_for(self.canvas) * x_scale,
            center.y() + bond_length_px_for(self.canvas) * y_scale,
        )
        actions.add_ring_from_points(
            actions.ring_points(other_center, ring_size),
            elements=elements,
            merge=merge,
        )

    def add_phenyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            atom_ids = actions.add_ring_from_points(actions.ring_points(center, 6))
            attach = QPointF(center.x() - bond_length_px_for(self.canvas) * 2.0, center.y())
            attach_id = self.committer.add_atom("C", attach.x(), attach.y())
            self.committer.add_bond(atom_ids[0], attach_id)
            self.committer.add_bond_graphics(actions.latest_bond_id(1))

        actions.run_recorded_build(_build)

    def add_benzyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            atom_ids = actions.add_ring_from_points(actions.ring_points(center, 6))
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
            oxygen_upper = QPointF(center.x() + step, center.y() - step * 0.6)
            oxygen_lower = QPointF(center.x() + step, center.y() + step * 0.6)
            actions.add_linear_chain([carbon, oxygen_upper], ["C", "O"], [2])
            actions.add_linear_chain([carbon, oxygen_lower], ["C", "O"], [1])

        actions.run_recorded_build(_build)

    def add_nitro(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            nitrogen = QPointF(center.x(), center.y())
            oxygen_upper = QPointF(center.x() + step, center.y() - step * 0.6)
            oxygen_lower = QPointF(center.x() + step, center.y() + step * 0.6)
            actions.add_linear_chain([nitrogen, oxygen_upper], ["N", "O"], [2])
            actions.add_linear_chain([nitrogen, oxygen_lower], ["N", "O"], [2])

        actions.run_recorded_build(_build)

    def add_sulfonyl(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            sulfur = QPointF(center.x(), center.y())
            oxygen_upper = QPointF(center.x() + step, center.y() - step * 0.7)
            oxygen_lower = QPointF(center.x() + step, center.y() + step * 0.7)
            actions.add_linear_chain([sulfur, oxygen_upper], ["S", "O"], [2])
            actions.add_linear_chain([sulfur, oxygen_lower], ["S", "O"], [2])

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
            branches = [
                QPointF(center.x() + step, center.y()),
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y() - step),
            ]
            for branch in branches:
                actions.add_linear_chain([carbon, branch], ["C", "C"], [1])

        actions.run_recorded_build(_build)

    def add_ipr(self, actions: StructureFragmentBuildActions) -> None:
        def _build() -> None:
            center = actions.viewport_center()
            step = bond_length_px_for(self.canvas)
            carbon = QPointF(center.x(), center.y())
            branch_right = QPointF(center.x() + step, center.y())
            branch_up = QPointF(center.x(), center.y() - step)
            actions.add_linear_chain([carbon, branch_right], ["C", "C"], [1])
            actions.add_linear_chain([carbon, branch_up], ["C", "C"], [1])

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


__all__ = ["StructureFragmentBuildActions", "StructureFragmentBuildService"]
