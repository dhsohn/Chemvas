import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.canvas_move_controller import CanvasMoveController
    from ui.canvas_view import CanvasView


class _FakeItem:
    def __init__(self, kind, *, data1=None, data2=None) -> None:
        self._data = {0: kind, 1: data1, 2: data2}
        self.moves = []
        self.set_data_calls = []

    def data(self, key):
        return self._data.get(key)

    def setData(self, key, value) -> None:
        self._data[key] = value
        self.set_data_calls.append((key, value))

    def moveBy(self, dx: float, dy: float) -> None:
        self.moves.append((dx, dy))


class _FakeRingItem:
    def __init__(self, atom_ids) -> None:
        self._atom_ids = atom_ids
        self.polygons = []

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None

    def setPolygon(self, polygon) -> None:
        self.polygons.append([(round(point.x(), 6), round(point.y(), 6)) for point in polygon])


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewMoveHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_move_item_atom_branch_and_guard_paths(self) -> None:
        missing_item = _FakeItem("atom", data1="bad")
        missing_atom_item = _FakeItem("atom", data1=9)
        atom_item = _FakeItem("atom", data1=1)
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 1.0, 2.0)},
                bonds=[Bond(1, 2, 1), Bond(3, 4, 1), None],
            ),
            _redraw_bond=mock.Mock(),
            _update_selection_outline=mock.Mock(),
        )
        view._move_controller = CanvasMoveController(view)

        CanvasView.move_item(view, missing_item, 2.0, 3.0)
        CanvasView.move_item(view, missing_atom_item, 2.0, 3.0)
        CanvasView.move_item(view, atom_item, 2.0, 3.0, update_selection=False)

        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (3.0, 5.0))
        self.assertEqual(atom_item.moves, [(2.0, 3.0)])
        view._redraw_bond.assert_called_once_with(0)
        view._update_selection_outline.assert_not_called()

    def test_move_item_updates_bond_mark_and_scene_item_payloads(self) -> None:
        bond_item = _FakeItem("bond", data1=0)
        mark_item = _FakeItem("mark", data1={"atom_id": 1})
        orbital_item = _FakeItem("orbital", data1={"center": QPointF(2.0, 3.0)})
        bracket_item = _FakeItem("ts_bracket", data1={"rect": QRectF(1.0, 2.0, 3.0, 4.0)})
        arrow_item = _FakeItem(
            "arrow",
            data2={
                "start": QPointF(0.0, 0.0),
                "end": QPointF(1.0, 1.0),
                "control": QPointF(2.0, 2.0),
            },
        )
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 10.0, 10.0)},
                bonds=[Bond(1, 2, 1), None],
            ),
            _move_atom=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _mark_center=mock.Mock(return_value=QPointF(15.0, 18.0)),
            _update_selection_outline=mock.Mock(),
        )
        view._move_controller = CanvasMoveController(view)

        CanvasView.move_item(view, bond_item, 4.0, -2.0)
        CanvasView.move_item(view, mark_item, 1.0, 2.0)
        CanvasView.move_item(view, orbital_item, -3.0, 5.0)
        CanvasView.move_item(view, bracket_item, 2.0, 2.0)
        CanvasView.move_item(view, arrow_item, 1.5, -0.5)

        view._move_atom.assert_has_calls([mock.call(1, 4.0, -2.0), mock.call(2, 4.0, -2.0)])
        view._redraw_connected_bonds.assert_has_calls([mock.call(1), mock.call(2)])
        self.assertEqual(mark_item.moves, [(1.0, 2.0)])
        self.assertEqual(mark_item.data(1)["dx"], 5.0)
        self.assertEqual(mark_item.data(1)["dy"], 8.0)
        self.assertEqual(orbital_item.data(1)["center"], QPointF(-1.0, 8.0))
        self.assertEqual(bracket_item.data(1)["rect"], QRectF(3.0, 4.0, 3.0, 4.0))
        self.assertEqual(arrow_item.data(2)["start"], QPointF(1.5, -0.5))
        self.assertEqual(arrow_item.data(2)["end"], QPointF(2.5, 0.5))
        self.assertEqual(arrow_item.data(2)["control"], QPointF(3.5, 1.5))
        self.assertEqual(view._update_selection_outline.call_count, 5)

    def test_move_item_covers_bond_mark_and_scene_item_guard_paths(self) -> None:
        invalid_bond_item = _FakeItem("bond", data1="bad")
        missing_bond_item = _FakeItem("bond", data1=1)
        non_int_mark = _FakeItem("mark", data1={"atom_id": "bad"})
        missing_mark_atom = _FakeItem("mark", data1={"atom_id": 9})
        orbital_item = _FakeItem("orbital", data1={"center": (2.0, 3.0)})
        bracket_item = _FakeItem("ts_bracket", data1={"rect": (1.0, 2.0, 3.0, 4.0)})
        arrow_item = _FakeItem(
            "arrow",
            data2={
                "start": "bad",
                "end": QPointF(1.0, 1.0),
                "control": QPointF(2.0, 2.0),
            },
        )
        other_item = _FakeItem("other")
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 10.0, 10.0)},
                bonds=[Bond(1, 2, 1), None],
            ),
            _move_atom=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _mark_center=mock.Mock(return_value=QPointF(15.0, 18.0)),
            _update_selection_outline=mock.Mock(),
        )
        view._move_controller = CanvasMoveController(view)

        CanvasView.move_item(view, invalid_bond_item, 4.0, -2.0)
        CanvasView.move_item(view, missing_bond_item, 4.0, -2.0)
        CanvasView.move_item(view, non_int_mark, 1.0, 2.0)
        CanvasView.move_item(view, missing_mark_atom, 1.0, 2.0)
        CanvasView.move_item(view, orbital_item, -3.0, 5.0)
        CanvasView.move_item(view, bracket_item, 2.0, 2.0)
        CanvasView.move_item(view, arrow_item, 1.5, -0.5)
        CanvasView.move_item(view, other_item, 0.5, 0.5)

        view._move_atom.assert_not_called()
        view._redraw_connected_bonds.assert_not_called()
        self.assertEqual(non_int_mark.moves, [(1.0, 2.0)])
        self.assertEqual(missing_mark_atom.moves, [(1.0, 2.0)])
        self.assertNotIn("dx", non_int_mark.data(1))
        self.assertNotIn("dx", missing_mark_atom.data(1))
        self.assertEqual(orbital_item.data(1)["center"], (2.0, 3.0))
        self.assertEqual(bracket_item.data(1)["rect"], (1.0, 2.0, 3.0, 4.0))
        self.assertEqual(arrow_item.data(2)["start"], "bad")
        self.assertEqual(arrow_item.data(2)["end"], QPointF(1.0, 1.0))
        self.assertEqual(arrow_item.data(2)["control"], QPointF(3.5, 1.5))
        self.assertEqual(view._update_selection_outline.call_count, 6)

    def test_move_atoms_uses_bond_sets_or_falls_back_to_redraw(self) -> None:
        bond_graphic = _FakeItem("bond")
        view = SimpleNamespace(
            bond_items={3: [bond_graphic], 4: []},
            _move_atom=mock.Mock(),
            update_bond_geometry=mock.Mock(),
            _redraw_bonds_for_atoms=mock.Mock(),
            _move_rings_for_atoms=mock.Mock(),
            _update_selection_outline=mock.Mock(),
        )
        view._move_controller = CanvasMoveController(view)

        CanvasView.move_atoms(view, set(), 1.0, 2.0)
        view._move_atom.assert_not_called()

        CanvasView.move_atoms(
            view,
            {1, 2},
            3.0,
            -4.0,
            bond_ids={3, 4},
            redraw_bond_ids={5},
            update_selection=False,
        )

        self.assertEqual({call.args[0] for call in view._move_atom.call_args_list}, {1, 2})
        self.assertEqual(bond_graphic.moves, [(3.0, -4.0)])
        view.update_bond_geometry.assert_called_once_with(5)
        view._move_rings_for_atoms.assert_called_once_with({1, 2}, 3.0, -4.0)
        view._update_selection_outline.assert_not_called()

        view._move_atom.reset_mock()
        view.update_bond_geometry.reset_mock()
        view._move_rings_for_atoms.reset_mock()

        CanvasView.move_atoms(view, {9}, 1.5, 2.5)

        view._move_atom.assert_called_once_with(9, 1.5, 2.5)
        view._redraw_bonds_for_atoms.assert_called_once_with({9})
        view._move_rings_for_atoms.assert_called_once_with({9}, 1.5, 2.5)
        view._update_selection_outline.assert_called_once_with()

    def test_move_rings_for_atoms_updates_only_matching_complete_rings(self) -> None:
        matching_ring = _FakeRingItem([1, 2, 3])
        short_ring = _FakeRingItem([1, 2, 9])
        non_matching_ring = _FakeRingItem([4, 5, 6])
        invalid_ring = _FakeRingItem("bad")
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 1.0, 1.0),
                    4: Atom("O", 9.0, 9.0),
                    5: Atom("O", 10.0, 9.0),
                    6: Atom("O", 9.0, 10.0),
                }
            ),
            ring_items=[matching_ring, short_ring, non_matching_ring, invalid_ring],
        )
        view._move_controller = CanvasMoveController(view)

        CanvasView._move_rings_for_atoms(view, {1, 2, 3}, 10.0, 20.0)

        self.assertEqual(matching_ring.polygons, [[(0.0, 0.0), (2.0, 0.0), (1.0, 1.0)]])
        self.assertEqual(short_ring.polygons, [])
        self.assertEqual(non_matching_ring.polygons, [])
        self.assertEqual(invalid_ring.polygons, [])

    def test_move_atom_updates_model_3d_labels_dots_and_marks(self) -> None:
        label = _FakeItem("atom")
        dot = _FakeItem("dot")
        mark = _FakeItem("mark")
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0)}),
            atom_coords_3d={1: (3.0, 4.0, 5.0)},
            atom_items={1: label},
            atom_dots={1: dot},
            _marks_by_atom={1: [mark]},
            _mark_spatial_index_dirty=mock.Mock(),
        )
        view._move_controller = CanvasMoveController(view)

        CanvasView._move_atom(view, 1, 2.5, -1.5)
        CanvasView._move_atom(view, 9, 2.0, 3.0)

        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (3.5, 0.5))
        self.assertEqual(view.atom_coords_3d[1], (5.5, 2.5, 5.0))
        self.assertEqual(label.moves, [(2.5, -1.5)])
        self.assertEqual(dot.moves, [(2.5, -1.5)])
        self.assertEqual(mark.moves, [(2.5, -1.5)])
        view._mark_spatial_index_dirty.assert_called_once_with()

    def test_move_wrappers_delegate_to_controller(self) -> None:
        view = SimpleNamespace()
        item = _FakeItem("arrow")
        controller = mock.Mock()

        with mock.patch("ui.canvas_view._move_controller_for", return_value=controller):
            CanvasView.move_item(view, item, 1.0, 2.0, update_selection=False)
            CanvasView.move_atoms(view, {1, 2}, 3.0, 4.0, bond_ids={5}, redraw_bond_ids={6}, update_selection=False)
            CanvasView._move_rings_for_atoms(view, {7}, 8.0, 9.0)
            CanvasView._move_atom(view, 10, 11.0, 12.0)

        controller.move_item.assert_called_once_with(item, 1.0, 2.0, update_selection=False)
        controller.move_atoms.assert_called_once_with(
            {1, 2},
            3.0,
            4.0,
            bond_ids={5},
            redraw_bond_ids={6},
            update_selection=False,
        )
        controller.move_rings_for_atoms.assert_called_once_with({7}, 8.0, 9.0)
        controller.move_atom.assert_called_once_with(10, 11.0, 12.0)


if __name__ == "__main__":
    unittest.main()
