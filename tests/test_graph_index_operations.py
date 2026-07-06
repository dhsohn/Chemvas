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


class _BondsThatMustNotBeScanned:
    def __iter__(self):
        raise AssertionError("valid indexed lookups must not scan the model")


class _CountingBonds:
    def __init__(self, bonds):
        self.bonds = bonds
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        return iter(self.bonds)


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
            {1: set(), 2: set()},
            bonds,
            1,
            2,
            bond_for_id=lambda bond_id: bonds[bond_id],
        )
        == 0
    )
    assert (
        bond_id_between_indexed_atoms(
            {1: set(), 2: set()},
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


def test_bond_lookup_preserves_fast_indexed_path_for_valid_entries() -> None:
    assert (
        bond_id_between_indexed_atoms(
            {1: {7}, 2: {7}},
            _BondsThatMustNotBeScanned(),
            1,
            2,
            bond_for_id=lambda bond_id: _bond(1, 2) if bond_id == 7 else None,
        )
        == 7
    )
    assert (
        bond_id_between_indexed_atoms(
            {1: {7}, 2: {8}},
            _BondsThatMustNotBeScanned(),
            1,
            2,
            bond_for_id=lambda bond_id: _bond(1, 2),
        )
        is None
    )


def test_bond_lookup_scans_stale_disjoint_entries_only_in_repair_mode() -> None:
    bonds = [_bond(1, 3), _bond(2, 4), _bond(1, 2)]
    atom_bond_ids = {1: {0}, 2: {1}, 3: {0}, 4: {1}}

    assert (
        bond_id_between_indexed_atoms(
            atom_bond_ids,
            _BondsThatMustNotBeScanned(),
            1,
            2,
            bond_for_id=lambda bond_id: bonds[bond_id],
        )
        is None
    )
    assert (
        bond_id_between_indexed_atoms(
            atom_bond_ids,
            bonds,
            1,
            2,
            bond_for_id=lambda bond_id: bonds[bond_id],
            scan_index_misses=True,
        )
        == 2
    )


def test_bond_lookup_scans_unindexed_negative_once() -> None:
    bonds = _CountingBonds([_bond(3, 4), _bond(5, 6)])

    assert (
        bond_id_between_indexed_atoms(
            {1: set(), 2: set()},
            bonds,
            1,
            2,
            bond_for_id=lambda bond_id: bonds.bonds[bond_id],
        )
        is None
    )
    assert bonds.iterations == 1


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


def test_bond_sets_scans_for_atoms_missing_an_index_entry() -> None:
    # Atom 2 has no index entry at all (never indexed), while atom 1 is
    # indexed: the lookup must scan for atom 2's bonds instead of silently
    # returning a partial result.
    bonds = [_bond(1, 5), _bond(2, 3)]
    atom_bond_ids = {1: {0}, 3: {1}, 5: {0}}

    assert (
        bond_sets_for_atom_ids(
            {1, 2},
            atom_bond_ids,
            bonds,
            bond_for_id=lambda bond_id: bonds[bond_id],
        )
        == (set(), {0, 1})
    )


def test_bond_sets_scans_for_atoms_with_empty_index_entries() -> None:
    bonds = [_bond(1, 5), _bond(2, 3)]
    atom_bond_ids = {1: {0}, 2: set(), 3: {1}, 5: {0}}

    assert (
        bond_sets_for_atom_ids(
            {1, 2},
            atom_bond_ids,
            bonds,
            bond_for_id=lambda bond_id: bonds[bond_id],
        )
        == (set(), {0, 1})
    )
