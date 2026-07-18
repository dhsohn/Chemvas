import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPen
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsEllipseItem,
        QGraphicsLineItem,
        QGraphicsScene,
    )
except ModuleNotFoundError:
    QApplication = None
    QGraphicsEllipseItem = None
    QGraphicsLineItem = None
    QGraphicsScene = None

if QApplication is not None:
    from chemvas.ui.benzene_preview_renderer import (
        _apply_preview_style,
        clear_benzene_preview,
        rebuild_benzene_preview,
    )
    from chemvas.ui.graphics_items import NoSelectLineItem


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for benzene preview renderer tests"
)
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

        def create_inner_bond_item(
            point: QPointF, next_point: QPointF, center: QPointF
        ) -> QGraphicsLineItem:
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
        inner_lines = [
            item
            for item in items
            if isinstance(item, QGraphicsLineItem)
            and not isinstance(item, NoSelectLineItem)
        ]
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

    def test_rebuild_benzene_preview_replaces_existing_items_when_pool_is_passed(
        self,
    ) -> None:
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
        moved_dots = [
            item for item in moved_items if isinstance(item, QGraphicsEllipseItem)
        ]
        self.assertAlmostEqual(moved_dots[0].rect().center().x(), 32.0, places=3)
        self.assertAlmostEqual(moved_dots[0].rect().center().y(), -5.0, places=3)

    def test_clear_benzene_preview_removes_scene_items_and_returns_empty_pool(
        self,
    ) -> None:
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

    def test_clear_benzene_preview_skips_detached_and_runtime_error_items(self) -> None:
        other_scene = QGraphicsScene()
        detached = QGraphicsLineItem(0.0, 0.0, 1.0, 1.0)
        other_scene.addItem(detached)

        class _DisposedItem:
            def scene(self):
                raise RuntimeError("disposed")

        cleared_items = clear_benzene_preview(self.scene, [detached, _DisposedItem()])

        self.assertEqual(cleared_items, [])
        self.assertIs(detached.scene(), other_scene)

    def test_rebuild_benzene_preview_covers_empty_ring_inner_none_and_brush_style_updates(
        self,
    ) -> None:
        original_items = rebuild_benzene_preview(
            self.scene,
            _hexagon_points(radius=7.0),
            base_pen=self.base_pen,
            atom_radius=1.0,
            create_inner_bond_item=lambda point, next_point, center: QGraphicsLineItem(
                point.x(), point.y(), center.x(), center.y()
            ),
        )

        self.assertEqual(
            rebuild_benzene_preview(
                self.scene,
                [],
                base_pen=self.base_pen,
                atom_radius=1.0,
                create_inner_bond_item=lambda point, next_point, center: None,
                existing_items=original_items,
            ),
            [],
        )
        self.assertEqual(len(self.scene.items()), 0)

        call_count = 0

        def create_inner_bond_item(
            point: QPointF, next_point: QPointF, center: QPointF
        ):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return None
            item = QGraphicsEllipseItem(center.x() - 1.0, center.y() - 1.0, 2.0, 2.0)
            item.setPen(QPen(QColor("#112233")))
            item.setBrush(QColor("#445566"))
            return item

        items = rebuild_benzene_preview(
            self.scene,
            _hexagon_points(radius=9.0),
            base_pen=self.base_pen,
            atom_radius=-2.0,
            create_inner_bond_item=create_inner_bond_item,
        )

        inner_dots = [
            item
            for item in items
            if isinstance(item, QGraphicsEllipseItem) and item.rect().width() == 2.0
        ]
        atom_dots = [
            item
            for item in items
            if isinstance(item, QGraphicsEllipseItem) and item.rect().width() == 0.0
        ]
        self.assertEqual(call_count, 3)
        self.assertEqual(len(inner_dots), 2)
        self.assertEqual(len(atom_dots), 6)
        self.assertEqual(inner_dots[0].pen().color(), QColor(120, 120, 120, 140))
        self.assertEqual(inner_dots[0].brush().color(), QColor(120, 120, 120, 140))

    def test_apply_preview_style_skips_items_without_pen_and_no_brush_fill(
        self,
    ) -> None:
        class _BrushOnlyItem:
            def __init__(self) -> None:
                self._brush = QBrush(Qt.BrushStyle.NoBrush)
                self.set_brush_calls = 0

            def brush(self):
                return QBrush(self._brush)

            def setBrush(self, brush) -> None:
                self.set_brush_calls += 1
                self._brush = QBrush(brush)

        item = _BrushOnlyItem()

        _apply_preview_style(item, QColor("#abcdef"))

        self.assertEqual(item.set_brush_calls, 0)


def _hexagon_points(
    *, radius: float, center: tuple[float, float] = (0.0, 0.0)
) -> list[QPointF]:
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
