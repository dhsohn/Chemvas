from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
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


def _shortest_cycle_through_edge(
    adjacency: Mapping[int, Iterable[int]],
    u: int,
    v: int,
) -> list[int] | None:
    """Shortest path from ``v`` back to ``u`` that does not use the ``u``-``v``
    edge, returned as an ordered atom list ``[u, ..., v]``. ``None`` when the
    edge is a bridge (no cycle contains it)."""
    prev: dict[int, int | None] = {u: None}
    queue: deque[int] = deque([u])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, ()):
            if {current, neighbor} == {u, v}:
                continue
            if neighbor in prev:
                continue
            prev[neighbor] = current
            if neighbor == v:
                path = [v]
                node: int | None = current
                while node is not None:
                    path.append(node)
                    node = prev[node]
                path.reverse()
                return path
            queue.append(neighbor)
    return None


def _fundamental_cycle_candidates(
    adjacency: Mapping[int, Iterable[int]],
    edge_list: Sequence[tuple[int, int]],
) -> list[list[int]]:
    """Return a guaranteed cycle-basis candidate for every non-tree edge.

    The shortest-cycle pass below deliberately chooses only one shortest path
    per edge.  Ties can therefore leave those candidates linearly dependent.
    Fundamental cycles from a spanning forest guarantee enough independent
    fallbacks to reach the graph's cycle rank while still letting the shorter
    candidates win during the length-sorted GF(2) selection.
    """
    parent: dict[int, int | None] = {}
    depth: dict[int, int] = {}
    tree_edges: set[frozenset[int]] = set()
    for root in sorted(adjacency):
        if root in parent:
            continue
        parent[root] = None
        depth[root] = 0
        stack = [root]
        while stack:
            current = stack.pop()
            for neighbor in sorted(adjacency.get(current, ()), reverse=True):
                if neighbor in parent:
                    continue
                parent[neighbor] = current
                depth[neighbor] = depth[current] + 1
                tree_edges.add(frozenset((current, neighbor)))
                stack.append(neighbor)

    cycles: list[list[int]] = []
    for u, v in edge_list:
        if frozenset((u, v)) in tree_edges:
            continue
        path_u = [u]
        path_v = [v]
        left = u
        right = v
        while depth[left] > depth[right]:
            next_left = parent[left]
            if next_left is None:
                break
            left = next_left
            path_u.append(left)
        while depth[right] > depth[left]:
            next_right = parent[right]
            if next_right is None:
                break
            right = next_right
            path_v.append(right)
        while left != right:
            next_left = parent[left]
            next_right = parent[right]
            if next_left is None or next_right is None:
                break
            left = next_left
            right = next_right
            path_u.append(left)
            path_v.append(right)
        if left == right:
            cycles.append(path_u + list(reversed(path_v[:-1])))
    return cycles


def find_rings(bonds: Iterable[Any]) -> list[list[int]]:
    """Smallest set of smallest rings for a bond graph.

    Each ring is returned as an ordered list of atom ids where consecutive
    entries (and the first/last pair) are bonded, suitable for building a ring
    polygon. Uses a Horton-style candidate generation with GF(2) independence so
    fused systems yield the chemically expected smallest rings.

    This is an SSSR *approximation*: shortest candidates are limited to one
    path per edge (full Horton enumerates every shortest-path tie). A spanning
    forest contributes fundamental cycles so the result still reaches the full
    cycle rank, but exotic cages can yield a valid basis that is not the
    textbook minimum SSSR. Common fused systems (6-6, 6-5, steroids) are
    unaffected.
    """
    bond_list = list(bonds)
    adjacency = adjacency_for_bonds(bond_list)
    if not adjacency:
        return []
    edge_list: list[tuple[int, int]] = []
    seen_edges: set[frozenset[int]] = set()
    for bond in bond_list:
        if bond is None:
            continue
        key = frozenset((bond.a, bond.b))
        if len(key) != 2 or key in seen_edges:
            continue
        seen_edges.add(key)
        edge_list.append((bond.a, bond.b))
    nodes = set(adjacency)
    num_components = len(connected_components_for_nodes(nodes, adjacency))
    cycle_rank = len(edge_list) - len(nodes) + num_components
    if cycle_rank <= 0:
        return []
    edge_index = {frozenset(edge): index for index, edge in enumerate(edge_list)}

    candidates: list[list[int]] = []
    for u, v in edge_list:
        ring = _shortest_cycle_through_edge(adjacency, u, v)
        if ring is not None:
            candidates.append(ring)
    candidates.extend(_fundamental_cycle_candidates(adjacency, edge_list))

    unique: dict[frozenset[frozenset[int]], list[int]] = {}
    for ring in candidates:
        key = frozenset(
            frozenset((ring[index], ring[(index + 1) % len(ring)]))
            for index in range(len(ring))
        )
        if key not in unique or len(ring) < len(unique[key]):
            unique[key] = ring

    chosen: list[list[int]] = []
    pivots: dict[int, int] = {}
    for ring in sorted(unique.values(), key=lambda candidate: (len(candidate), tuple(candidate))):
        vector = 0
        valid = True
        for index in range(len(ring)):
            edge_key = frozenset((ring[index], ring[(index + 1) % len(ring)]))
            edge_id = edge_index.get(edge_key)
            if edge_id is None:
                valid = False
                break
            vector ^= 1 << edge_id
        if not valid or vector == 0:
            continue
        reduced = vector
        while reduced:
            high_bit = reduced.bit_length() - 1
            existing = pivots.get(high_bit)
            if existing is None:
                pivots[high_bit] = reduced
                chosen.append(ring)
                break
            reduced ^= existing
        if len(chosen) >= cycle_rank:
            break
    return chosen


__all__ = [
    "adjacency_for_bonds",
    "connected_components_for_nodes",
    "edge_has_reachable_alternative_path",
    "find_rings",
    "reachable_component_without_edge",
    "reachable_from",
]
