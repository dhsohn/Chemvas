"""The one bond-removal rule shared by every delete path (Qt-free)."""

from __future__ import annotations

from chemvas.domain.document import (
    Bond,
    bond_endpoint_ids,
    broken_ring_fill_indices,
    orphaned_atom_ids,
    ring_fill_is_intact,
)


def _bonds(*pairs: tuple[int, int] | None) -> list[Bond | None]:
    return [None if pair is None else Bond(pair[0], pair[1], 1) for pair in pairs]


def _never_visible(_atom_id: int) -> bool:
    return False


def test_bond_endpoint_ids_lists_each_endpoint_once_in_bond_order() -> None:
    bonds = _bonds((3, 1), (1, 2), None)
    assert bond_endpoint_ids(bonds, [0, 1]) == (3, 1, 2)


def test_bond_endpoint_ids_skips_missing_and_out_of_range_bonds() -> None:
    bonds = _bonds((3, 1), None)
    assert bond_endpoint_ids(bonds, [1, 7, -1, 0]) == (3, 1)


def test_bare_endpoints_without_a_surviving_bond_are_orphaned() -> None:
    bonds = _bonds((0, 1), (1, 2))
    assert orphaned_atom_ids(
        bonds,
        candidate_atom_ids=(0, 1),
        removed_bond_ids={0},
        keeps_visible=_never_visible,
    ) == (0,)


def test_a_removed_bond_already_gone_from_the_model_is_not_required() -> None:
    # The single-bond delete path calls after the bond left the model.
    bonds = _bonds(None, (1, 2))
    assert orphaned_atom_ids(
        bonds, candidate_atom_ids=(0, 1), keeps_visible=_never_visible
    ) == (0,)


def test_labels_marks_removal_and_absence_all_protect() -> None:
    bonds = _bonds((0, 1), (2, 3), (4, 5))
    assert orphaned_atom_ids(
        bonds,
        candidate_atom_ids=(0, 1, 2, 3, 4, 5, 9),
        removed_bond_ids={0, 1, 2},
        removed_atom_ids={1},
        keeps_visible=lambda atom_id: atom_id in {2, 4},
        atom_exists=lambda atom_id: atom_id != 9,
    ) == (0, 3, 5)


def test_orphans_keep_candidate_order_and_deduplicate() -> None:
    bonds = _bonds((5, 2), (2, 5))
    assert orphaned_atom_ids(
        bonds,
        candidate_atom_ids=(5, 2, 5),
        removed_bond_ids={0, 1},
        keeps_visible=_never_visible,
    ) == (5, 2)


def test_fills_that_no_longer_form_a_bonded_cycle_are_broken() -> None:
    atom_ids = {0, 1, 2, 3}
    bond_pairs = {(0, 1), (1, 2), (0, 2)}
    fills = [[0, 1, 2], [0, 1, 3], "not a list", [0, 1, 2.0]]
    assert broken_ring_fill_indices(
        fills, atom_ids=atom_ids, bond_pairs=bond_pairs
    ) == (1, 2, 3)
    assert ring_fill_is_intact([0, 1, 2], atom_ids=atom_ids, bond_pairs=bond_pairs)
    assert not ring_fill_is_intact((0, 1, 2), atom_ids=atom_ids, bond_pairs=bond_pairs)
