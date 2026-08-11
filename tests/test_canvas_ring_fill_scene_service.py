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
    from chemvas.domain.document import Atom
    from chemvas.ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService
    from chemvas.ui.canvas_scene_items_state import (
        CanvasSceneItemsState,
        set_scene_item_collection_for,
    )

    from tests.runtime_state import canvas_runtime_state
else:
    CanvasRingFillSceneService = None


class _FakeRingItem:
    def __init__(self, atom_ids=None) -> None:
        self._atom_ids = atom_ids
        self.setPolygon = mock.Mock()

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None


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
            runtime_state=canvas_runtime_state(
                scene_items_state=CanvasSceneItemsState()
            ),
        )
        set_scene_item_collection_for(
            canvas, "ring_items", [matching_ring, non_matching_ring, invalid_ring]
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

    def test_update_ring_fills_for_atoms_skips_missing_atoms_and_short_polygons(
        self,
    ) -> None:
        short_ring = _FakeRingItem([1, 2, 99])
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                }
            ),
            runtime_state=canvas_runtime_state(
                scene_items_state=CanvasSceneItemsState()
            ),
        )
        set_scene_item_collection_for(canvas, "ring_items", [short_ring])

        CanvasRingFillSceneService(canvas).update_ring_fills_for_atoms({1, 2, 99})

        short_ring.setPolygon.assert_not_called()

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
        self.assertTrue(item.flags() & item.GraphicsItemFlag.ItemIsSelectable)
        # Ring fills stack behind bonds/labels so an opaque pastel fill never
        # covers the structure.
        self.assertLess(item.zValue(), 0.0)


if __name__ == "__main__":
    unittest.main()
