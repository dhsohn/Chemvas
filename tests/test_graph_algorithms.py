from types import SimpleNamespace

from ui.graph_algorithms import (
    adjacency_for_bonds,
    connected_components_for_nodes,
    edge_has_reachable_alternative_path,
    reachable_component_without_edge,
    reachable_from,
)


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
