from types import SimpleNamespace

from ui.graph_algorithms import (
    adjacency_for_bonds,
    connected_components_for_nodes,
    edge_has_reachable_alternative_path,
    find_rings,
    reachable_component_without_edge,
    reachable_from,
)


def _bond(a: int, b: int) -> SimpleNamespace:
    return SimpleNamespace(a=a, b=b)


def test_find_rings_returns_ordered_single_ring_for_simple_cycle() -> None:
    bonds = [_bond(0, 1), _bond(1, 2), _bond(2, 3), _bond(3, 4), _bond(4, 5), _bond(5, 0)]

    rings = find_rings(bonds)

    assert len(rings) == 1
    assert frozenset(rings[0]) == {0, 1, 2, 3, 4, 5}
    # consecutive entries (and wrap-around) must be bonded
    edges = {frozenset((b.a, b.b)) for b in bonds}
    ring = rings[0]
    for index in range(len(ring)):
        assert frozenset((ring[index], ring[(index + 1) % len(ring)])) in edges


def test_find_rings_finds_both_fused_rings_and_ignores_substituents() -> None:
    naphthalene = [
        _bond(0, 1), _bond(1, 2), _bond(2, 3), _bond(3, 4), _bond(4, 5), _bond(5, 0),
        _bond(5, 6), _bond(6, 7), _bond(7, 8), _bond(8, 9), _bond(9, 0),
        _bond(2, 10),  # exocyclic substituent
    ]

    rings = find_rings(naphthalene)

    assert sorted(sorted(r) for r in rings) == [[0, 1, 2, 3, 4, 5], [0, 5, 6, 7, 8, 9]]


def test_find_rings_completes_cycle_basis_when_shortest_candidates_are_dependent() -> None:
    # The four atoms 1-4 form K4 and atom 0 adds one more triangle on edge
    # 3-4.  One-shortest-path-per-edge can choose dependent candidates here,
    # but the graph's cycle rank is E - V + C = 8 - 5 + 1 = 4.
    bonds = [
        _bond(0, 3),
        _bond(0, 4),
        _bond(1, 2),
        _bond(1, 3),
        _bond(1, 4),
        _bond(2, 3),
        _bond(2, 4),
        _bond(3, 4),
    ]

    rings = find_rings(bonds)

    assert len(rings) == 4
    edges = {frozenset((bond.a, bond.b)) for bond in bonds}
    assert all(
        frozenset((ring[index], ring[(index + 1) % len(ring)])) in edges
        for ring in rings
        for index in range(len(ring))
    )


def test_find_rings_accepts_single_pass_bond_iterables() -> None:
    bonds = (_bond(a, b) for a, b in ((0, 1), (1, 2), (2, 0)))

    rings = find_rings(bonds)

    assert len(rings) == 1
    assert frozenset(rings[0]) == {0, 1, 2}


def test_find_rings_returns_empty_for_acyclic_graph() -> None:
    assert find_rings([_bond(0, 1), _bond(1, 2), _bond(2, 3)]) == []
    assert find_rings([]) == []


def test_connected_components_for_nodes_filters_to_requested_atom_ids() -> None:
    adjacency = {
        1: {2},
        2: {1, 3},
        3: {2},
        4: {5},
        5: {4},
    }

    components = {
        frozenset(component)
        for component in connected_components_for_nodes({1, 2, 4, 9}, adjacency)
    }

    assert components == {frozenset({1, 2}), frozenset({4}), frozenset({9})}


def test_reachability_helpers_can_skip_one_direct_edge() -> None:
    adjacency = {
        1: {2, 3},
        2: {1, 4},
        3: {1, 4},
        4: {2, 3},
    }

    assert reachable_component_without_edge(1, adjacency, blocked_edge=(1, 2)) == {1, 2, 3, 4}
    assert reachable_component_without_edge(1, {1: {2}, 2: {1}}, blocked_edge=(1, 2)) == {1}
    assert edge_has_reachable_alternative_path(1, 2, adjacency, skip_direct_edge=True)
    assert edge_has_reachable_alternative_path(1, 2, adjacency, skip_direct_edge=False)
    assert not edge_has_reachable_alternative_path(1, 2, {1: {2}, 2: {1}}, skip_direct_edge=True)


def test_adjacency_for_bonds_and_reachable_from_ignore_empty_bond_slots() -> None:
    bonds = [
        SimpleNamespace(a=1, b=2),
        None,
        SimpleNamespace(a=3, b=4),
        SimpleNamespace(a=4, b=5),
    ]

    adjacency = adjacency_for_bonds(bonds)

    assert adjacency == {1: {2}, 2: {1}, 3: {4}, 4: {3, 5}, 5: {4}}
    assert reachable_from({3}, adjacency) == {3, 4, 5}
    assert reachable_from(set(), adjacency) == set()
