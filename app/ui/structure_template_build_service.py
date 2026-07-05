from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ui.structure_fragment_build_service import (
    StructureFragmentBuildActions,
)


class StructureTemplateBuildService:
    def __init__(
        self,
        fragment_builder: Any,
        *,
        actions_factory: Callable[[], StructureFragmentBuildActions],
    ) -> None:
        self.fragment_builder = fragment_builder
        self.actions_factory = actions_factory

    def actions(self) -> StructureFragmentBuildActions:
        return self.actions_factory()

    def add_regular_ring_template(self, n: int) -> None:
        self.fragment_builder.add_regular_ring_template(n, self.actions())

    def add_hetero_ring_template(self, n: int, elements: list[str], bond_orders: list[int] | None = None) -> None:
        self.fragment_builder.add_hetero_ring_template(n, elements, self.actions(), bond_orders=bond_orders)

    def add_fused_benzenes(self, count: int, mode: str = "linear") -> None:
        self.fragment_builder.add_fused_benzenes(count, mode, self.actions())

    def add_crown_ether(self, atoms: int, oxygens: int) -> None:
        self.fragment_builder.add_crown_ether(atoms, oxygens, self.actions())

    def add_cyclohexane_chair(self) -> None:
        self.fragment_builder.add_cyclohexane_chair(self.actions())

    def add_cyclohexane_boat(self) -> None:
        self.fragment_builder.add_cyclohexane_boat(self.actions())

    def add_indole(self) -> None:
        self._run_recorded_fused_heterocycle_template(
            ring_size=5,
            elements=["C", "C", "N", "C", "C"],
            x_scale=1.1,
            y_scale=0.6,
        )

    def add_quinoline(self) -> None:
        self._run_recorded_fused_heterocycle_template(
            ring_size=6,
            elements=["C", "C", "N", "C", "C", "C"],
            x_scale=1.5,
        )

    def add_isoquinoline(self) -> None:
        self._run_recorded_fused_heterocycle_template(
            ring_size=6,
            elements=["C", "C", "C", "C", "N", "C"],
            x_scale=1.5,
        )

    def add_benzimidazole(self) -> None:
        self._run_recorded_fused_heterocycle_template(
            ring_size=5,
            elements=["C", "C", "N", "C", "N"],
            x_scale=1.1,
            y_scale=0.6,
        )

    def _run_recorded_fused_heterocycle_template(
        self,
        *,
        ring_size: int,
        elements: list[str],
        x_scale: float,
        y_scale: float = 0.0,
    ) -> None:
        actions = self.actions()
        actions.run_recorded_build(
            lambda: self.add_fused_heterocycle_template(
                ring_size=ring_size,
                elements=elements,
                x_scale=x_scale,
                y_scale=y_scale,
                actions=actions,
            )
        )

    def add_fused_heterocycle_template(
        self,
        *,
        ring_size: int,
        elements: list[str],
        x_scale: float,
        y_scale: float = 0.0,
        actions: StructureFragmentBuildActions | None = None,
    ) -> None:
        self.fragment_builder.add_fused_heterocycle_template(
            ring_size=ring_size,
            elements=elements,
            x_scale=x_scale,
            y_scale=y_scale,
            actions=actions or self.actions(),
        )

    def add_phenyl(self) -> None:
        self.fragment_builder.add_phenyl(self.actions())

    def add_benzyl(self) -> None:
        self.fragment_builder.add_benzyl(self.actions())

    def add_vinyl(self) -> None:
        self.fragment_builder.add_vinyl(self.actions())

    def add_allyl(self) -> None:
        self.fragment_builder.add_allyl(self.actions())

    def add_carboxyl(self) -> None:
        self.fragment_builder.add_carboxyl(self.actions())

    def add_nitro(self) -> None:
        self.fragment_builder.add_nitro(self.actions())

    def add_sulfonyl(self) -> None:
        self.fragment_builder.add_sulfonyl(self.actions())

    def add_carbonyl(self) -> None:
        self.fragment_builder.add_carbonyl(self.actions())

    def add_tbu(self) -> None:
        self.fragment_builder.add_tbu(self.actions())

    def add_ipr(self) -> None:
        self.fragment_builder.add_ipr(self.actions())

    def add_me(self) -> None:
        self.fragment_builder.add_me(self.actions())

    def add_et(self) -> None:
        self.fragment_builder.add_et(self.actions())

    def add_peptide_2(self) -> None:
        self.fragment_builder.add_peptide_2(self.actions())


__all__ = ["StructureTemplateBuildService"]
