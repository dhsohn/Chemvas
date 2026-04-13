import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.selection_hit_logic import (
    AtomHitCandidate,
    BondHitCandidate,
    SelectionHitRequest,
    SelectionRect,
    SelectionSnapshot,
    StructureHit,
    build_selection_snapshot,
    choose_preferred_structure_hit,
    nearest_ring_atom_id,
    padded_rect_contains_point,
    selection_hit_matches,
    structure_hit_is_selected,
)


class SelectionHitLogicTest(unittest.TestCase):
    def test_build_selection_snapshot_expands_selected_bond_endpoints(self) -> None:
        snapshot = build_selection_snapshot(
            selected_atom_ids=[1],
            selected_bond_ids=[7],
            selected_bond_atom_ids=((2, 3),),
            selection_items=("item",),
        )

        self.assertEqual(
            snapshot,
            SelectionSnapshot(
                selected_atom_ids=frozenset({1, 2, 3}),
                selected_bond_ids=frozenset({7}),
                selection_items=("item",),
            ),
        )

    def test_build_selection_snapshot_preserves_empty_inputs(self) -> None:
        snapshot = build_selection_snapshot(
            selected_atom_ids=[],
            selected_bond_ids=[],
            selection_items=[],
        )

        self.assertEqual(
            snapshot,
            SelectionSnapshot(
                selected_atom_ids=frozenset(),
                selected_bond_ids=frozenset(),
                selection_items=(),
            ),
        )

    def test_unlabeled_atom_in_hard_pick_zone_beats_bond(self) -> None:
        hit = choose_preferred_structure_hit(
            AtomHitCandidate(atom_id=1, distance=1.0, has_visible_label=False),
            BondHitCandidate(bond_id=2, distance=0.1),
            atom_pick_radius=10.0,
            bond_pick_radius=10.0,
        )

        self.assertEqual(hit, StructureHit(kind="atom", id=1))

    def test_bond_wins_when_normalized_scores_are_close_for_labeled_atom(self) -> None:
        hit = choose_preferred_structure_hit(
            AtomHitCandidate(atom_id=1, distance=6.0, has_visible_label=True),
            BondHitCandidate(bond_id=2, distance=5.0),
            atom_pick_radius=10.0,
            bond_pick_radius=10.0,
        )

        self.assertEqual(hit, StructureHit(kind="bond", id=2))

    def test_atom_wins_when_bond_score_is_materially_worse(self) -> None:
        hit = choose_preferred_structure_hit(
            AtomHitCandidate(atom_id=1, distance=6.0, has_visible_label=True),
            BondHitCandidate(bond_id=2, distance=9.0),
            atom_pick_radius=10.0,
            bond_pick_radius=10.0,
        )

        self.assertEqual(hit, StructureHit(kind="atom", id=1))

    def test_single_candidate_and_no_candidate_cases(self) -> None:
        self.assertEqual(
            choose_preferred_structure_hit(
                AtomHitCandidate(atom_id=4, distance=7.0, has_visible_label=True),
                None,
                atom_pick_radius=10.0,
                bond_pick_radius=10.0,
            ),
            StructureHit(kind="atom", id=4),
        )
        self.assertEqual(
            choose_preferred_structure_hit(
                None,
                BondHitCandidate(bond_id=7, distance=2.0),
                atom_pick_radius=10.0,
                bond_pick_radius=10.0,
            ),
            StructureHit(kind="bond", id=7),
        )
        self.assertIsNone(
            choose_preferred_structure_hit(
                None,
                None,
                atom_pick_radius=10.0,
                bond_pick_radius=10.0,
            )
        )

    def test_nearest_ring_atom_id_returns_nearest_within_threshold(self) -> None:
        self.assertEqual(
            nearest_ring_atom_id([(10, 8.0), (11, 2.5), (12, 4.0)], max_distance=5.0),
            11,
        )
        self.assertIsNone(nearest_ring_atom_id([(10, 8.0), (11, 6.0)], max_distance=5.0))

    def test_structure_hit_is_selected_for_atom_bond_ring_and_other(self) -> None:
        selected_atom_ids = {1, 2}
        selected_bond_ids = {9}

        self.assertTrue(
            structure_hit_is_selected(
                StructureHit(kind="atom", id=1),
                selected_atom_ids=selected_atom_ids,
                selected_bond_ids=selected_bond_ids,
            )
        )
        self.assertTrue(
            structure_hit_is_selected(
                StructureHit(kind="bond", id=5),
                selected_atom_ids=selected_atom_ids,
                selected_bond_ids=selected_bond_ids,
                bond_atom_ids=(2, 4),
            )
        )
        self.assertTrue(
            structure_hit_is_selected(
                StructureHit(kind="ring"),
                selected_atom_ids=selected_atom_ids,
                selected_bond_ids=selected_bond_ids,
                ring_atom_ids=[4, 5, 2],
            )
        )
        self.assertTrue(
            structure_hit_is_selected(
                StructureHit(kind="other"),
                selected_atom_ids=selected_atom_ids,
                selected_bond_ids=selected_bond_ids,
                item_is_selected=True,
            )
        )
        self.assertFalse(
            structure_hit_is_selected(
                StructureHit(kind="bond", id=4),
                selected_atom_ids=set(),
                selected_bond_ids=set(),
                bond_atom_ids=(6, 7),
            )
        )

    def test_structure_hit_is_selected_handles_none_and_direct_selected_bond(self) -> None:
        self.assertFalse(
            structure_hit_is_selected(
                None,
                selected_atom_ids=set(),
                selected_bond_ids=set(),
            )
        )
        self.assertTrue(
            structure_hit_is_selected(
                StructureHit(kind="bond", id=9),
                selected_atom_ids=set(),
                selected_bond_ids={9},
            )
        )

    def test_structure_hit_is_selected_requires_context_for_ring_and_bond(self) -> None:
        self.assertFalse(
            structure_hit_is_selected(
                StructureHit(kind="bond", id=4),
                selected_atom_ids=set(),
                selected_bond_ids=set(),
                bond_atom_ids=None,
            )
        )
        self.assertFalse(
            structure_hit_is_selected(
                StructureHit(kind="ring"),
                selected_atom_ids={1},
                selected_bond_ids=set(),
                ring_atom_ids=None,
            )
        )

    def test_padded_rect_contains_point_expands_bounds(self) -> None:
        rect = SelectionRect(left=10.0, top=20.0, right=30.0, bottom=40.0)

        self.assertTrue(padded_rect_contains_point(rect, (8.0, 20.0), pad=2.0))
        self.assertFalse(padded_rect_contains_point(rect, (7.9, 20.0), pad=2.0))

    def test_selection_hit_matches_accepts_outline_and_rect_hits(self) -> None:
        outline_request = SelectionHitRequest(
            point=(0.0, 0.0),
            outline_hit=True,
            rects=(),
            pad=0.0,
            hit=None,
            selected_atom_ids=frozenset(),
            selected_bond_ids=frozenset(),
        )
        rect_request = SelectionHitRequest(
            point=(15.0, 15.0),
            outline_hit=False,
            rects=(SelectionRect(left=10.0, top=10.0, right=20.0, bottom=20.0),),
            pad=1.0,
            hit=None,
            selected_atom_ids=frozenset(),
            selected_bond_ids=frozenset(),
        )

        self.assertTrue(selection_hit_matches(outline_request))
        self.assertTrue(selection_hit_matches(rect_request))

    def test_selection_hit_matches_falls_back_to_structure_selectedness(self) -> None:
        request = SelectionHitRequest(
            point=(0.0, 0.0),
            outline_hit=False,
            rects=(),
            pad=0.0,
            hit=StructureHit(kind="bond", id=9),
            selected_atom_ids=frozenset(),
            selected_bond_ids=frozenset({9}),
            item_is_selected=False,
        )
        miss_request = SelectionHitRequest(
            point=(0.0, 0.0),
            outline_hit=False,
            rects=(),
            pad=0.0,
            hit=StructureHit(kind="other"),
            selected_atom_ids=frozenset(),
            selected_bond_ids=frozenset(),
            item_is_selected=False,
        )

        self.assertTrue(selection_hit_matches(request))
        self.assertFalse(selection_hit_matches(miss_request))


if __name__ == "__main__":
    unittest.main()
