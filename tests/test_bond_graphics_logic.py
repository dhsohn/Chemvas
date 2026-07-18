import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.domain.document import Bond
from chemvas.features.rendering import refresh_bond_graphics


class _FakeSelectableItem:
    def __init__(self, *, selected: bool = False) -> None:
        self._selected = selected

    def isSelected(self) -> bool:
        return self._selected

    def setSelected(self, selected: bool) -> None:
        self._selected = selected


class BondGraphicsLogicTest(unittest.TestCase):
    def test_refresh_bond_graphics_returns_false_for_invalid_or_missing_bond(
        self,
    ) -> None:
        removed: list[object] = []
        add_calls: list[int] = []
        redraw_calls: list[tuple[int, int | None]] = []
        bond_items: dict[int, list[object]] = {0: ["old"]}

        self.assertFalse(
            refresh_bond_graphics(
                9,
                bonds=[Bond(1, 2, 1)],
                bond_items=bond_items,
                remove_scene_item=removed.append,
                add_bond_graphics=add_calls.append,
                redraw_connected=True,
                redraw_connected_bonds=lambda atom_id, skip_bond_id: (
                    redraw_calls.append((atom_id, skip_bond_id))
                ),
            )
        )
        self.assertFalse(
            refresh_bond_graphics(
                0,
                bonds=[None],
                bond_items=bond_items,
                remove_scene_item=removed.append,
                add_bond_graphics=add_calls.append,
                redraw_connected=True,
                redraw_connected_bonds=lambda atom_id, skip_bond_id: (
                    redraw_calls.append((atom_id, skip_bond_id))
                ),
            )
        )

        self.assertEqual(removed, [])
        self.assertEqual(add_calls, [])
        self.assertEqual(redraw_calls, [])
        self.assertEqual(bond_items[0], ["old"])

    def test_refresh_bond_graphics_preserves_selection_and_redraws_neighbors(
        self,
    ) -> None:
        removed: list[object] = []
        add_calls: list[int] = []
        redraw_calls: list[tuple[int, int | None]] = []
        original_a = _FakeSelectableItem(selected=True)
        original_b = _FakeSelectableItem()
        replacement = _FakeSelectableItem()
        bond_items: dict[int, list[object]] = {0: [original_a, original_b]}

        def add_bond_graphics(bond_id: int) -> None:
            add_calls.append(bond_id)
            bond_items[bond_id] = [replacement]

        self.assertTrue(
            refresh_bond_graphics(
                0,
                bonds=[Bond(1, 2, 1)],
                bond_items=bond_items,
                remove_scene_item=removed.append,
                add_bond_graphics=add_bond_graphics,
                redraw_connected=True,
                redraw_connected_bonds=lambda atom_id, skip_bond_id: (
                    redraw_calls.append((atom_id, skip_bond_id))
                ),
            )
        )

        self.assertEqual(removed, [original_a, original_b])
        self.assertEqual(add_calls, [0])
        self.assertEqual(bond_items[0], [replacement])
        self.assertTrue(replacement.isSelected())
        self.assertEqual(redraw_calls, [(1, 0), (2, 0)])

    def test_refresh_bond_graphics_tolerates_non_selectable_original_items(
        self,
    ) -> None:
        removed: list[object] = []
        add_calls: list[int] = []
        original = object()
        replacement = object()
        bond_items: dict[int, list[object]] = {0: [original]}

        def add_bond_graphics(bond_id: int) -> None:
            add_calls.append(bond_id)
            bond_items[bond_id] = [replacement]

        self.assertTrue(
            refresh_bond_graphics(
                0,
                bonds=[Bond(1, 2, 1)],
                bond_items=bond_items,
                remove_scene_item=removed.append,
                add_bond_graphics=add_bond_graphics,
            )
        )

        self.assertEqual(removed, [original])
        self.assertEqual(add_calls, [0])
        self.assertEqual(bond_items[0], [replacement])

    def test_refresh_bond_graphics_skips_selection_restore_for_non_selectable_replacements(
        self,
    ) -> None:
        removed: list[object] = []
        original = _FakeSelectableItem(selected=True)
        replacement = object()
        bond_items: dict[int, list[object]] = {0: [original]}

        def add_bond_graphics(bond_id: int) -> None:
            bond_items[bond_id] = [replacement]

        self.assertTrue(
            refresh_bond_graphics(
                0,
                bonds=[Bond(1, 2, 1)],
                bond_items=bond_items,
                remove_scene_item=removed.append,
                add_bond_graphics=add_bond_graphics,
            )
        )

        self.assertEqual(removed, [original])
        self.assertEqual(bond_items[0], [replacement])


if __name__ == "__main__":
    unittest.main()
