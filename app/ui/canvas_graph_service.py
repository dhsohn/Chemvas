from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.canvas_graph_state import CanvasGraphState, CanvasGraphStateAdapter, graph_state_for

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class CanvasGraphService:
    def __init__(self, canvas: CanvasView, graph_state: CanvasGraphState | CanvasGraphStateAdapter | None = None) -> None:
        self.canvas = canvas
        self.graph = graph_state if graph_state is not None else graph_state_for(canvas)

    def ensure_atom_neighbors(self, atom_id: int) -> None:
        if atom_id not in self.graph.atom_neighbors:
            self.graph.atom_neighbors[atom_id] = set()

    def ensure_atom_bond_ids(self, atom_id: int) -> None:
        if atom_id not in self.graph.atom_bond_ids:
            self.graph.atom_bond_ids[atom_id] = set()

    def add_bond_neighbors(self, a_id: int, b_id: int) -> None:
        self.graph.atom_neighbors.setdefault(a_id, set()).add(b_id)
        self.graph.atom_neighbors.setdefault(b_id, set()).add(a_id)
        self.graph.bump_version()

    def remove_bond_neighbors(self, a_id: int, b_id: int, skip_bond_id: int | None = None) -> None:
        if self.canvas._bond_id_between(a_id, b_id, skip_bond_id=skip_bond_id) is not None:
            return
        changed = False
        neighbors_a = self.graph.atom_neighbors.get(a_id)
        if neighbors_a is not None and b_id in neighbors_a:
            neighbors_a.remove(b_id)
            changed = True
        neighbors_b = self.graph.atom_neighbors.get(b_id)
        if neighbors_b is not None and a_id in neighbors_b:
            neighbors_b.remove(a_id)
            changed = True
        if changed:
            self.graph.bump_version()

    def add_bond_index(self, bond_id: int, a_id: int, b_id: int) -> None:
        self.graph.atom_bond_ids.setdefault(a_id, set()).add(bond_id)
        self.graph.atom_bond_ids.setdefault(b_id, set()).add(bond_id)

    def remove_bond_index(self, bond_id: int, a_id: int, b_id: int) -> None:
        bonds_a = self.graph.atom_bond_ids.get(a_id)
        if bonds_a is not None and bond_id in bonds_a:
            bonds_a.remove(bond_id)
        bonds_b = self.graph.atom_bond_ids.get(b_id)
        if bonds_b is not None and bond_id in bonds_b:
            bonds_b.remove(bond_id)

    def rebuild_bond_adjacency(self) -> None:
        self.graph.atom_neighbors = {atom_id: set() for atom_id in self.canvas.model.atoms}
        self.graph.atom_bond_ids = {atom_id: set() for atom_id in self.canvas.model.atoms}
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            self.graph.atom_neighbors.setdefault(bond.a, set()).add(bond.b)
            self.graph.atom_neighbors.setdefault(bond.b, set()).add(bond.a)
            self.graph.atom_bond_ids.setdefault(bond.a, set()).add(bond_id)
            self.graph.atom_bond_ids.setdefault(bond.b, set()).add(bond_id)
        self.graph.bump_version()
        self.graph.selection_component_cache = []

    def connected_components(self, atom_ids: set[int]) -> list[set[int]]:
        if not atom_ids:
            return []
        remaining = set(atom_ids)
        components = []
        while remaining:
            start = remaining.pop()
            stack = [start]
            comp = {start}
            while stack:
                current = stack.pop()
                for neighbor in self.graph.atom_neighbors.get(current, ()):
                    if neighbor not in atom_ids:
                        continue
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        comp.add(neighbor)
                        stack.append(neighbor)
            components.append(comp)
        return components

    def component_without_bond(self, start_atom_id: int, skip_bond_id: int) -> set[int]:
        skip_bond = None
        skip_a = None
        skip_b = None
        has_alt_between = False
        if 0 <= skip_bond_id < len(self.canvas.model.bonds):
            skip_bond = self.canvas.model.bonds[skip_bond_id]
        if skip_bond is not None:
            skip_a = skip_bond.a
            skip_b = skip_bond.b
            shared = self.graph.atom_bond_ids.get(skip_a, set()) & self.graph.atom_bond_ids.get(skip_b, set())
            has_alt_between = any(bond_id != skip_bond_id for bond_id in shared)
        visited = {start_atom_id}
        stack = [start_atom_id]
        while stack:
            current = stack.pop()
            for neighbor in self.graph.atom_neighbors.get(current, ()):
                if (
                    skip_bond is not None
                    and not has_alt_between
                    and (
                        (current == skip_a and neighbor == skip_b)
                        or (current == skip_b and neighbor == skip_a)
                    )
                ):
                    continue
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)
        return visited

    def bond_in_cycle(self, bond_id: int) -> bool:
        cached = self.graph.bond_cycle_cache.get(bond_id)
        if cached is not None and cached[0] == self.graph.graph_version:
            return cached[1]
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            self.graph.bond_cycle_cache[bond_id] = (self.graph.graph_version, False)
            return False
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            self.graph.bond_cycle_cache[bond_id] = (self.graph.graph_version, False)
            return False
        start = bond.a
        target = bond.b
        shared = self.graph.atom_bond_ids.get(start, set()) & self.graph.atom_bond_ids.get(target, set())
        has_alt_between = any(other_id != bond_id for other_id in shared)
        visited = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in self.graph.atom_neighbors.get(current, ()):
                if (
                    not has_alt_between
                    and (
                        (current == start and neighbor == target)
                        or (current == target and neighbor == start)
                    )
                ):
                    continue
                if neighbor in visited:
                    continue
                if neighbor == target:
                    self.graph.bond_cycle_cache[bond_id] = (self.graph.graph_version, True)
                    return True
                visited.add(neighbor)
                stack.append(neighbor)
        self.graph.bond_cycle_cache[bond_id] = (self.graph.graph_version, False)
        return False

    def bond_is_rotatable(self, bond_id: int) -> bool:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return False
        bond = self.canvas.model.bonds[bond_id]
        if bond is None or bond.order != 1:
            return False
        if self.bond_in_cycle(bond_id):
            return False
        return True

    def bond_component_atoms(self, bond_id: int) -> set[int] | None:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return None
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return None
        comp_a = self.component_without_bond(bond.a, bond_id)
        comp_b = self.component_without_bond(bond.b, bond_id)
        return comp_a | comp_b

    def rotation_side_for_bond(
        self,
        bond_id: int,
        selected_atom_ids: set[int],
        allow_fallback: bool,
    ) -> set[int] | None:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return None
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return None
        comp_a = self.component_without_bond(bond.a, bond_id)
        comp_b = self.component_without_bond(bond.b, bond_id)
        effective_selected = set(selected_atom_ids) - {bond.a, bond.b}
        selected_in_a = effective_selected & comp_a
        selected_in_b = effective_selected & comp_b
        if selected_in_a and not selected_in_b:
            return comp_a
        if selected_in_b and not selected_in_a:
            return comp_b
        if not selected_in_a and not selected_in_b:
            a_selected = bond.a in selected_atom_ids
            b_selected = bond.b in selected_atom_ids
            if a_selected ^ b_selected:
                return comp_a if a_selected else comp_b
        if allow_fallback:
            count_a = len(selected_in_a)
            count_b = len(selected_in_b)
            if count_a != count_b:
                return comp_a if count_a > count_b else comp_b
            size_a = max(0, len(comp_a) - 1)
            size_b = max(0, len(comp_b) - 1)
            if size_a != size_b:
                return comp_a if size_a > size_b else comp_b
            return comp_a if len(comp_a) >= len(comp_b) else comp_b
        return None

    def preferred_rotation_side_for_bond(
        self,
        bond_id: int,
        selected_atom_ids: set[int],
        press_pos: QPointF | None = None,
        allow_fallback: bool = True,
    ) -> set[int] | None:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return None
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return None
        comp_a = self.component_without_bond(bond.a, bond_id)
        comp_b = self.component_without_bond(bond.b, bond_id)
        component = comp_a | comp_b
        selected_in_component = set(selected_atom_ids) & component
        is_partial_selection = 0 < len(selected_in_component) < len(component)
        effective_selected = selected_in_component - {bond.a, bond.b}
        selected_in_a = effective_selected & comp_a
        selected_in_b = effective_selected & comp_b
        overlap_a = selected_in_component & comp_a
        overlap_b = selected_in_component & comp_b
        atom_a = self.canvas.model.atoms.get(bond.a)
        atom_b = self.canvas.model.atoms.get(bond.b)
        dist_a = None
        dist_b = None
        if is_partial_selection:
            if selected_in_a and not selected_in_b:
                return comp_a
            if selected_in_b and not selected_in_a:
                return comp_b
            if overlap_a and not overlap_b:
                return comp_a
            if overlap_b and not overlap_a:
                return comp_b
            coverage_a = len(overlap_a) / max(1, len(comp_a))
            coverage_b = len(overlap_b) / max(1, len(comp_b))
            if abs(coverage_a - coverage_b) > 1e-9:
                return comp_a if coverage_a > coverage_b else comp_b
            if len(selected_in_a) != len(selected_in_b):
                return comp_a if len(selected_in_a) > len(selected_in_b) else comp_b
            if len(overlap_a) != len(overlap_b):
                return comp_a if len(overlap_a) > len(overlap_b) else comp_b
        elif not selected_in_a and not selected_in_b:
            a_selected = bond.a in selected_atom_ids
            b_selected = bond.b in selected_atom_ids
            if a_selected ^ b_selected:
                return comp_a if a_selected else comp_b
        if press_pos is not None and atom_a is not None and atom_b is not None:
            dist_a = math.hypot(press_pos.x() - atom_a.x, press_pos.y() - atom_a.y)
            dist_b = math.hypot(press_pos.x() - atom_b.x, press_pos.y() - atom_b.y)
            tol = self.canvas.renderer.style.bond_length_px * 0.05
            if abs(dist_a - dist_b) > tol:
                return comp_a if dist_a < dist_b else comp_b
        if not allow_fallback:
            return None
        size_a = max(0, len(comp_a) - 1)
        size_b = max(0, len(comp_b) - 1)
        if size_a != size_b:
            return comp_a if size_a < size_b else comp_b
        if dist_a is not None and dist_b is not None:
            return comp_a if dist_a <= dist_b else comp_b
        return comp_a if bond.a <= bond.b else comp_b

    def rotatable_axis_from_selection(
        self,
        selected_atom_ids: set[int],
        selected_bond_ids: set[int],
    ) -> tuple[int, set[int]] | None:
        if self.graph.rotation_axis_cache_version != self.graph.graph_version:
            self.graph.rotation_axis_cache.clear()
            self.graph.rotation_axis_cache_version = self.graph.graph_version
        cache_key = (
            frozenset(selected_atom_ids),
            frozenset(selected_bond_ids),
            self.graph.graph_version,
        )
        if cache_key in self.graph.rotation_axis_cache:
            return self.graph.rotation_axis_cache[cache_key]

        def _store(axis: tuple[int, set[int]] | None) -> tuple[int, set[int]] | None:
            self.graph.rotation_axis_cache[cache_key] = axis
            return axis

        explicit_atoms = set(selected_atom_ids)
        bond_atoms: set[int] = set()
        selected_bonds: set[int] = set()
        for bond_id in selected_bond_ids:
            if not (0 <= bond_id < len(self.canvas.model.bonds)):
                continue
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                continue
            selected_bonds.add(bond_id)
            bond_atoms.add(bond.a)
            bond_atoms.add(bond.b)
        atoms_for_boundary = explicit_atoms | bond_atoms
        if selected_bonds and len(selected_bonds) == 1:
            bond_id = next(iter(selected_bonds))
            if self.bond_is_rotatable(bond_id):
                rotating = self.preferred_rotation_side_for_bond(
                    bond_id,
                    atoms_for_boundary,
                    allow_fallback=True,
                )
                if rotating is not None:
                    return _store((bond_id, rotating))
        if not explicit_atoms and len(selected_bonds) > 1:
            selected_degree: dict[int, int] = {}
            for bond_id in selected_bonds:
                bond = self.canvas.model.bonds[bond_id]
                selected_degree[bond.a] = selected_degree.get(bond.a, 0) + 1
                selected_degree[bond.b] = selected_degree.get(bond.b, 0) + 1
            has_unselected_bond: dict[int, bool] = {}
            for other_id, other in enumerate(self.canvas.model.bonds):
                if other is None or other_id in selected_bonds:
                    continue
                has_unselected_bond[other.a] = True
                has_unselected_bond[other.b] = True
            candidates = []
            for bond_id in selected_bonds:
                bond = self.canvas.model.bonds[bond_id]
                a_leaf = selected_degree.get(bond.a, 0) == 1 and has_unselected_bond.get(bond.a, False)
                b_leaf = selected_degree.get(bond.b, 0) == 1 and has_unselected_bond.get(bond.b, False)
                if a_leaf ^ b_leaf:
                    candidates.append(bond_id)
            if len(candidates) == 1:
                bond_id = candidates[0]
                if self.bond_is_rotatable(bond_id):
                    rotating = self.rotation_side_for_bond(
                        bond_id,
                        bond_atoms,
                        allow_fallback=True,
                    )
                    if rotating is not None:
                        return _store((bond_id, rotating))
                return _store(None)
        if not atoms_for_boundary:
            return _store(None)
        boundary = []
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            a_sel = bond.a in atoms_for_boundary
            b_sel = bond.b in atoms_for_boundary
            if a_sel ^ b_sel:
                boundary.append(bond_id)
        if len(boundary) == 1:
            bond_id = boundary[0]
            if not self.bond_is_rotatable(bond_id):
                return _store(None)
            rotating = self.rotation_side_for_bond(
                bond_id,
                atoms_for_boundary,
                allow_fallback=not explicit_atoms,
            )
            if rotating is not None:
                return _store((bond_id, rotating))
        atoms_for_axis = set(atoms_for_boundary)
        candidates: list[tuple[int, set[int]]] = []
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None or not self.bond_is_rotatable(bond_id):
                continue
            rotating = self.rotation_side_for_bond(
                bond_id,
                atoms_for_axis,
                allow_fallback=False,
            )
            if rotating is None:
                continue
            candidates.append((bond_id, rotating))
        axis = candidates[0] if len(candidates) == 1 else None
        return _store(axis)

    def axis_from_rotation_hint(
        self,
        axis_hint: int,
        rotation_atom_ids: set[int],
        press_pos: QPointF | None = None,
    ) -> tuple[int, set[int]] | None:
        if not self.bond_is_rotatable(axis_hint):
            return None
        component = self.bond_component_atoms(axis_hint)
        if component is None:
            return None
        selected_in_component = rotation_atom_ids & component
        if not selected_in_component:
            return None
        rotating = self.preferred_rotation_side_for_bond(
            axis_hint,
            selected_in_component,
            press_pos=press_pos,
            allow_fallback=True,
        )
        if rotating is None:
            return None
        return axis_hint, rotating

    def bond_sets_for_atoms(self, atom_ids: set[int]) -> tuple[set[int], set[int]]:
        internal: set[int] = set()
        boundary: set[int] = set()
        if not atom_ids:
            return internal, boundary
        bond_ids: set[int] = set()
        for atom_id in atom_ids:
            bond_ids.update(self.graph.atom_bond_ids.get(atom_id, ()))
        if not bond_ids:
            for bond_id, bond in enumerate(self.canvas.model.bonds):
                if bond is None:
                    continue
                a_in = bond.a in atom_ids
                b_in = bond.b in atom_ids
                if a_in or b_in:
                    bond_ids.add(bond_id)
        for bond_id in bond_ids:
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                continue
            a_in = bond.a in atom_ids
            b_in = bond.b in atom_ids
            if a_in and b_in:
                internal.add(bond_id)
            elif a_in or b_in:
                boundary.add(bond_id)
        return internal, boundary

    def expand_connected_atoms(self, atom_ids: set[int]) -> set[int]:
        if not atom_ids:
            return set()
        adjacency: dict[int, set[int]] = {}
        for bond in self.canvas.model.bonds:
            if bond is None:
                continue
            adjacency.setdefault(bond.a, set()).add(bond.b)
            adjacency.setdefault(bond.b, set()).add(bond.a)
        visited = set(atom_ids)
        stack = list(atom_ids)
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        return visited

def canvas_graph_service_for(canvas) -> CanvasGraphService:
    return canvas._canvas_graph_service


__all__ = ["CanvasGraphService", "canvas_graph_service_for"]
