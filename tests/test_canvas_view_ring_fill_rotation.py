import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.domain.document import Atom
    from chemvas.ui.canvas_ring_fill_scene_access import (
        rotate_ring_fills_3d_for,
        rotate_ring_fills_for,
    )
    from chemvas.ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService
    from chemvas.ui.canvas_scene_items_state import set_scene_item_collection_for


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


def _attach_ring_fill_service(view) -> None:
    view.services = SimpleNamespace(
        canvas_ring_fill_scene_service=CanvasRingFillSceneService(view)
    )


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewRingFillRotationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_rotate_ring_fills_returns_when_no_atom_points(self) -> None:
        ring_item = _FakeRingItem([1, 2, 3], [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)])
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={99: Atom("C", 9.0, 9.0)}),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=12.0)),
        )
        set_scene_item_collection_for(view, "ring_items", [ring_item])
        _attach_ring_fill_service(view)

        rotate_ring_fills_for(view, {1, 2}, QPointF(0.0, 0.0), math.pi / 2.0)
        rotate_ring_fills_3d_for(
            view, {1, 2}, (0.0, 0.0, 0.0), math.pi / 4.0, math.pi / 4.0, 1.0
        )

        ring_item.setPolygon.assert_not_called()

    def test_rotate_ring_fills_updates_only_matching_list_rings_and_skips_short_points(
        self,
    ) -> None:
        matching_ring = _FakeRingItem([1, 2, 3])
        short_ring = _FakeRingItem([1, 2, 99])
        non_matching_ring = _FakeRingItem([4, 5, 6])
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
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=12.0)),
        )
        set_scene_item_collection_for(
            view, "ring_items", [matching_ring, short_ring, non_matching_ring]
        )
        _attach_ring_fill_service(view)

        rotate_ring_fills_for(view, {1, 2, 3}, QPointF(0.0, 0.0), math.pi / 2.0)

        self.assertEqual(
            _polygon_points(matching_ring.setPolygon.call_args.args[0]),
            [(0.0, 0.0), (2.0, 0.0), (1.0, 1.5)],
        )
        short_ring.setPolygon.assert_not_called()
        non_matching_ring.setPolygon.assert_not_called()

    def test_rotate_ring_fills_skips_nonmatching_polygon_ring_and_rotates_matching_ring(
        self,
    ) -> None:
        matching_ring = _FakeRingItem(None, [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0)])
        skipped_ring = _FakeRingItem(None, [(9.0, 9.0), (11.0, 9.0), (9.0, 11.0)])
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 0.0, 2.0),
                }
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=8.0)),
        )
        set_scene_item_collection_for(view, "ring_items", [matching_ring, skipped_ring])
        _attach_ring_fill_service(view)

        rotate_ring_fills_for(view, {1, 2, 3}, QPointF(1.0, 1.0), math.pi / 2.0)

        self.assertEqual(
            _polygon_points(matching_ring.setPolygon.call_args.args[0]),
            [(2.0, 0.0), (2.0, 2.0), (0.0, 0.0)],
        )
        skipped_ring.setPolygon.assert_not_called()

    def test_rotate_ring_fills_3d_skips_nonmatching_polygon_ring_and_rotates_matching_ring(
        self,
    ) -> None:
        matching_ring = _FakeRingItem(None, [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0)])
        skipped_ring = _FakeRingItem(None, [(9.0, 9.0), (11.0, 9.0), (9.0, 11.0)])
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 0.0, 2.0),
                }
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=8.0)),
        )
        set_scene_item_collection_for(view, "ring_items", [matching_ring, skipped_ring])
        _attach_ring_fill_service(view)

        rotate_ring_fills_3d_for(
            view, {1, 2, 3}, (1.0, 1.0, 0.0), 0.0, math.pi / 2.0, 1.0
        )

        self.assertEqual(len(matching_ring.setPolygon.call_args.args[0]), 3)
        self.assertNotEqual(
            _polygon_points(matching_ring.polygon()),
            [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0)],
        )
        skipped_ring.setPolygon.assert_not_called()
