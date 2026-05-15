import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QCursor
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.canvas_hit_testing_service import CanvasHitTestingService, canvas_hit_testing_service_for


class _FakeScene:
    def __init__(self, items_at_pos=None) -> None:
        self._items_at_pos = list(items_at_pos or [])

    def items(self, *_args, **_kwargs):
        return list(self._items_at_pos)


class _FakeItem:
    def __init__(self, kind, *, data1=None, data2=None) -> None:
        self._data = {0: kind, 1: data1, 2: data2}

    def data(self, key):
        return self._data.get(key)


class _PositionEvent:
    def position(self):
        return SimpleNamespace(toPoint=lambda: "position-point")


class _PosEvent:
    def pos(self):
        return "pos-point"


def _service_double(**overrides):
    defaults = dict(
        scene_pos_from_event=mock.Mock(),
        item_at_scene_pos=mock.Mock(),
        item_at_event=mock.Mock(),
        grid_cell_size=mock.Mock(),
        cell_coords=mock.Mock(),
        ensure_spatial_index=mock.Mock(),
        rebuild_spatial_index=mock.Mock(),
        find_atom_near=mock.Mock(),
        find_bond_near=mock.Mock(),
        distance_point_to_segment=mock.Mock(),
        nearest_atom_hit=mock.Mock(),
        nearest_bond_hit=mock.Mock(),
        bond_id_from_event=mock.Mock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas hit testing service tests")
class CanvasHitTestingServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_scene_pos_from_event_uses_position_pos_and_cursor_fallback(self) -> None:
        viewport = SimpleNamespace(mapFromGlobal=lambda pos: "global-point" if pos == "cursor-pos" else "other")
        canvas = SimpleNamespace(
            mapToScene=lambda value: QPointF(1.0, 2.0)
            if value == "position-point"
            else QPointF(3.0, 4.0)
            if value == "pos-point"
            else QPointF(5.0, 6.0),
            viewport=lambda: viewport,
        )
        service = CanvasHitTestingService(canvas)

        with mock.patch.object(QCursor, "pos", return_value="cursor-pos"):
            self.assertEqual(service.scene_pos_from_event(_PositionEvent()), QPointF(1.0, 2.0))
            self.assertEqual(service.scene_pos_from_event(_PosEvent()), QPointF(3.0, 4.0))
            self.assertEqual(service.scene_pos_from_event(object()), QPointF(5.0, 6.0))

    def test_item_lookup_prefers_atom_and_falls_back_to_nearby_bond(self) -> None:
        atom_item = _FakeItem("atom")
        canvas = SimpleNamespace(
            scene=lambda: _FakeScene(
                [
                    _FakeItem("selection_outline"),
                    _FakeItem("note_select"),
                    _FakeItem("bond"),
                    _FakeItem("ring"),
                    atom_item,
                ]
            ),
            bond_items={},
            _bond_pick_radius=mock.Mock(return_value=9.0),
        )
        service = CanvasHitTestingService(canvas)
        service.find_bond_near = mock.Mock(return_value=None)

        self.assertIs(service.item_at_scene_pos(QPointF(0.0, 0.0)), atom_item)

        nearby_bond_graphic = _FakeItem("bond_graphic")
        fallback_canvas = SimpleNamespace(
            scene=lambda: _FakeScene([_FakeItem("note_box"), _FakeItem("other")]),
            bond_items={4: [nearby_bond_graphic]},
            _bond_pick_radius=mock.Mock(return_value=7.0),
        )
        fallback_service = CanvasHitTestingService(fallback_canvas)
        fallback_service.find_bond_near = mock.Mock(return_value=4)

        self.assertIs(fallback_service.item_at_scene_pos(QPointF(2.0, 2.0)), nearby_bond_graphic)

        empty_fallback_canvas = SimpleNamespace(
            scene=lambda: _FakeScene([_FakeItem("note_box"), _FakeItem("other")]),
            bond_items={4: []},
            _bond_pick_radius=mock.Mock(return_value=7.0),
        )
        empty_fallback_service = CanvasHitTestingService(empty_fallback_canvas)
        empty_fallback_service.find_bond_near = mock.Mock(return_value=4)

        self.assertEqual(empty_fallback_service.item_at_scene_pos(QPointF(2.0, 2.0)).data(0), "other")

    def test_spatial_index_helpers_rebuild_and_find_atom_and_bond(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 10.0, 0.0),
                    3: Atom("N", 50.0, 50.0),
                },
                bonds=[Bond(1, 2, 1), None],
            ),
            _spatial_index_dirty=True,
            _spatial_cell_size=0.0,
            _atom_grid={},
            _bond_grid={},
        )
        service = CanvasHitTestingService(canvas)

        self.assertEqual(service.grid_cell_size(), 20.0)
        self.assertEqual(service.cell_coords(21.0, -1.0, 10.0), (2, -1))

        service.ensure_spatial_index()

        self.assertFalse(canvas._spatial_index_dirty)
        self.assertEqual(canvas._spatial_cell_size, 20.0)
        self.assertEqual(service.find_atom_near(1.0, 1.0, 5.0), 1)
        self.assertEqual(service.find_bond_near(QPointF(5.0, 2.0), 4.0), 0)
        self.assertIsNone(service.find_bond_near(QPointF(40.0, 40.0), 4.0))

    def test_spatial_index_and_nearest_helpers_cover_missing_sparse_and_zero_cell_paths(self) -> None:
        sparse_canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0)},
                bonds=[Bond(1, 99, 1)],
            ),
            _spatial_index_dirty=True,
            _spatial_cell_size=0.0,
            _atom_grid={},
            _bond_grid={},
        )
        sparse_service = CanvasHitTestingService(sparse_canvas)
        sparse_service.rebuild_spatial_index(20.0)
        self.assertEqual(sparse_canvas._bond_grid, {})

        zero_cell_canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[Bond(1, 2, 1)]),
            _spatial_index_dirty=False,
            _spatial_cell_size=0.0,
            _atom_grid={(0, 0): {1}},
            _bond_grid={(0, 0): {0}},
            _grid_cell_size=lambda: 0.0,
        )
        zero_cell_service = CanvasHitTestingService(zero_cell_canvas)
        self.assertIsNone(zero_cell_service.find_atom_near(0.0, 0.0, 5.0))
        self.assertIsNone(zero_cell_service.find_bond_near(QPointF(0.0, 0.0), 5.0))

        sparse_lookup_canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[None, Bond(1, 99, 1)]),
            _spatial_index_dirty=False,
            _spatial_cell_size=20.0,
            _atom_grid={(0, 0): {9, 1}},
            _bond_grid={(0, 0): {5, 0, 1}},
        )
        sparse_lookup_service = CanvasHitTestingService(sparse_lookup_canvas)
        self.assertEqual(sparse_lookup_service.find_atom_near(0.0, 0.0, 5.0), 1)
        self.assertIsNone(sparse_lookup_service.find_bond_near(QPointF(0.0, 0.0), 5.0))

    def test_nearest_hit_helpers_and_bond_id_from_event_use_canvas_overrides(self) -> None:
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 3.0, 4.0), 2: Atom("O", 10.0, 0.0)},
                bonds=[Bond(1, 2, 1), None],
            ),
            hover_bond_id=7,
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _atom_pick_radius=mock.Mock(return_value=5.0),
            _bond_pick_radius=mock.Mock(return_value=6.0),
            find_atom_near=mock.Mock(return_value=1),
            _find_bond_near=mock.Mock(return_value=0),
            _distance_point_to_segment=mock.Mock(return_value=2.5),
            scene_pos_from_event=mock.Mock(return_value=QPointF(3.0, 4.0)),
        )
        service = CanvasHitTestingService(canvas)

        self.assertEqual(service.nearest_atom_hit(QPointF(0.0, 0.0)), (1, 5.0))
        self.assertEqual(service.nearest_bond_hit(QPointF(5.0, 2.0)), (0, 2.5))
        self.assertEqual(service.bond_id_from_event(object()), 7)

        canvas.hover_bond_id = None
        canvas._find_bond_near.return_value = 2
        self.assertEqual(service.bond_id_from_event(object()), 2)
        canvas._find_bond_near.assert_called_with(QPointF(3.0, 4.0), 7.0)

    def test_helper_prefers_injected_service_double(self) -> None:
        injected = _service_double()
        canvas = SimpleNamespace(_hit_testing_service=injected)

        self.assertIs(canvas_hit_testing_service_for(canvas), injected)


if __name__ == "__main__":
    unittest.main()
