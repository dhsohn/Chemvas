from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def connected_components_for_nodes(
    atom_ids: set[int],
    adjacency: Mapping[int, Iterable[int]],
) -> list[set[int]]:
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
            for neighbor in adjacency.get(current, ()):
                if neighbor not in atom_ids:
                    continue
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    comp.add(neighbor)
                    stack.append(neighbor)
        components.append(comp)
    return components


def reachable_component_without_edge(
    start_atom_id: int,
    adjacency: Mapping[int, Iterable[int]],
    *,
    blocked_edge: tuple[int, int] | None = None,
) -> set[int]:
    visited = {start_atom_id}
    stack = [start_atom_id]
    while stack:
        current = stack.pop()
        for neighbor in adjacency.get(current, ()):
            if blocked_edge is not None and {
                current,
                neighbor,
            } == set(blocked_edge):
                continue
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return visited


def edge_has_reachable_alternative_path(
    start_atom_id: int,
    target_atom_id: int,
    adjacency: Mapping[int, Iterable[int]],
    *,
    skip_direct_edge: bool,
) -> bool:
    blocked_edge = (start_atom_id, target_atom_id) if skip_direct_edge else None
    visited = {start_atom_id}
    stack = [start_atom_id]
    while stack:
        current = stack.pop()
        for neighbor in adjacency.get(current, ()):
            if blocked_edge is not None and {
                current,
                neighbor,
            } == set(blocked_edge):
                continue
            if neighbor in visited:
                continue
            if neighbor == target_atom_id:
                return True
            visited.add(neighbor)
            stack.append(neighbor)
    return False


def adjacency_for_bonds(bonds: Iterable[Any]) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = {}
    for bond in bonds:
        if bond is None:
            continue
        adjacency.setdefault(bond.a, set()).add(bond.b)
        adjacency.setdefault(bond.b, set()).add(bond.a)
    return adjacency


def reachable_from(atom_ids: set[int], adjacency: Mapping[int, Iterable[int]]) -> set[int]:
    if not atom_ids:
        return set()
    visited = set(atom_ids)
    stack = list(atom_ids)
    while stack:
        current = stack.pop()
        for neighbor in adjacency.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return visited


__all__ = [
    "adjacency_for_bonds",
    "connected_components_for_nodes",
    "edge_has_reachable_alternative_path",
    "reachable_component_without_edge",
    "reachable_from",
]
