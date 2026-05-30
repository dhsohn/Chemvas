import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPolygonF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QPointF = None
    Qt = None
    QBrush = None
    QColor = None
    QPolygonF = None

if QApplication is not None:
    from core.model import Atom
    from ui.canvas_ring_fill_scene_service import (
        CanvasRingFillSceneService,
        canvas_ring_fill_scene_service_for,
    )
else:
    CanvasRingFillSceneService = None
    canvas_ring_fill_scene_service_for = None


class _FakeRingItem:
    def __init__(self, atom_ids=None, points=()) -> None:
        self._atom_ids = atom_ids
        self._polygon = QPolygonF([QPointF(x, y) for x, y in points])
        self.setPolygon = mock.Mock(side_effect=self._set_polygon)

    def _set_polygon(self, polygon) -> None:
        self._polygon = QPolygonF(polygon)

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None

    def polygon(self):
        return QPolygonF(self._polygon)


def _polygon_points(polygon) -> list[tuple[float, float]]:
    return [(round(point.x(), 6), round(point.y(), 6)) for point in polygon]


@unittest.skipUnless(
    QApplication is not None and CanvasRingFillSceneService is not None,
    "PyQt6 and the ring fill scene service are required for tests",
)
class CanvasRingFillSceneServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_update_ring_fills_for_atoms_updates_matching_ring_polygons(self) -> None:
        matching_ring = _FakeRingItem([1, 2, 3])
        non_matching_ring = _FakeRingItem([4, 5, 6])
        invalid_ring = _FakeRingItem("bad")
        canvas = SimpleNamespace(
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

        service = CanvasRingFillSceneService(canvas)
        service.update_ring_fills_for_atoms({1, 2, 3})

        matching_ring.setPolygon.assert_called_once()
        polygon = matching_ring.setPolygon.call_args.args[0]
        self.assertEqual(
            _polygon_points(polygon),
            [(0.0, 0.0), (2.0, 0.0), (1.0, 1.5)],
        )
        non_matching_ring.setPolygon.assert_not_called()
        invalid_ring.setPolygon.assert_not_called()

    def test_update_ring_fills_for_atoms_skips_missing_atoms_and_short_polygons(self) -> None:
        short_ring = _FakeRingItem([1, 2, 99])
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                }
            ),
            ring_items=[short_ring],
        )

        CanvasRingFillSceneService(canvas).update_ring_fills_for_atoms({1, 2, 99})

        short_ring.setPolygon.assert_not_called()

    def test_rotate_ring_fills_returns_when_no_atom_points(self) -> None:
        ring_item = _FakeRingItem([1, 2, 3], [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)])
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={99: Atom("C", 9.0, 9.0)}),
            ring_items=[ring_item],
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=12.0)),
        )

        service = CanvasRingFillSceneService(canvas)
        service.rotate_ring_fills({1, 2}, QPointF(0.0, 0.0), math.pi / 2.0)
        service.rotate_ring_fills_3d({1, 2}, (0.0, 0.0, 0.0), math.pi / 4.0, math.pi / 4.0, 1.0)

        ring_item.setPolygon.assert_not_called()

    def test_rotate_ring_fills_updates_only_matching_list_rings_and_skips_short_points(self) -> None:
        matching_ring = _FakeRingItem([1, 2, 3])
        short_ring = _FakeRingItem([1, 2, 99])
        non_matching_ring = _FakeRingItem([4, 5, 6])
        canvas = SimpleNamespace(
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
            ring_items=[matching_ring, short_ring, non_matching_ring],
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=12.0)),
        )

        CanvasRingFillSceneService(canvas).rotate_ring_fills({1, 2, 3}, QPointF(0.0, 0.0), math.pi / 2.0)

        self.assertEqual(
            _polygon_points(matching_ring.setPolygon.call_args.args[0]),
            [(0.0, 0.0), (2.0, 0.0), (1.0, 1.5)],
        )
        short_ring.setPolygon.assert_not_called()
        non_matching_ring.setPolygon.assert_not_called()

    def test_rotate_ring_fills_skips_nonmatching_polygon_ring_and_rotates_matching_ring(self) -> None:
        matching_ring = _FakeRingItem(None, [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0)])
        skipped_ring = _FakeRingItem(None, [(9.0, 9.0), (11.0, 9.0), (9.0, 11.0)])
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 0.0, 2.0),
                }
            ),
            ring_items=[matching_ring, skipped_ring],
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=8.0)),
        )

        CanvasRingFillSceneService(canvas).rotate_ring_fills({1, 2, 3}, QPointF(1.0, 1.0), math.pi / 2.0)

        self.assertEqual(
            _polygon_points(matching_ring.setPolygon.call_args.args[0]),
            [(2.0, 0.0), (2.0, 2.0), (0.0, 0.0)],
        )
        skipped_ring.setPolygon.assert_not_called()

    def test_rotate_ring_fills_3d_skips_nonmatching_polygon_ring_and_rotates_matching_ring(self) -> None:
        matching_ring = _FakeRingItem(None, [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0)])
        skipped_ring = _FakeRingItem(None, [(9.0, 9.0), (11.0, 9.0), (9.0, 11.0)])
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 0.0, 2.0),
                }
            ),
            ring_items=[matching_ring, skipped_ring],
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=8.0)),
        )

        CanvasRingFillSceneService(canvas).rotate_ring_fills_3d(
            {1, 2, 3},
            (1.0, 1.0, 0.0),
            0.0,
            math.pi / 2.0,
            1.0,
        )

        self.assertEqual(len(matching_ring.setPolygon.call_args.args[0]), 3)
        self.assertNotEqual(_polygon_points(matching_ring.polygon()), [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0)])
        skipped_ring.setPolygon.assert_not_called()

    def test_rotate_ring_fills_3d_skips_nonmatching_and_short_list_backed_rings(self) -> None:
        short_ring = _FakeRingItem([1, 2, 99])
        skipped_ring = _FakeRingItem([7, 8, 9])
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    7: Atom("O", 9.0, 9.0),
                    8: Atom("O", 10.0, 9.0),
                    9: Atom("O", 9.0, 10.0),
                }
            ),
            ring_items=[short_ring, skipped_ring],
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=8.0)),
        )

        CanvasRingFillSceneService(canvas).rotate_ring_fills_3d(
            {1, 2, 99},
            (1.0, 1.0, 0.0),
            math.pi / 4.0,
            math.pi / 4.0,
            1.0,
        )

        short_ring.setPolygon.assert_not_called()
        skipped_ring.setPolygon.assert_not_called()

    def test_create_ring_fill_item_sets_metadata_and_selectable_contract(self) -> None:
        brush = QBrush(QColor("#f3ead7"))
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(ring_fill_brush=mock.Mock(return_value=brush)),
            _make_selectable=mock.Mock(),
        )

        item = CanvasRingFillSceneService(canvas).create_ring_fill_item(
            [QPointF(0.0, 0.0), QPointF(2.0, 0.0), QPointF(1.0, 1.5)],
            [1, 2, 3],
        )

        self.assertEqual(item.data(0), "ring")
        self.assertEqual(item.data(2), [1, 2, 3])
        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(item.brush().color().name(), brush.color().name())
        canvas._make_selectable.assert_called_once_with(item)

    def test_service_resolver_returns_bound_service(self) -> None:
        canvas = SimpleNamespace()
        bound = CanvasRingFillSceneService(canvas)
        canvas._canvas_ring_fill_scene_service = bound
        self.assertIs(canvas_ring_fill_scene_service_for(canvas), bound)

        injected = SimpleNamespace(
            update_ring_fills_for_atoms=mock.Mock(),
            rotate_ring_fills_3d=mock.Mock(),
            rotate_ring_fills=mock.Mock(),
            create_ring_fill_item=mock.Mock(),
        )
        other_canvas = SimpleNamespace(_canvas_ring_fill_scene_service=injected)
        self.assertIs(canvas_ring_fill_scene_service_for(other_canvas), injected)

        placeholder = object()
        fresh_canvas = SimpleNamespace(_canvas_ring_fill_scene_service=placeholder)
        self.assertIs(canvas_ring_fill_scene_service_for(fresh_canvas), placeholder)


if __name__ == "__main__":
    unittest.main()
