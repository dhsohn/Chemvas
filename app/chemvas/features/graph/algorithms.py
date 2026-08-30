"""Pure graph judgments over atom adjacencies and bond components.

Everything here answers a question about graph shape -- connectivity,
reachability, rings, or which side of a bond should rotate -- from plain
mappings and sets. Nothing imports Qt or a drawing surface; bond, atom, and
point arguments are structural (`BondLike`, `AtomCoordsLike`, `PointLike`).
"""

from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING, Protocol

from chemvas.domain.document import connected_atom_components

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence


class BondLike(Protocol):
    """Any bond-shaped object: two atom-id endpoints named ``a`` and ``b``."""

    a: int
    b: int


class AtomCoordsLike(Protocol):
    """Any atom-shaped object carrying 2D coordinates."""

    x: float
    y: float


class PointLike(Protocol):
    """Any point read through ``x()``/``y()`` accessors (e.g. ``QPointF``)."""

    def x(self) -> float: ...

    def y(self) -> float: ...


def connected_components_for_nodes(
    atom_ids: set[int],
    adjacency: Mapping[int, Iterable[int]],
) -> list[set[int]]:
    return [
        set(component)
        for component in connected_atom_components(
            atom_ids,
            (
                (atom_id, neighbor)
                for atom_id in atom_ids
                for neighbor in adjacency.get(atom_id, ())
            ),
        )
    ]


def _walk_reachable(
    seed_atom_ids: Iterable[int],
    adjacency: Mapping[int, Iterable[int]],
    *,
    blocked_edge: tuple[int, int] | None = None,
    stop_at_atom_id: int | None = None,
) -> tuple[set[int], bool]:
    """The one depth-first reachability walk the public helpers below share.

    ``stop_at_atom_id`` is compared *after* the visited check on purpose: a
    seed atom counts as already visited, so asking whether an atom reaches
    itself answers ``False`` and returns before the caller can read a stale
    ``True``.  ``MoleculeModel.add_bond`` rejects ``a == b``, so no bond can
    ask that question today, but the answer is part of this contract and the
    guard in the model is what keeps it unreachable.

    Stopping early is the point of ``stop_at_atom_id``: an existence question
    must not pay for the rest of the component.
    """

    visited = set(seed_atom_ids)
    stack = list(visited)
    blocked = None if blocked_edge is None else set(blocked_edge)
    while stack:
        current = stack.pop()
        for neighbor in adjacency.get(current, ()):
            if blocked is not None and {current, neighbor} == blocked:
                continue
            if neighbor in visited:
                continue
            if neighbor == stop_at_atom_id:
                return visited, True
            visited.add(neighbor)
            stack.append(neighbor)
    return visited, False


def reachable_component_without_edge(
    start_atom_id: int,
    adjacency: Mapping[int, Iterable[int]],
    *,
    blocked_edge: tuple[int, int] | None = None,
) -> set[int]:
    visited, _found = _walk_reachable(
        (start_atom_id,),
        adjacency,
        blocked_edge=blocked_edge,
    )
    return visited


def edge_has_reachable_alternative_path(
    start_atom_id: int,
    target_atom_id: int,
    adjacency: Mapping[int, Iterable[int]],
    *,
    skip_direct_edge: bool,
) -> bool:
    _visited, found = _walk_reachable(
        (start_atom_id,),
        adjacency,
        blocked_edge=(start_atom_id, target_atom_id) if skip_direct_edge else None,
        stop_at_atom_id=target_atom_id,
    )
    return found


def adjacency_for_bonds(bonds: Iterable[BondLike | None]) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = {}
    for bond in bonds:
        if bond is None:
            continue
        adjacency.setdefault(bond.a, set()).add(bond.b)
        adjacency.setdefault(bond.b, set()).add(bond.a)
    return adjacency


def reachable_from(
    atom_ids: set[int], adjacency: Mapping[int, Iterable[int]]
) -> set[int]:
    if not atom_ids:
        return set()
    visited, _found = _walk_reachable(atom_ids, adjacency)
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


def find_rings(bonds: Iterable[BondLike | None]) -> list[list[int]]:
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
        ring_key = frozenset(
            frozenset((ring[index], ring[(index + 1) % len(ring)]))
            for index in range(len(ring))
        )
        if ring_key not in unique or len(ring) < len(unique[ring_key]):
            unique[ring_key] = ring

    chosen: list[list[int]] = []
    pivots: dict[int, int] = {}
    for ring in sorted(
        unique.values(), key=lambda candidate: (len(candidate), tuple(candidate))
    ):
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


def preferred_rotation_side_for_bond_policy(
    bond: BondLike,
    comp_a: set[int],
    comp_b: set[int],
    selected_atom_ids: set[int],
    *,
    atom_a: AtomCoordsLike | None,
    atom_b: AtomCoordsLike | None,
    press_pos: PointLike | None = None,
    bond_length_px: float | None = None,
    allow_fallback: bool,
) -> set[int] | None:
    component = comp_a | comp_b
    selected_in_component = set(selected_atom_ids) & component
    is_partial_selection = 0 < len(selected_in_component) < len(component)
    effective_selected = selected_in_component - {bond.a, bond.b}
    selected_in_a = effective_selected & comp_a
    selected_in_b = effective_selected & comp_b
    overlap_a = selected_in_component & comp_a
    overlap_b = selected_in_component & comp_b
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
        tol = (bond_length_px or 0.0) * 0.05
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


def axis_from_rotation_hint_policy(
    axis_hint: int,
    rotation_atom_ids: set[int],
    *,
    bond_is_rotatable: Callable[[int], bool],
    bond_component_atoms: Callable[[int], set[int] | None],
    preferred_rotation_side_for_bond: Callable[..., set[int] | None],
    press_pos: PointLike | None = None,
) -> tuple[int, set[int]] | None:
    if not bond_is_rotatable(axis_hint):
        return None
    component = bond_component_atoms(axis_hint)
    if component is None:
        return None
    selected_in_component = rotation_atom_ids & component
    if not selected_in_component:
        return None
    rotating = preferred_rotation_side_for_bond(
        axis_hint,
        selected_in_component,
        press_pos=press_pos,
        allow_fallback=True,
    )
    if rotating is None:
        return None
    return axis_hint, rotating


__all__ = [
    "AtomCoordsLike",
    "BondLike",
    "PointLike",
    "adjacency_for_bonds",
    "axis_from_rotation_hint_policy",
    "connected_components_for_nodes",
    "edge_has_reachable_alternative_path",
    "find_rings",
    "preferred_rotation_side_for_bond_policy",
    "reachable_component_without_edge",
    "reachable_from",
]
