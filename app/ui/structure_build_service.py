from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.canvas_model_access import (
    atom_for_id,
    atoms_for,
    bond_count_for,
    bond_for_id,
    bonds_for,
)
from ui.canvas_ring_fill_scene_access import create_ring_fill_item_for
from ui.input_view_access import viewport_center_scene_pos_for
from ui.structure_benzene_build_service import StructureBenzeneBuildService
from ui.structure_bond_build_service import StructureBondBuildService
from ui.structure_build_committer import StructureBuildCommitter
from ui.structure_fragment_build_service import (
    StructureFragmentBuildActions,
    StructureFragmentBuildService,
)
from ui.structure_geometry_access import (
    atom_point_for,
    cyclohexane_boat_points_for,
    cyclohexane_chair_points_for,
    default_bond_endpoint_for,
    regular_ring_points_for_atom_for,
    regular_ring_points_for_bond_for,
    regular_ring_radius_for,
    ring_points_for,
    sprout_bond_endpoint_for,
    template_points_for_bond_for,
)
from ui.structure_growth_build_actions import structure_growth_build_actions_for
from ui.structure_growth_build_service import StructureGrowthBuildService
from ui.structure_growth_logic import (
    resolve_bond_placement_context,
)
from ui.structure_template_build_service import StructureTemplateBuildService

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class StructureBuildService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        hit_testing_service,
        move_controller,
        graph_service,
    ) -> None:
        self.canvas = canvas
        self.graph_service = graph_service
        self.committer = StructureBuildCommitter(canvas)
        self.bond_builder = StructureBondBuildService(
            canvas,
            self.committer,
            hit_testing_service=hit_testing_service,
            move_controller=move_controller,
            graph_service=self.graph_service,
        )
        self.benzene_builder = StructureBenzeneBuildService(canvas, self.committer)
        self.fragment_builder = StructureFragmentBuildService(canvas, self.committer)
        self.growth_builder = StructureGrowthBuildService(structure_growth_build_actions_for(self))
        self.template_builder = StructureTemplateBuildService(
            self.fragment_builder,
            actions_factory=self._fragment_actions,
        )

    def viewport_center(self) -> QPointF:
        return viewport_center_scene_pos_for(self.canvas)

    def regular_ring_radius(self, n: int) -> float:
        return regular_ring_radius_for(self.canvas, n)

    def ring_points(self, center, n: int, radius: float | None = None):
        return ring_points_for(self.canvas, center, n, radius=radius)

    def cyclohexane_chair_points(self, center):
        return cyclohexane_chair_points_for(self.canvas, center)

    def cyclohexane_boat_points(self, center):
        return cyclohexane_boat_points_for(self.canvas, center)

    def atom_point(self, atom_id: int):
        return atom_point_for(self.canvas, atom_id)

    def sprout_bond_endpoint(self, atom_id: int, *, cyclic: bool = False):
        return sprout_bond_endpoint_for(self.canvas, atom_id, cyclic=cyclic)

    def default_bond_endpoint(self, start, start_atom_id: int | None):
        return default_bond_endpoint_for(self.canvas, start, start_atom_id)

    @property
    def atoms(self):
        return atoms_for(self.canvas)

    @property
    def bonds(self):
        return bonds_for(self.canvas)

    @property
    def bond_count(self) -> int:
        return bond_count_for(self.canvas)

    def latest_bond_id(self, offset: int = 1) -> int:
        return self.bond_count - offset

    def has_atom(self, atom_id: int | None) -> bool:
        return atom_for_id(self.canvas, atom_id) is not None

    def bond(self, bond_id: int | None):
        return bond_for_id(self.canvas, bond_id)

    def bond_placement_context(self, bond_id: int):
        return resolve_bond_placement_context(
            bond_id,
            bonds=self.bonds,
            atoms=self.atoms,
        )

    def regular_ring_points_for_atom(self, n: int, atom_id: int):
        return regular_ring_points_for_atom_for(self.canvas, n, atom_id)

    def regular_ring_points_for_bond(self, n: int, bond_id: int, midpoint):
        return regular_ring_points_for_bond_for(self.canvas, n, bond_id, midpoint)

    def template_points_for_bond(self, points_local, bond_id: int, midpoint):
        return template_points_for_bond_for(self.canvas, points_local, bond_id, midpoint)

    def bond_exists(self, a_id: int, b_id: int) -> bool:
        return self.graph_service.bond_exists(a_id, b_id)

    def create_ring_fill_item(self, points, atom_ids):
        return create_ring_fill_item_for(self.canvas, points, atom_ids)

    def ensure_ring_fills_for_model(self) -> list:
        """Make sure every ring in the model has a fill polygon so it can be
        selected and colored. Existing fills (saved or freshly built) are left
        untouched; new fills are invisible (default alpha) until colored."""
        return self.committer.ensure_ring_fills_for_model()

    def run_recorded_build(
        self,
        action: Callable[[], list | None],
        *,
        before_smiles_input: str | None = None,
    ) -> list:
        snapshot = self.committer.begin_recorded_change(before_smiles_input=before_smiles_input)
        added_scene_items = action()
        if added_scene_items is None:
            self.committer.abort_recorded_change(snapshot)
            return []
        self.committer.record_additions(snapshot, added_scene_items=added_scene_items)
        return added_scene_items

    def _run_fragment_recorded_build(
        self,
        action: Callable[[], list | None],
        *,
        before_smiles_input: str | None = None,
    ) -> list:
        def _action() -> list | None:
            added_scene_items = action()
            return [] if added_scene_items is None else added_scene_items

        return self.run_recorded_build(_action, before_smiles_input=before_smiles_input)

    def _run_recorded_additions_action(
        self,
        action: Callable[[], bool],
        *,
        before_smiles_input: str | None = None,
    ) -> bool:
        snapshot = self.committer.begin_recorded_change(before_smiles_input=before_smiles_input)
        if not action():
            self.committer.abort_recorded_change(snapshot)
            return False
        self.committer.record_additions(snapshot)
        return True

    def _fragment_actions(self) -> StructureFragmentBuildActions:
        return StructureFragmentBuildActions(
            viewport_center=self.viewport_center,
            regular_ring_radius=self.regular_ring_radius,
            ring_points=self.ring_points,
            cyclohexane_chair_points=self.cyclohexane_chair_points,
            cyclohexane_boat_points=self.cyclohexane_boat_points,
            add_ring_from_points=self.add_ring_from_points,
            add_linear_chain=self.add_linear_chain,
            run_recorded_build=self._run_fragment_recorded_build,
            latest_bond_id=self.latest_bond_id,
        )

    def sprout_bond_from_atom(
        self,
        atom_id: int,
        *,
        style: str,
        order: int,
        cyclic: bool = False,
    ) -> tuple[int, int] | None:
        return self.growth_builder.sprout_bond_from_atom(atom_id, style=style, order=order, cyclic=cyclic)

    def sprout_benzene_from_atom(self, atom_id: int) -> object | None:
        return self.growth_builder.sprout_benzene_from_atom(atom_id)

    def sprout_acetyl_from_atom(self, atom_id: int) -> None:
        self.growth_builder.sprout_acetyl_from_atom(atom_id)

    def sprout_regular_ring_from_atom(self, atom_id: int, n: int) -> None:
        self.growth_builder.sprout_regular_ring_from_atom(atom_id, n)

    def fuse_regular_ring_to_bond(self, bond_id: int, n: int) -> None:
        self.growth_builder.fuse_regular_ring_to_bond(bond_id, n)

    def fuse_chair_to_bond(self, bond_id: int, mirrored: bool = False) -> None:
        self.growth_builder.fuse_chair_to_bond(bond_id, mirrored=mirrored)

    def fuse_benzene_to_bond(self, bond_id: int) -> object | None:
        return self.growth_builder.fuse_benzene_to_bond(bond_id)

    def add_bond_between_points(
        self,
        start: QPointF,
        end: QPointF,
        style: str,
        order: int,
    ) -> tuple[int, int] | None:
        return self.bond_builder.add_bond_between_points(start, end, style, order)

    def benzene_ring_points(
        self,
        center: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        return self.benzene_builder.benzene_ring_points(
            center,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
            regular_ring_points_for_bond=self.regular_ring_points_for_bond,
            regular_ring_points_for_atom=self.regular_ring_points_for_atom,
        )

    def add_benzene_ring(
        self,
        center: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
        *,
        before_smiles_input: str | None = None,
    ) -> object | None:
        return self.benzene_builder.add_benzene_ring(
            center,
            attach_atom_id,
            attach_bond_id,
            before_smiles_input=before_smiles_input,
            benzene_ring_points=self.benzene_ring_points,
            add_atom_with_merge=self.add_atom_with_merge,
            bond_exists=self.bond_exists,
            create_ring_fill_item=self.create_ring_fill_item,
            run_recorded_build=self.run_recorded_build,
        )

    def add_ring_from_points(
        self,
        points,
        elements: list[str] | None = None,
        merge: list | None = None,
    ) -> list[int]:
        return self.committer.add_ring_from_points(points, elements=elements, merge=merge)

    def add_atom_with_merge(self, point: QPointF, element: str, merge: list) -> int:
        return self.committer.add_atom_with_merge(point, element, merge)

    def add_linear_chain(self, points: list[QPointF], elements: list[str], bonds: list[int]):
        return self.committer.add_linear_chain(points, elements, bonds)

    def render_model(self) -> None:
        self.committer.render_model()


__all__ = ["StructureBuildService"]
