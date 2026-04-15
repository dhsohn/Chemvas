import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor, QPen, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsLineItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
    )
except ModuleNotFoundError:
    QApplication = None
    QGraphicsLineItem = None
    QGraphicsPolygonItem = None
    QGraphicsScene = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.bond_preview_renderer import (
        BondPreviewBuildResolvers,
        BondPreviewConfig,
        BondPreviewUpdateResolvers,
        add_bond_preview_items,
        build_bond_preview_items,
        clear_bond_preview_items,
        update_bond_preview_items,
    )
    from ui.graphics_items import NoSelectLineItem


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for bond preview renderer tests")
class BondPreviewRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_build_single_preview_returns_line_item_with_pen(self) -> None:
        items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(12.0, 4.0),
            config=_config(style="single", order=1),
            a_id=None,
            b_id=None,
            resolvers=_build_resolvers(),
        )

        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], NoSelectLineItem)
        self.assertEqual(items[0].pen().color(), QColor("#224466"))

    def test_update_single_preview_reuses_existing_line(self) -> None:
        item = QGraphicsLineItem(0.0, 0.0, 10.0, 0.0)

        updated = update_bond_preview_items(
            [item],
            QPointF(2.0, 3.0),
            QPointF(16.0, 7.0),
            config=_config(style="single", order=1),
            a_id=None,
            b_id=None,
            resolvers=_update_resolvers(),
        )

        self.assertTrue(updated)
        self.assertEqual((item.line().x1(), item.line().y1(), item.line().x2(), item.line().y2()), (2.0, 3.0, 16.0, 7.0))

    def test_build_bold_parallel_preview_replaces_first_segment_with_strip(self) -> None:
        items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(14.0, 0.0),
            config=_config(style="bold_out", order=2),
            a_id=1,
            b_id=2,
            resolvers=_build_resolvers(),
        )

        self.assertEqual(len(items), 2)
        self.assertIsInstance(items[0], QGraphicsPolygonItem)
        self.assertIsInstance(items[1], QGraphicsLineItem)

    def test_update_hash_preview_returns_false_when_item_count_mismatches(self) -> None:
        items = [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0), QGraphicsLineItem(0.0, 1.0, 1.0, 1.0)]

        updated = update_bond_preview_items(
            items,
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            config=_config(style="hash", order=1),
            a_id=None,
            b_id=None,
            resolvers=_update_resolvers(),
        )

        self.assertFalse(updated)

    def test_add_and_clear_bond_preview_items_manage_scene_pool(self) -> None:
        scene = QGraphicsScene()
        items = [
            NoSelectLineItem(0.0, 0.0, 8.0, 0.0),
            QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 2.0), QPointF(4.0, -2.0)])),
        ]

        added = add_bond_preview_items(scene, items)
        cleared = clear_bond_preview_items(scene, added)

        self.assertEqual(len(added), 2)
        self.assertEqual(len(scene.items()), 0)
        self.assertEqual(cleared, [])
        self.assertTrue(all(item.scene() is None for item in added))


def _config(*, style: str, order: int) -> BondPreviewConfig:
    return BondPreviewConfig(
        style=style,
        order=order,
        bond_length_px=20.0,
        bond_line_width=1.2,
        bold_bond_width=2.4,
        hash_spacing_px=4.0,
    )


def _build_resolvers() -> BondPreviewBuildResolvers:
    return BondPreviewBuildResolvers(
        draw_wedge_bond=lambda *args: [QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(6.0, 0.0), QPointF(3.0, 3.0)]))],
        draw_hash_bond=lambda *args: [QGraphicsLineItem(0.0, 0.0, 4.0, 0.0), QGraphicsLineItem(0.0, 1.0, 4.0, 1.0)],
        draw_parallel_bonds=lambda *args: [QGraphicsLineItem(0.0, 0.0, 10.0, 0.0), QGraphicsLineItem(0.0, 1.0, 10.0, 1.0)],
        line_normal=lambda *args: (0.0, 1.0),
        one_sided_bond_strip=lambda *args: QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 2.0), QPointF(0.0, 2.0)])
        ),
        bond_pen=lambda: QPen(QColor("#224466")),
    )


def _update_resolvers() -> BondPreviewUpdateResolvers:
    return BondPreviewUpdateResolvers(
        wedge_polygon=lambda *args: QPolygonF([QPointF(0.0, 0.0), QPointF(8.0, 0.0), QPointF(4.0, 4.0)]),
        hash_segments=lambda *args: ((0.0, 0.0, 4.0, 0.0), (0.0, 1.0, 4.0, 1.0), (0.0, 2.0, 4.0, 2.0)),
        parallel_bond_segments=lambda *args: ((0.0, 0.0, 10.0, 0.0), (0.0, 1.0, 10.0, 1.0)),
        line_normal=lambda *args: (0.0, 1.0),
        strip_polygon=lambda *args: QPolygonF([QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 2.0), QPointF(0.0, 2.0)]),
    )


if __name__ == "__main__":
    unittest.main()
