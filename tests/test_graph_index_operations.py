from types import SimpleNamespace

from ui.graph_index_operations import (
    add_bond_to_atom_index,
    add_neighbor_edge,
    bond_id_between_indexed_atoms,
    bond_matches_atoms,
    bond_sets_for_atom_ids,
    build_bond_adjacency_index,
    ensure_bond_index_entry,
    ensure_neighbor_entry,
    first_matching_bond_id,
    remove_bond_from_atom_index,
    remove_neighbor_edge,
)


def _bond(a: int, b: int, order: int = 1):
    return SimpleNamespace(a=a, b=b, order=order)


def test_neighbor_and_atom_bond_index_mutations_preserve_existing_entries() -> None:
    atom_neighbors = {1: {2}, 2: {1}}
    atom_bond_ids = {1: {0}, 2: {0}}

    ensure_neighbor_entry(atom_neighbors, 3)
    ensure_bond_index_entry(atom_bond_ids, 3)
    add_neighbor_edge(atom_neighbors, 2, 3)
    add_bond_to_atom_index(atom_bond_ids, 1, 2, 3)

    assert atom_neighbors == {1: {2}, 2: {1, 3}, 3: {2}}
    assert atom_bond_ids == {1: {0}, 2: {0, 1}, 3: {1}}
    assert remove_neighbor_edge(atom_neighbors, 1, 2)
    assert atom_neighbors == {1: set(), 2: {3}, 3: {2}}
    assert not remove_neighbor_edge(atom_neighbors, 1, 9)
    remove_bond_from_atom_index(atom_bond_ids, 1, 2, 3)
    remove_bond_from_atom_index(atom_bond_ids, 99, 2, 3)
    assert atom_bond_ids == {1: {0}, 2: {0}, 3: set()}


def test_bond_lookup_uses_index_when_available_and_falls_back_to_scan() -> None:
    bonds = [_bond(1, 2), _bond(1, 2, order=2), None, _bond(2, 3)]
    atom_bond_ids = {1: {0, 1}, 2: {0, 1, 3}, 3: {3}}

    assert bond_matches_atoms(bonds[0], 2, 1)
    assert not bond_matches_atoms(None, 1, 2)
    assert first_matching_bond_id(bonds, 1, 2) == 0
    assert first_matching_bond_id(bonds, 1, 2, skip_bond_id=0) == 1
    assert first_matching_bond_id(bonds, 1, 9) is None
    assert (
        bond_id_between_indexed_atoms(
            atom_bond_ids,
            bonds,
            1,
            2,
            bond_for_id=lambda bond_id: bonds[bond_id],
        )
        == 0
    )
    assert (
        bond_id_between_indexed_atoms(
            atom_bond_ids,
            bonds,
            1,
            2,
            bond_for_id=lambda bond_id: bonds[bond_id],
            skip_bond_id=0,
        )
        == 1
    )
    assert (
        bond_id_between_indexed_atoms(
            {},
            bonds,
            1,
            2,
            bond_for_id=lambda bond_id: bonds[bond_id],
            skip_bond_id=0,
        )
        == 1
    )
    assert (
        bond_id_between_indexed_atoms(
            atom_bond_ids,
            bonds,
            1,
            1,
            bond_for_id=lambda bond_id: bonds[bond_id],
        )
        is None
    )


def test_build_bond_adjacency_index_and_bond_set_classification() -> None:
    bonds = [_bond(1, 2), None, _bond(2, 3), _bond(9, 10)]

    atom_neighbors, atom_bond_ids = build_bond_adjacency_index([1, 2, 3, 4], bonds)

    assert atom_neighbors == {
        1: {2},
        2: {1, 3},
        3: {2},
        4: set(),
        9: {10},
        10: {9},
    }
    assert atom_bond_ids == {
        1: {0},
        2: {0, 2},
        3: {2},
        4: set(),
        9: {3},
        10: {3},
    }
    assert (
        bond_sets_for_atom_ids(
            {1, 2},
            atom_bond_ids,
            bonds,
            bond_for_id=lambda bond_id: bonds[bond_id],
        )
        == ({0}, {2})
    )
    assert (
        bond_sets_for_atom_ids(
            {9},
            {},
            bonds,
            bond_for_id=lambda bond_id: bonds[bond_id],
        )
        == (set(), {3})
    )
    assert (
        bond_sets_for_atom_ids(
            set(),
            atom_bond_ids,
            bonds,
            bond_for_id=lambda bond_id: bonds[bond_id],
        )
        == (set(), set())
    )
