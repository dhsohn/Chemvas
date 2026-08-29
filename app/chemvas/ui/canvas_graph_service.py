from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.ui.canvas_graph_state import (
    CanvasGraphState,
    graph_state_for,
)
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    atoms_for,
    bond_for_id,
    bonds_for,
)
from chemvas.ui.graph_algorithms import (
    adjacency_for_bonds,
    connected_components_for_nodes,
    reachable_component_without_edge,
    reachable_from,
)
from chemvas.ui.graph_index_operations import (
    add_bond_to_atom_index,
    add_neighbor_edge,
    bond_id_between_indexed_atoms,
    bond_sets_for_atom_ids,
    build_bond_adjacency_index,
    cached_bond_in_cycle,
    ensure_bond_index_entry,
    ensure_neighbor_entry,
    remove_bond_from_atom_index,
    remove_neighbor_edge,
)
from chemvas.ui.graph_index_operations import (
    bond_matches_atoms as graph_bond_matches_atoms,
)
from chemvas.ui.graph_index_operations import (
    first_matching_bond_id as graph_first_matching_bond_id,
)
from chemvas.ui.graph_rotation_policy import (
    axis_from_rotation_hint_policy,
    preferred_rotation_side_for_bond_policy,
)
from chemvas.ui.renderer_style_access import bond_length_px_for

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas_view import CanvasView


