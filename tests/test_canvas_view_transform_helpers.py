import math
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.canvas_view import CanvasView


class _FakeSelectableItem:
    def __init__(self, kind, data1=None, data2=None) -> None:
        self._kind = kind
        self._data1 = data1
        self._data2 = data2
        self._selected = False

    def data(self, key):
        if key == 0:
            return self._kind
        if key == 1:
            return self._data1
        if key == 2:
            return self._data2
        return None

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)

    def isSelected(self) -> bool:
        return self._selected


class _FakeScene:
    def __init__(self) -> None:
        self.clearSelection = mock.Mock()


class _FakeRingItem:
    def __init__(self, atom_ids) -> None:
        self._atom_ids = atom_ids
        self.setPolygon = mock.Mock()

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewTransformHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_rotate_view_updates_base_transform_and_skips_zero_angle(self) -> None:
        view = SimpleNamespace(
            _base_transform=QTransform(),
            _update_view_transform=mock.Mock(),
        )

        CanvasView.rotate_view(view, 45.0)

        self.assertFalse(view._base_transform.isIdentity())
        view._update_view_transform.assert_called_once_with()

        idle_view = SimpleNamespace(
            _base_transform=QTransform(),
            _update_view_transform=mock.Mock(),
        )
        CanvasView.rotate_view(idle_view, 0.0)
        self.assertTrue(idle_view._base_transform.isIdentity())
        idle_view._update_view_transform.assert_not_called()

    def test_rotate_selection_rotates_atoms_and_updates_dependent_items(self) -> None:
        label_1 = object()
        label_2 = object()
        atom_1 = Atom("C", 1.0, 0.0)
        atom_2 = Atom("O", 0.0, 1.0)
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: atom_1, 2: atom_2},
                bonds=[Bond(1, 2, 1), None],
            ),
            atom_items={1: label_1, 2: label_2},
            _selected_ids=mock.Mock(return_value=(set(), {0, 1, 99})),
            _center_for_atoms=mock.Mock(return_value=QPointF(0.5, 0.5)),
            _position_label=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _rotate_ring_fills=mock.Mock(),
            _update_selection_outline=mock.Mock(),
        )

        CanvasView.rotate_selection(view, 90.0)

        self.assertAlmostEqual(atom_1.x, 1.0)
        self.assertAlmostEqual(atom_1.y, 1.0)
        self.assertAlmostEqual(atom_2.x, 0.0)
        self.assertAlmostEqual(atom_2.y, 0.0)
        self.assertAlmostEqual(view._rotate_ring_fills.call_args.args[2], math.pi / 2.0)
        self.assertEqual(view._rotate_ring_fills.call_args.args[1].x(), 0.5)
        self.assertEqual(view._rotate_ring_fills.call_args.args[1].y(), 0.5)
        self.assertEqual(view._selected_ids.call_count, 1)
        self.assertEqual(
            {call.args[0] for call in view._position_label.call_args_list},
            {label_1, label_2},
        )
        self.assertEqual(
            {
                call.args[0]: (round(call.args[1], 6), round(call.args[2], 6))
                for call in view._position_label.call_args_list
            },
            {label_1: (1.0, 1.0), label_2: (0.0, 0.0)},
        )
        self.assertEqual(
            {call.args[0] for call in view._redraw_connected_bonds.call_args_list},
            {1, 2},
        )
        view._update_selection_outline.assert_called_once_with()

    def test_rotate_selection_skips_when_nothing_can_be_rotated(self) -> None:
        empty_view = SimpleNamespace(
            _selected_ids=mock.Mock(return_value=(set(), set())),
            _center_for_atoms=mock.Mock(),
            _position_label=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _rotate_ring_fills=mock.Mock(),
            _update_selection_outline=mock.Mock(),
        )

        CanvasView.rotate_selection(empty_view, 15.0)

        empty_view._center_for_atoms.assert_not_called()
        empty_view._position_label.assert_not_called()
        empty_view._redraw_connected_bonds.assert_not_called()
        empty_view._rotate_ring_fills.assert_not_called()
        empty_view._update_selection_outline.assert_not_called()

        no_center_view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 2.0, 3.0)}),
            atom_items={1: object()},
            _selected_ids=mock.Mock(return_value=({1}, set())),
            _center_for_atoms=mock.Mock(return_value=None),
            _position_label=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _rotate_ring_fills=mock.Mock(),
            _update_selection_outline=mock.Mock(),
        )

        CanvasView.rotate_selection(no_center_view, 15.0)

        no_center_view._center_for_atoms.assert_called_once_with({1})
        no_center_view._position_label.assert_not_called()
        no_center_view._redraw_connected_bonds.assert_not_called()
        no_center_view._rotate_ring_fills.assert_not_called()
        no_center_view._update_selection_outline.assert_not_called()

    def test_bond_sets_for_atoms_classifies_internal_boundary_and_falls_back_to_model_scan(self) -> None:
        classified_view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    Bond(1, 2, 2),
                    Bond(3, 4, 1),
                    None,
                ]
            ),
            _atom_bond_ids={
                1: {0, 1},
                2: {0, 1},
                3: {2},
            },
        )

        internal, boundary = CanvasView.bond_sets_for_atoms(classified_view, {1, 2, 3})
        self.assertEqual(internal, {0, 1})
        self.assertEqual(boundary, {2})

        fallback_view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    Bond(5, 6, 1),
                    Bond(6, 7, 2),
                    None,
                ]
            ),
            _atom_bond_ids={},
        )

        internal, boundary = CanvasView.bond_sets_for_atoms(fallback_view, {5, 6})
        self.assertEqual(internal, {0})
        self.assertEqual(boundary, {1})
        self.assertEqual(CanvasView.bond_sets_for_atoms(fallback_view, set()), (set(), set()))

    def test_restore_selection_from_ids_selects_atoms_bonds_and_refreshes_outline(self) -> None:
        atom_item = _FakeSelectableItem("atom", 1)
        atom_dot = _FakeSelectableItem("atom", 2)
        bond_item_a = _FakeSelectableItem("bond", 7)
        bond_item_b = _FakeSelectableItem("bond", 7)
        scene = _FakeScene()
        view = SimpleNamespace(
            scene=lambda: scene,
            atom_items={1: atom_item},
            atom_dots={2: atom_dot},
            bond_items={7: [bond_item_a, bond_item_b]},
            _update_selection_outline=mock.Mock(),
        )

        CanvasView._restore_selection_from_ids(view, {1, 2}, {7})

        scene.clearSelection.assert_called_once_with()
        self.assertTrue(atom_item.isSelected())
        self.assertTrue(atom_dot.isSelected())
        self.assertTrue(bond_item_a.isSelected())
        self.assertTrue(bond_item_b.isSelected())
        view._update_selection_outline.assert_called_once_with()

    def test_expand_connected_atoms_returns_transitive_component(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    Bond(2, 3, 1),
                    Bond(4, 5, 1),
                    None,
                ]
            )
        )

        self.assertEqual(CanvasView._expand_connected_atoms(view, {1}), {1, 2, 3})
        self.assertEqual(CanvasView._expand_connected_atoms(view, {4}), {4, 5})
        self.assertEqual(CanvasView._expand_connected_atoms(view, set()), set())

    def test_update_ring_fills_for_atoms_updates_matching_ring_polygons(self) -> None:
        matching_ring = _FakeRingItem([1, 2, 3])
        non_matching_ring = _FakeRingItem([4, 5, 6])
        invalid_ring = _FakeRingItem("bad")
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 1.0, 1.5),
                    4: Atom("O", 9.0, 9.0),
                    5: Atom("O", 10.0, 9.0),
                    6: Atom("O", 9.5, 10.0),
                }
            ),
            ring_items=[matching_ring, non_matching_ring, invalid_ring],
        )

        CanvasView._update_ring_fills_for_atoms(view, {1, 2, 3})

        matching_ring.setPolygon.assert_called_once()
        polygon = matching_ring.setPolygon.call_args.args[0]
        self.assertEqual(
            [(round(point.x(), 6), round(point.y(), 6)) for point in polygon],
            [(0.0, 0.0), (2.0, 0.0), (1.0, 1.5)],
        )
        non_matching_ring.setPolygon.assert_not_called()
        invalid_ring.setPolygon.assert_not_called()
        CanvasView._update_ring_fills_for_atoms(view, set())
        self.assertEqual(matching_ring.setPolygon.call_count, 1)
