import math
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor, QPen
    from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsScene
except ModuleNotFoundError:
    QApplication = None
    QGraphicsEllipseItem = None
    QGraphicsLineItem = None
    QGraphicsScene = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.benzene_preview_renderer import clear_benzene_preview, rebuild_benzene_preview
    from ui.graphics_items import NoSelectLineItem


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for benzene preview renderer tests")
class BenzenePreviewRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.scene = QGraphicsScene()
        self.base_pen = QPen(QColor("#224466"))

    def test_rebuild_benzene_preview_returns_full_item_pool(self) -> None:
        ring_points = _hexagon_points(radius=10.0)
        calls: list[tuple[QPointF, QPointF, QPointF]] = []

        def create_inner_bond_item(point: QPointF, next_point: QPointF, center: QPointF) -> QGraphicsLineItem:
            calls.append((point, next_point, center))
            return QGraphicsLineItem(point.x(), point.y(), center.x(), center.y())

        items = rebuild_benzene_preview(
            self.scene,
            ring_points,
            base_pen=self.base_pen,
            atom_radius=1.5,
            create_inner_bond_item=create_inner_bond_item,
        )

        outer_lines = [item for item in items if isinstance(item, NoSelectLineItem)]
        inner_lines = [item for item in items if isinstance(item, QGraphicsLineItem) and not isinstance(item, NoSelectLineItem)]
        dots = [item for item in items if isinstance(item, QGraphicsEllipseItem)]

        self.assertEqual(len(calls), 3)
        self.assertEqual(len(items), 15)
        self.assertEqual(len(outer_lines), 6)
        self.assertEqual(len(inner_lines), 3)
        self.assertEqual(len(dots), 6)
        self.assertEqual(len(self.scene.items()), 15)
        self.assertTrue(all(item.scene() is self.scene for item in items))
        self.assertTrue(all(item.opacity() == 0.5 for item in items))
        self.assertEqual(outer_lines[0].pen().color(), QColor(120, 120, 120, 140))
        self.assertEqual(inner_lines[0].pen().color(), QColor(120, 120, 120, 140))
        self.assertEqual(dots[0].brush().color(), QColor(120, 120, 120, 140))
        self.assertAlmostEqual(calls[0][2].x(), 0.0, places=4)
        self.assertAlmostEqual(calls[0][2].y(), 0.0, places=4)

    def test_rebuild_benzene_preview_replaces_existing_items_when_pool_is_passed(self) -> None:
        original_items = rebuild_benzene_preview(
            self.scene,
            _hexagon_points(radius=8.0),
            base_pen=self.base_pen,
            atom_radius=1.0,
            create_inner_bond_item=lambda point, next_point, center: QGraphicsLineItem(
                point.x(), point.y(), center.x(), center.y()
            ),
        )

        moved_items = rebuild_benzene_preview(
            self.scene,
            _hexagon_points(radius=12.0, center=(20.0, -5.0)),
            base_pen=self.base_pen,
            atom_radius=2.0,
            create_inner_bond_item=lambda point, next_point, center: QGraphicsLineItem(
                point.x(), point.y(), center.x(), center.y()
            ),
            existing_items=original_items,
        )

        self.assertEqual(len(original_items), 15)
        self.assertEqual(len(moved_items), 15)
        self.assertTrue(all(item.scene() is None for item in original_items))
        self.assertTrue(all(item.scene() is self.scene for item in moved_items))
        self.assertEqual(len(self.scene.items()), 15)
        moved_dots = [item for item in moved_items if isinstance(item, QGraphicsEllipseItem)]
        self.assertAlmostEqual(moved_dots[0].rect().center().x(), 32.0, places=3)
        self.assertAlmostEqual(moved_dots[0].rect().center().y(), -5.0, places=3)

    def test_clear_benzene_preview_removes_scene_items_and_returns_empty_pool(self) -> None:
        items = rebuild_benzene_preview(
            self.scene,
            _hexagon_points(radius=6.0),
            base_pen=self.base_pen,
            atom_radius=0.75,
            create_inner_bond_item=lambda point, next_point, center: QGraphicsLineItem(
                point.x(), point.y(), center.x(), center.y()
            ),
        )

        cleared_items = clear_benzene_preview(self.scene, items)

        self.assertEqual(cleared_items, [])
        self.assertEqual(len(self.scene.items()), 0)
        self.assertTrue(all(item.scene() is None for item in items))


def _hexagon_points(*, radius: float, center: tuple[float, float] = (0.0, 0.0)) -> list[QPointF]:
    cx, cy = center
    return [
        QPointF(
            cx + radius * math.cos(math.radians(angle_degrees)),
            cy + radius * math.sin(math.radians(angle_degrees)),
        )
        for angle_degrees in range(0, 360, 60)
    ]


if __name__ == "__main__":
    unittest.main()