class CanvasGraphService:
    def __init__(
        self, canvas: CanvasView, graph_state: CanvasGraphState | None = None
    ) -> None:
        self.canvas = canvas
        self.graph = graph_state if graph_state is not None else graph_state_for(canvas)

    def ensure_atom_neighbors(self, atom_id: int) -> None:
        ensure_neighbor_entry(self.graph.atom_neighbors, atom_id)

    def ensure_atom_bond_ids(self, atom_id: int) -> None:
        ensure_bond_index_entry(self.graph.atom_bond_ids, atom_id)

    def add_bond_neighbors(self, a_id: int, b_id: int) -> None:
        add_neighbor_edge(self.graph.atom_neighbors, a_id, b_id)
        self.graph.bump_version()

    def remove_bond_neighbors(
        self, a_id: int, b_id: int, skip_bond_id: int | None = None
    ) -> None:
        if self.bond_id_between(a_id, b_id, skip_bond_id=skip_bond_id) is not None:
            return
        if remove_neighbor_edge(self.graph.atom_neighbors, a_id, b_id):
            self.graph.bump_version()

    def add_bond_index(self, bond_id: int, a_id: int, b_id: int) -> None:
        add_bond_to_atom_index(self.graph.atom_bond_ids, bond_id, a_id, b_id)

    def remove_bond_index(self, bond_id: int, a_id: int, b_id: int) -> None:
        remove_bond_from_atom_index(self.graph.atom_bond_ids, bond_id, a_id, b_id)

    def _ensure_indexed_bond(self, bond_id: int, a_id: int, b_id: int) -> None:
        changed = False
        bonds_a = self.graph.atom_bond_ids.setdefault(a_id, set())
        if bond_id not in bonds_a:
            bonds_a.add(bond_id)
            changed = True
        bonds_b = self.graph.atom_bond_ids.setdefault(b_id, set())
        if bond_id not in bonds_b:
            bonds_b.add(bond_id)
            changed = True

        neighbors_a = self.graph.atom_neighbors.setdefault(a_id, set())
        if b_id not in neighbors_a:
            neighbors_a.add(b_id)
            changed = True
        neighbors_b = self.graph.atom_neighbors.setdefault(b_id, set())
        if a_id not in neighbors_b:
            neighbors_b.add(a_id)
            changed = True

        if changed:
            self.graph.bump_version()

    @staticmethod
    def bond_matches_atoms(bond, a_id: int, b_id: int) -> bool:
        return graph_bond_matches_atoms(bond, a_id, b_id)

    @classmethod
    def first_matching_bond_id(
        cls,
        bonds,
        a_id: int,
        b_id: int,
        *,
        skip_bond_id: int | None = None,
    ) -> int | None:
        return graph_first_matching_bond_id(
            bonds,
            a_id,
            b_id,
            skip_bond_id=skip_bond_id,
        )

    def _indexed_bond_id_between(
        self,
        a_id: int,
        b_id: int,
        *,
        skip_bond_id: int | None = None,
        scan_index_misses: bool = False,
    ) -> int | None:
        bond_id = bond_id_between_indexed_atoms(
            self.graph.atom_bond_ids,
            bonds_for(self.canvas),
            a_id,
            b_id,
            bond_for_id=lambda bond_id: bond_for_id(self.canvas, bond_id),
            skip_bond_id=skip_bond_id,
            scan_index_misses=scan_index_misses,
        )
        if bond_id is not None:
            self._ensure_indexed_bond(bond_id, a_id, b_id)
        return bond_id

    def bond_id_between(
        self, a_id: int, b_id: int, skip_bond_id: int | None = None
    ) -> int | None:
        return self._indexed_bond_id_between(a_id, b_id, skip_bond_id=skip_bond_id)

    def bond_id_between_with_repair(self, a_id: int, b_id: int) -> int | None:
        """Lookup that scans and repairs after any indexed miss."""
        return self._indexed_bond_id_between(a_id, b_id, scan_index_misses=True)

    def bond_exists(self, a_id: int, b_id: int) -> bool:
        return self.bond_id_between(a_id, b_id) is not None

    def rebuild_bond_adjacency(self) -> None:
        self.graph.atom_neighbors, self.graph.atom_bond_ids = (
            build_bond_adjacency_index(
                atoms_for(self.canvas),
                bonds_for(self.canvas),
            )
        )
        self.graph.bump_version()
        self.graph.selection_component_cache = []

    def connected_components(self, atom_ids: set[int]) -> list[set[int]]:
        return connected_components_for_nodes(atom_ids, self.graph.atom_neighbors)

    def component_without_bond(self, start_atom_id: int, skip_bond_id: int) -> set[int]:
        skip_bond = bond_for_id(self.canvas, skip_bond_id)
        blocked_edge = None
        if skip_bond is not None:
            shared = self.graph.atom_bond_ids.get(
                skip_bond.a, set()
            ) & self.graph.atom_bond_ids.get(skip_bond.b, set())
            has_alt_between = any(bond_id != skip_bond_id for bond_id in shared)
            if not has_alt_between:
                blocked_edge = (skip_bond.a, skip_bond.b)
        return reachable_component_without_edge(
            start_atom_id,
            self.graph.atom_neighbors,
            blocked_edge=blocked_edge,
        )

    def bond_in_cycle(self, bond_id: int) -> bool:
        return cached_bond_in_cycle(
            self.graph,
            bond_id,
            lambda candidate_id: bond_for_id(self.canvas, candidate_id),
        )

    def bond_is_rotatable(self, bond_id: int) -> bool:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None or bond.order != 1:
            return False
        return not self.bond_in_cycle(bond_id)

    def bond_component_atoms(self, bond_id: int) -> set[int] | None:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return None
        comp_a = self.component_without_bond(bond.a, bond_id)
        comp_b = self.component_without_bond(bond.b, bond_id)
        return comp_a | comp_b

    def preferred_rotation_side_for_bond(
        self,
        bond_id: int,
        selected_atom_ids: set[int],
        press_pos: QPointF | None = None,
        allow_fallback: bool = True,
    ) -> set[int] | None:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return None
        comp_a = self.component_without_bond(bond.a, bond_id)
        comp_b = self.component_without_bond(bond.b, bond_id)
        atom_a = atom_for_id(self.canvas, bond.a)
        atom_b = atom_for_id(self.canvas, bond.b)
        return preferred_rotation_side_for_bond_policy(
            bond,
            comp_a,
            comp_b,
            selected_atom_ids,
            atom_a=atom_a,
            atom_b=atom_b,
            press_pos=press_pos,
            bond_length_px=bond_length_px_for(self.canvas),
            allow_fallback=allow_fallback,
        )

    def axis_from_rotation_hint(
        self,
        axis_hint: int,
        rotation_atom_ids: set[int],
        press_pos: QPointF | None = None,
    ) -> tuple[int, set[int]] | None:
        return axis_from_rotation_hint_policy(
            axis_hint,
            rotation_atom_ids,
            bond_is_rotatable=self.bond_is_rotatable,
            bond_component_atoms=self.bond_component_atoms,
            preferred_rotation_side_for_bond=self.preferred_rotation_side_for_bond,
            press_pos=press_pos,
        )

    def bond_sets_for_atoms(self, atom_ids: set[int]) -> tuple[set[int], set[int]]:
        return bond_sets_for_atom_ids(
            atom_ids,
            self.graph.atom_bond_ids,
            bonds_for(self.canvas),
            bond_for_id=lambda bond_id: bond_for_id(self.canvas, bond_id),
        )

    def expand_connected_atoms(self, atom_ids: set[int]) -> set[int]:
        return reachable_from(atom_ids, adjacency_for_bonds(bonds_for(self.canvas)))


__all__ = ["CanvasGraphService"]
