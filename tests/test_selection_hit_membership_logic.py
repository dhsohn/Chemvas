import unittest

try:
    from ui.selection_hit_logic import (
        SelectionHitRequest,
        SelectionRect,
        StructureHit,
        selection_hit_matches,
    )
except ImportError as exc:  # pragma: no cover - contract test for upcoming helper API
    SelectionHitRequest = None
    SelectionRect = None
    StructureHit = None
    selection_hit_matches = None
    IMPORT_ERROR = str(exc)
else:  # pragma: no cover - trivial import branch
    IMPORT_ERROR = ""


@unittest.skipIf(
    SelectionHitRequest is None
    or SelectionRect is None
    or selection_hit_matches is None
    or StructureHit is None,
    f"could not import selection-hit matching API from 'ui.selection_hit_logic': {IMPORT_ERROR}",
)
class SelectionHitMembershipLogicTest(unittest.TestCase):
    def _request(
        self,
        *,
        point: tuple[float, float] = (0.0, 0.0),
        outline_hit: bool = False,
        rects: tuple[tuple[float, float, float, float], ...] = (),
        pad: float = 0.0,
        hit=None,
        selected_atom_ids: frozenset[int] = frozenset(),
        selected_bond_ids: frozenset[int] = frozenset(),
        bond_atom_ids: tuple[int, int] | None = None,
        ring_atom_ids: tuple[int, ...] = (),
        item_is_selected: bool = False,
    ):
        return SelectionHitRequest(
            point=point,
            outline_hit=outline_hit,
            rects=tuple(SelectionRect(*rect) for rect in rects),
            pad=pad,
            hit=hit,
            selected_atom_ids=selected_atom_ids,
            selected_bond_ids=selected_bond_ids,
            bond_atom_ids=bond_atom_ids,
            ring_atom_ids=ring_atom_ids,
            item_is_selected=item_is_selected,
        )

    def test_outline_hit_matches_without_other_context(self) -> None:
        self.assertTrue(selection_hit_matches(self._request(outline_hit=True)))

    def test_padded_rect_hit_matches_even_without_structure_hit(self) -> None:
        request = self._request(
            point=(10.8, 20.8),
            rects=((0.0, 0.0, 10.0, 20.0),),
            pad=1.0,
        )

        self.assertTrue(selection_hit_matches(request))

    def test_missed_outline_and_rects_fall_back_to_false_without_selected_hit(self) -> None:
        request = self._request(
            point=(50.0, 50.0),
            rects=((0.0, 0.0, 10.0, 20.0),),
            pad=1.0,
        )

        self.assertFalse(selection_hit_matches(request))

    def test_selected_atom_hit_matches(self) -> None:
        request = self._request(
            hit=StructureHit(kind="atom", id=4),
            selected_atom_ids=frozenset({4}),
        )

        self.assertTrue(selection_hit_matches(request))

    def test_selected_bond_hit_matches_from_direct_bond_selection(self) -> None:
        request = self._request(
            hit=StructureHit(kind="bond", id=9),
            selected_bond_ids=frozenset({9}),
        )

        self.assertTrue(selection_hit_matches(request))

    def test_selected_bond_hit_matches_from_selected_endpoint(self) -> None:
        request = self._request(
            hit=StructureHit(kind="bond", id=7),
            selected_atom_ids=frozenset({11}),
            bond_atom_ids=(11, 12),
        )

        self.assertTrue(selection_hit_matches(request))

    def test_selected_ring_hit_matches_when_any_ring_atom_is_selected(self) -> None:
        request = self._request(
            hit=StructureHit(kind="ring"),
            selected_atom_ids=frozenset({2}),
            ring_atom_ids=(1, 2, 3, 4, 5, 6),
        )

        self.assertTrue(selection_hit_matches(request))

    def test_selected_other_hit_uses_item_selected_flag(self) -> None:
        request = self._request(
            hit=StructureHit(kind="other"),
            item_is_selected=True,
        )

        self.assertTrue(selection_hit_matches(request))

    def test_unselected_structure_hit_does_not_match(self) -> None:
        request = self._request(
            hit=StructureHit(kind="bond", id=4),
            selected_atom_ids=frozenset(),
            selected_bond_ids=frozenset(),
            bond_atom_ids=(20, 21),
        )

        self.assertFalse(selection_hit_matches(request))


if __name__ == "__main__":
    unittest.main()
