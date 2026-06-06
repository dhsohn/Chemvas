from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPointF

from ui.canvas_model_access import atoms_for, bond_count_for, bonds_for
from ui.canvas_ring_fill_scene_access import create_ring_fill_item_for
from ui.canvas_scene_items_state import ring_items_for
from ui.renderer_style_access import bond_length_px_for
from ui.scene_item_access import attach_scene_item
from ui.structure_benzene_logic import plan_benzene_ring_points
from ui.structure_build_committer import StructureBuildCommitter
from ui.structure_geometry_logic import compute_free_benzene_ring_points
from ui.structure_growth_logic import alternating_ring_bond_specs


class StructureBenzeneBuildService:
    def __init__(self, canvas, committer: StructureBuildCommitter) -> None:
        self.canvas = canvas
        self.committer = committer

    def benzene_ring_points(
        self,
        center: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
        *,
        regular_ring_points_for_bond: Callable,
        regular_ring_points_for_atom: Callable,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        return plan_benzene_ring_points(
            center,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
            bonds=bonds_for(self.canvas),
            atoms=atoms_for(self.canvas),
            ring_items=ring_items_for(self.canvas),
            bond_length=bond_length_px_for(self.canvas),
            regular_ring_points_for_bond=regular_ring_points_for_bond,
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=compute_free_benzene_ring_points,
        )

    def add_benzene_ring(
        self,
        center: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
        *,
        before_smiles_input: str | None = None,
        benzene_ring_points: Callable,
        add_atom_with_merge: Callable,
        bond_exists: Callable[[int, int], bool],
        create_ring_fill_item: Callable | None = None,
        run_recorded_build: Callable,
    ) -> object | None:
        built_ring_item = None

        def _build():
            nonlocal built_ring_item
            result = benzene_ring_points(center, attach_atom_id, attach_bond_id)
            if result is None:
                return []
            points, merge = result

            atom_ids: list[int] = []
            for point in points:
                atom_ids.append(add_atom_with_merge(point, "C", merge))

            bonds_start = bond_count_for(self.canvas)
            for a_id, b_id, order in alternating_ring_bond_specs(atom_ids):
                if bond_exists(a_id, b_id):
                    continue
                self.committer.add_bond(a_id, b_id, order)

            factory = create_ring_fill_item or self.create_ring_fill_item
            built_ring_item = factory(points, atom_ids)
            attach_scene_item(self.canvas, built_ring_item)

            self.committer.add_bond_graphics_range(bonds_start)
            return [built_ring_item]

        run_recorded_build(_build, before_smiles_input=before_smiles_input)
        return built_ring_item

    def create_ring_fill_item(self, points, atom_ids):
        return create_ring_fill_item_for(self.canvas, points, atom_ids)


__all__ = ["StructureBenzeneBuildService"]
