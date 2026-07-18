from __future__ import annotations

from chemvas.features.selection import (
    center_for_coords_3d,
    flatten_coords_to_plane,
    fragment_plane_normal_for,
)
from chemvas.ui.canvas_graph_state import graph_state_for
from chemvas.ui.canvas_model_access import bond_for_id, bonds_for
from chemvas.ui.graph_algorithms import edge_has_reachable_alternative_path


def bond_in_cycle_for(canvas, bond_id: int) -> bool:
    graph = graph_state_for(canvas)
    cached = graph.bond_cycle_cache.get(bond_id)
    if cached is not None and cached[0] == graph.graph_version:
        return cached[1]
    bond = bond_for_id(canvas, bond_id)
    if bond is None:
        graph.bond_cycle_cache[bond_id] = (graph.graph_version, False)
        return False
    shared = graph.atom_bond_ids.get(bond.a, set()) & graph.atom_bond_ids.get(
        bond.b, set()
    )
    has_alt_between = any(other_id != bond_id for other_id in shared)
    in_cycle = edge_has_reachable_alternative_path(
        bond.a,
        bond.b,
        graph.atom_neighbors,
        skip_direct_edge=not has_alt_between,
    )
    graph.bond_cycle_cache[bond_id] = (graph.graph_version, in_cycle)
    return in_cycle


def atom_in_planar_system_for(canvas, atom_id: int, *, bond_in_cycle=None) -> bool:
    graph = graph_state_for(canvas)
    if bond_in_cycle is None:

        def bond_in_cycle(candidate_id: int) -> bool:
            return bond_in_cycle_for(canvas, candidate_id)

    for bond_id in graph.atom_bond_ids.get(atom_id, ()):
        bond = bond_for_id(canvas, bond_id)
        if bond is None:
            continue
        if bond.order > 1 or bond_in_cycle(bond_id):
            return True
    return False


def bond_is_planar_fragment_edge_for(
    canvas, bond_id: int, *, bond_in_cycle=None
) -> bool:
    if bond_in_cycle is None:

        def bond_in_cycle(candidate_id: int) -> bool:
            return bond_in_cycle_for(canvas, candidate_id)

    bond = bond_for_id(canvas, bond_id)
    if bond is None:
        return False
    if bond.order > 1 or bond_in_cycle(bond_id):
        return True
    return atom_in_planar_system_for(
        canvas, bond.a, bond_in_cycle=bond_in_cycle
    ) and atom_in_planar_system_for(
        canvas,
        bond.b,
        bond_in_cycle=bond_in_cycle,
    )


def planar_fragment_components_for(
    canvas, atom_ids: set[int], *, bond_in_cycle=None
) -> list[set[int]]:
    adjacency: dict[int, set[int]] = {}
    for bond_id, bond in enumerate(bonds_for(canvas)):
        if bond is None:
            continue
        if bond.a not in atom_ids or bond.b not in atom_ids:
            continue
        if not bond_is_planar_fragment_edge_for(
            canvas, bond_id, bond_in_cycle=bond_in_cycle
        ):
            continue
        adjacency.setdefault(bond.a, set()).add(bond.b)
        adjacency.setdefault(bond.b, set()).add(bond.a)
    visited: set[int] = set()
    components: list[set[int]] = []
    for atom_id in adjacency:
        if atom_id in visited:
            continue
        component: set[int] = set()
        stack = [atom_id]
        visited.add(atom_id)
        while stack:
            current = stack.pop()
            component.add(current)
            for neighbor in adjacency.get(current, ()):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)
        if len(component) >= 3:
            components.append(component)
    return components


def flatten_planar_fragments_for(
    canvas,
    atom_ids: set[int],
    coords: dict[int, tuple[float, float, float]],
    *,
    bond_in_cycle=None,
) -> dict[int, tuple[float, float, float]]:
    if not atom_ids:
        return dict(coords)
    flattened = dict(coords)
    for fragment in planar_fragment_components_for(
        canvas, atom_ids, bond_in_cycle=bond_in_cycle
    ):
        normal = fragment_plane_normal_for(fragment, flattened)
        if normal is None:
            continue
        centroid = center_for_coords_3d(fragment, flattened)
        if centroid is None:
            continue
        flattened = flatten_coords_to_plane(
            flattened,
            fragment,
            normal=normal,
            centroid=centroid,
        )
    return flattened


__all__ = [
    "atom_in_planar_system_for",
    "bond_in_cycle_for",
    "bond_is_planar_fragment_edge_for",
    "flatten_planar_fragments_for",
    "planar_fragment_components_for",
]
