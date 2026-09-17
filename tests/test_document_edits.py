"""The one bond-removal rule shared by every delete path (Qt-free)."""

from __future__ import annotations

import unittest

from chemvas.domain.document import (
    Bond,
    bond_endpoint_ids,
    broken_ring_fill_indices,
    orphaned_atom_ids,
)


def _bonds(*pairs: tuple[int, int] | None) -> list[Bond | None]:
    return [None if pair is None else Bond(pair[0], pair[1], 1) for pair in pairs]


class BondEndpointIdsTest(unittest.TestCase):
    def test_lists_each_endpoint_once_in_bond_order(self) -> None:
        bonds = _bonds((3, 1), (1, 2), None)
        self.assertEqual(bond_endpoint_ids(bonds, [0, 1]), (3, 1, 2))

    def test_skips_missing_and_out_of_range_bonds(self) -> None:
        bonds = _bonds((3, 1), None)
        self.assertEqual(bond_endpoint_ids(bonds, [1, 7, -1, 0]), (3, 1))


class OrphanedAtomIdsTest(unittest.TestCase):
    def test_bare_endpoints_without_a_surviving_bond_are_orphaned(self) -> None:
        bonds = _bonds((0, 1), (1, 2))
        self.assertEqual(
            orphaned_atom_ids(
                bonds,
                candidate_atom_ids=(0, 1),
                removed_bond_ids={0},
                keeps_visible=lambda _atom_id: False,
            ),
            (0,),
        )

    def test_a_removed_bond_already_gone_from_the_model_is_not_required(self) -> None:
        # The single-bond delete path calls after the bond left the model.
        bonds = _bonds(None, (1, 2))
        self.assertEqual(
            orphaned_atom_ids(
                bonds,
                candidate_atom_ids=(0, 1),
                keeps_visible=lambda _atom_id: False,
            ),
            (0,),
        )

    def test_labels_marks_removal_and_absence_all_protect(self) -> None:
        bonds = _bonds((0, 1), (2, 3), (4, 5))
        self.assertEqual(
            orphaned_atom_ids(
                bonds,
                candidate_atom_ids=(0, 1, 2, 3, 4, 5, 9),
                removed_bond_ids={0, 1, 2},
                removed_atom_ids={1},
                keeps_visible=lambda atom_id: atom_id in {2, 4},
                atom_exists=lambda atom_id: atom_id != 9,
            ),
            (0, 3, 5),
        )

    def test_keeps_candidate_order_and_deduplicates(self) -> None:
        bonds = _bonds((5, 2), (2, 5))
        self.assertEqual(
            orphaned_atom_ids(
                bonds,
                candidate_atom_ids=(5, 2, 5),
                removed_bond_ids={0, 1},
                keeps_visible=lambda _atom_id: False,
            ),
            (5, 2),
        )


class BrokenRingFillIndicesTest(unittest.TestCase):
    def test_fills_that_no_longer_form_a_bonded_cycle_are_broken(self) -> None:
        atom_ids = {0, 1, 2, 3}
        bond_pairs = {(0, 1), (1, 2), (0, 2)}
        fills = [[0, 1, 2], [0, 1, 3], "not a list", [0, 1, 2.0]]
        self.assertEqual(
            broken_ring_fill_indices(fills, atom_ids=atom_ids, bond_pairs=bond_pairs),
            (1, 2, 3),
        )


if __name__ == "__main__":
    unittest.main()
