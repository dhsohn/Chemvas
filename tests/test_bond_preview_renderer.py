import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPainterPath, QPen, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None
    Qt = None
    QPainterPath = None
    QGraphicsLineItem = None
    QGraphicsPathItem = None
    QGraphicsPolygonItem = None
    QGraphicsScene = None
    QGraphicsTextItem = None

if QApplication is not None:
    from chemvas.ui.bond_preview_renderer import (
        add_bond_preview_items,
        build_bond_preview_items,
        clear_bond_preview_items,
        update_bond_preview_items,
    )
    from chemvas.ui.graphics_items import NoSelectLineItem


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for bond preview renderer tests"
)
class BondPreviewRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_build_single_preview_returns_line_item_with_pen(self) -> None:
        items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(12.0, 4.0),
            style="single",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], NoSelectLineItem)
        self.assertEqual(items[0].pen().color(), QColor("#224466"))

    def test_build_dotted_preview_returns_dotted_path_item(self) -> None:
        items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(12.0, 0.0),
            style="dotted",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], QGraphicsPathItem)
        self.assertFalse(items[0].path().isEmpty())
        self.assertEqual(items[0].pen().style(), Qt.PenStyle.NoPen)

    def test_update_single_preview_reuses_existing_line(self) -> None:
        item = QGraphicsLineItem(0.0, 0.0, 10.0, 0.0)

        updated = update_bond_preview_items(
            [item],
            QPointF(2.0, 3.0),
            QPointF(16.0, 7.0),
            style="single",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertTrue(updated)
        self.assertEqual(
            (item.line().x1(), item.line().y1(), item.line().x2(), item.line().y2()),
            (2.0, 3.0, 16.0, 7.0),
        )

    def test_build_bold_parallel_preview_replaces_first_segment_with_strip(
        self,
    ) -> None:
        items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(14.0, 0.0),
            style="bold_out",
            order=2,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=_bond_renderer(),
        )

        self.assertEqual(len(items), 2)
        self.assertIsInstance(items[0], QGraphicsPolygonItem)
        self.assertIsInstance(items[1], QGraphicsLineItem)

    def test_update_hash_preview_returns_false_when_item_count_mismatches(self) -> None:
        items = [
            QGraphicsLineItem(0.0, 0.0, 1.0, 0.0),
            QGraphicsLineItem(0.0, 1.0, 1.0, 1.0),
        ]

        updated = update_bond_preview_items(
            items,
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="hash",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)

    def test_add_and_clear_bond_preview_items_manage_scene_pool(self) -> None:
        scene = QGraphicsScene()
        items = [
            NoSelectLineItem(0.0, 0.0, 8.0, 0.0),
            QGraphicsPolygonItem(
                QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 2.0), QPointF(4.0, -2.0)])
            ),
        ]

        added = add_bond_preview_items(scene, items)
        cleared = clear_bond_preview_items(scene, added)

        self.assertEqual(len(added), 2)
        self.assertEqual(len(scene.items()), 0)
        self.assertEqual(cleared, [])
        self.assertTrue(all(item.scene() is None for item in added))

    def test_add_bond_preview_items_applies_color_to_pen_and_brush(self) -> None:
        scene = QGraphicsScene()
        line = NoSelectLineItem(0.0, 0.0, 5.0, 0.0)
        line.setPen(QPen(QColor("#000000")))
        polygon = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(3.0, 0.0), QPointF(1.5, 2.0)])
        )
        polygon.setPen(QPen(QColor("#111111")))
        polygon.setBrush(QColor("#222222"))

        color = QColor("#4A6C8E")
        added = add_bond_preview_items(
            scene, [line, polygon], color=color, opacity=0.25, z_value=7.0
        )

        self.assertEqual(len(added), 2)
        self.assertEqual(line.pen().color().name(), color.name())
        self.assertEqual(polygon.pen().color().name(), color.name())
        self.assertEqual(polygon.brush().color().name(), color.name())
        self.assertTrue(all(item.opacity() == 0.25 for item in added))
        self.assertTrue(all(item.zValue() == 7.0 for item in added))

    def test_clear_bond_preview_items_ignores_runtime_error_from_dead_item(
        self,
    ) -> None:
        class DeadItem:
            def scene(self):
                raise RuntimeError("wrapped C/C++ object has been deleted")

        self.assertEqual(clear_bond_preview_items(QGraphicsScene(), [DeadItem()]), [])

    def test_clear_bond_preview_items_leaves_detached_items_untouched(self) -> None:
        scene = QGraphicsScene()
        other_scene = QGraphicsScene()
        detached = QGraphicsLineItem(0.0, 0.0, 1.0, 1.0)
        other_scene.addItem(detached)

        self.assertEqual(clear_bond_preview_items(scene, [detached]), [])
        self.assertIs(detached.scene(), other_scene)

    def test_build_wedge_preview_delegates_to_bond_renderer(self) -> None:
        expected = [QGraphicsPolygonItem()]
        wedge = mock.Mock(return_value=expected)
        bond_renderer = _bond_renderer(
            draw_wedge_bond=wedge,
            draw_hash_bond=mock.Mock(),
            draw_dotted_bond=mock.Mock(),
            draw_parallel_bonds=mock.Mock(),
            line_normal=mock.Mock(),
            one_sided_bond_strip=mock.Mock(),
        )

        items = build_bond_preview_items(
            QPointF(1.0, 2.0),
            QPointF(7.0, 8.0),
            style="wedge",
            order=1,
            canvas_renderer=_renderer(),
            a_id=3,
            b_id=4,
            bond_renderer=bond_renderer,
        )

        self.assertIs(items, expected)
        wedge.assert_called_once_with(1.0, 2.0, 7.0, 8.0, 3, 4)

    def test_build_hash_preview_delegates_to_bond_renderer(self) -> None:
        expected = [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)]
        hashed = mock.Mock(return_value=expected)
        bond_renderer = _bond_renderer(
            draw_wedge_bond=mock.Mock(),
            draw_hash_bond=hashed,
            draw_dotted_bond=mock.Mock(),
            draw_parallel_bonds=mock.Mock(),
            line_normal=mock.Mock(),
            one_sided_bond_strip=mock.Mock(),
        )

        items = build_bond_preview_items(
            QPointF(-2.0, 1.0),
            QPointF(5.0, 6.0),
            style="hash",
            order=1,
            canvas_renderer=_renderer(),
            a_id=9,
            b_id=10,
            bond_renderer=bond_renderer,
        )

        self.assertIs(items, expected)
        hashed.assert_called_once_with(-2.0, 1.0, 5.0, 6.0, 9, 10)

    def test_build_bold_single_preview_uses_atom_to_atom_segment_and_flipped_normal(
        self,
    ) -> None:
        strip = QGraphicsPolygonItem()
        line_normal = mock.Mock(return_value=(0.25, 0.75))
        one_sided = mock.Mock(return_value=strip)
        bond_renderer = _bond_renderer(
            draw_wedge_bond=mock.Mock(),
            draw_hash_bond=mock.Mock(),
            draw_dotted_bond=mock.Mock(),
            draw_parallel_bonds=mock.Mock(),
            line_normal=line_normal,
            one_sided_bond_strip=one_sided,
        )
        start = QPointF(0.0, 0.0)
        end = QPointF(10.0, 0.0)

        items = build_bond_preview_items(
            start,
            end,
            style="bold_out",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=bond_renderer,
        )

        bx1, by1, bx2, by2 = start.x(), start.y(), end.x(), end.y()
        self.assertEqual(items, [strip])
        line_normal.assert_called_once_with(bx1, by1, bx2, by2, None)
        one_sided.assert_called_once_with(bx1, by1, bx2, by2, -0.25, -0.75, 1.2, 2.4)

    def test_build_bold_single_preview_keeps_inward_normal(self) -> None:
        strip = QGraphicsPolygonItem()
        line_normal = mock.Mock(return_value=(0.25, 0.75))
        one_sided = mock.Mock(return_value=strip)

        items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="bold",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(
                line_normal=line_normal,
                one_sided_bond_strip=one_sided,
            ),
        )

        self.assertEqual(items, [strip])
        self.assertEqual(one_sided.call_args.args[4:6], (0.25, 0.75))

    def test_build_bold_parallel_preview_keeps_non_line_first_item(self) -> None:
        first = QGraphicsPolygonItem()
        second = QGraphicsLineItem(0.0, 0.0, 10.0, 1.0)
        draw_parallel = mock.Mock(return_value=[first, second])
        bond_renderer = _bond_renderer(
            draw_wedge_bond=mock.Mock(),
            draw_hash_bond=mock.Mock(),
            draw_dotted_bond=mock.Mock(),
            draw_parallel_bonds=draw_parallel,
            line_normal=mock.Mock(),
            one_sided_bond_strip=mock.Mock(),
        )

        items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(14.0, 0.0),
            style="bold",
            order=2,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=bond_renderer,
        )

        self.assertEqual(items, [first, second])
        draw_parallel.assert_called_once()

    def test_build_bold_default_preview_uses_inward_double_position(self) -> None:
        strip = QGraphicsPolygonItem()
        line_normal = mock.Mock(return_value=(0.25, 0.75))
        one_sided = mock.Mock(return_value=strip)
        bond_renderer = _bond_renderer(
            draw_wedge_bond=mock.Mock(),
            draw_hash_bond=mock.Mock(),
            draw_dotted_bond=mock.Mock(),
            draw_parallel_bonds=lambda *_args: [
                QGraphicsLineItem(0.0, 0.0, 10.0, 0.0),
                QGraphicsLineItem(0.0, 1.0, 10.0, 1.0),
            ],
            line_normal=line_normal,
            one_sided_bond_strip=one_sided,
        )

        items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(14.0, 0.0),
            style="bold",
            order=2,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=bond_renderer,
        )

        self.assertIsInstance(items[0], QGraphicsPolygonItem)
        one_sided.assert_called_once_with(0.0, 0.5, 10.0, 0.5, -0.25, -0.75, 1.2, 2.4)

    def test_build_parallel_nonbold_preview_uses_parallel_bond_renderer(self) -> None:
        expected = [
            QGraphicsLineItem(0.0, 0.0, 8.0, 0.0),
            QGraphicsLineItem(0.0, 1.0, 8.0, 1.0),
        ]
        draw_parallel = mock.Mock(return_value=expected)
        bond_renderer = _bond_renderer(
            draw_wedge_bond=mock.Mock(),
            draw_hash_bond=mock.Mock(),
            draw_dotted_bond=mock.Mock(),
            draw_parallel_bonds=draw_parallel,
            line_normal=mock.Mock(),
            one_sided_bond_strip=mock.Mock(),
        )

        items = build_bond_preview_items(
            QPointF(-1.0, 0.0),
            QPointF(9.0, 0.0),
            style="single",
            order=2,
            canvas_renderer=_renderer(),
            a_id=5,
            b_id=6,
            bond_renderer=bond_renderer,
        )

        self.assertIs(items, expected)
        draw_parallel.assert_called_once_with(-1.0, 0.0, 9.0, 0.0, 2, 5, 6)

    def test_build_plain_double_preview_keeps_long_line_on_single_axis(self) -> None:
        def _parallel_items(*_args):
            return [
                QGraphicsLineItem(0.0, -2.0, 10.0, -2.0),
                QGraphicsLineItem(0.0, 2.0, 10.0, 2.0),
            ]

        bond_renderer = _bond_renderer(
            draw_wedge_bond=mock.Mock(),
            draw_hash_bond=mock.Mock(),
            draw_dotted_bond=mock.Mock(),
            draw_parallel_bonds=mock.Mock(side_effect=_parallel_items),
            line_normal=mock.Mock(),
            one_sided_bond_strip=mock.Mock(),
        )

        default_items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="double",
            order=2,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=bond_renderer,
        )
        outer_items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="double_outer",
            order=2,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=bond_renderer,
        )

        self.assertEqual(
            (default_items[0].line().y1(), default_items[0].line().y2()), (0.0, 0.0)
        )
        self.assertEqual(
            (default_items[1].line().y1(), default_items[1].line().y2()), (4.4, 4.4)
        )
        self.assertEqual(
            (outer_items[0].line().y1(), outer_items[0].line().y2()), (0.0, 0.0)
        )
        self.assertEqual(
            (outer_items[1].line().y1(), outer_items[1].line().y2()), (-4.4, -4.4)
        )

    def test_update_returns_false_for_empty_items(self) -> None:
        updated = update_bond_preview_items(
            [],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="single",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)

    def test_update_wedge_preview_updates_polygon(self) -> None:
        item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.5, 1.0)])
        )

        updated = update_bond_preview_items(
            [item],
            QPointF(0.0, 0.0),
            QPointF(8.0, 2.0),
            style="wedge",
            order=1,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=_bond_renderer(),
        )

        points = [(point.x(), point.y()) for point in item.polygon()]
        self.assertTrue(updated)
        self.assertEqual(points, [(0.0, 0.0), (8.0, 0.0), (4.0, 4.0)])

    def test_update_wedge_preview_returns_false_for_wrong_item_type(self) -> None:
        updated = update_bond_preview_items(
            [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)],
            QPointF(0.0, 0.0),
            QPointF(8.0, 2.0),
            style="wedge",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)

    def test_update_hash_preview_updates_all_segments(self) -> None:
        items = [
            QGraphicsLineItem(0.0, 0.0, 1.0, 0.0),
            QGraphicsLineItem(0.0, 1.0, 1.0, 1.0),
            QGraphicsLineItem(0.0, 2.0, 1.0, 2.0),
        ]

        updated = update_bond_preview_items(
            items,
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="hash",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertTrue(updated)
        self.assertEqual(
            (
                items[2].line().x1(),
                items[2].line().y1(),
                items[2].line().x2(),
                items[2].line().y2(),
            ),
            (0.0, 2.0, 4.0, 2.0),
        )

    def test_update_hash_preview_returns_false_for_non_line_item(self) -> None:
        items = [
            QGraphicsLineItem(0.0, 0.0, 1.0, 0.0),
            QGraphicsPolygonItem(),
            QGraphicsLineItem(0.0, 2.0, 1.0, 2.0),
        ]

        updated = update_bond_preview_items(
            items,
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="hash",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)

    def test_update_bold_parallel_preview_updates_polygon_first_item(self) -> None:
        items = [
            QGraphicsPolygonItem(
                QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.5, 1.0)])
            ),
            QGraphicsLineItem(0.0, 1.0, 1.0, 1.0),
        ]

        updated = update_bond_preview_items(
            items,
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="bold_out",
            order=2,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=_bond_renderer(),
        )

        points = [(point.x(), point.y()) for point in items[0].polygon()]
        self.assertTrue(updated)
        self.assertEqual(points, [(0.0, 0.0), (10.0, 0.0), (10.0, 2.0), (0.0, 2.0)])
        self.assertEqual(
            (
                items[1].line().x1(),
                items[1].line().y1(),
                items[1].line().x2(),
                items[1].line().y2(),
            ),
            (1.2, -0.6000000000000001, 8.8, -0.6000000000000001),
        )

    def test_update_bold_parallel_preview_updates_line_first_item(self) -> None:
        items = [
            QGraphicsLineItem(0.0, 0.0, 1.0, 0.0),
            QGraphicsLineItem(0.0, 1.0, 1.0, 1.0),
        ]

        updated = update_bond_preview_items(
            items,
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="bold",
            order=2,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=_bond_renderer(),
        )

        self.assertTrue(updated)
        self.assertEqual(
            (
                items[0].line().x1(),
                items[0].line().y1(),
                items[0].line().x2(),
                items[0].line().y2(),
            ),
            (0.0, 0.5, 10.0, 0.5),
        )

    def test_update_bold_parallel_preview_returns_false_for_bad_item_shapes(
        self,
    ) -> None:
        updated = update_bond_preview_items(
            [QGraphicsTextItem("bad"), QGraphicsLineItem(0.0, 1.0, 1.0, 1.0)],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="bold",
            order=2,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)

    def test_update_bold_parallel_preview_returns_false_when_segments_are_missing(
        self,
    ) -> None:
        bond_renderer = _bond_renderer(
            wedge_polygon=lambda *args: QPolygonF(),
            hash_segments=lambda *args: (),
            dotted_bond_path=lambda *args: QPainterPath(),
            parallel_bond_segments=lambda *args: (),
            line_normal=lambda *args: (0.0, 1.0),
            strip_polygon=lambda *args: QPolygonF(),
        )

        updated = update_bond_preview_items(
            [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="bold",
            order=2,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=bond_renderer,
        )

        self.assertFalse(updated)

    def test_update_bold_single_preview_updates_line_item(self) -> None:
        item = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)

        updated = update_bond_preview_items(
            [item],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="bold",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        bx1, by1, bx2, by2 = 0.0, 0.0, 10.0, 0.0
        self.assertTrue(updated)
        self.assertEqual(
            (item.line().x1(), item.line().y1(), item.line().x2(), item.line().y2()),
            (bx1, by1, bx2, by2),
        )

    def test_update_bold_single_preview_returns_false_for_bad_first_item(self) -> None:
        updated = update_bond_preview_items(
            [QGraphicsTextItem("bad")],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="bold",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)

    def test_update_dotted_preview_returns_false_for_wrong_item_type(self) -> None:
        updated = update_bond_preview_items(
            [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="dotted",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)

    def test_update_dotted_preview_updates_existing_path_item(self) -> None:
        item = QGraphicsPathItem()

        updated = update_bond_preview_items(
            [item],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="dotted",
            order=1,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=_bond_renderer(),
        )

        self.assertTrue(updated)
        self.assertFalse(item.path().isEmpty())

    def test_update_bold_parallel_preview_returns_false_for_bad_later_item(
        self,
    ) -> None:
        updated = update_bond_preview_items(
            [QGraphicsPolygonItem(), QGraphicsPolygonItem()],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="bold",
            order=2,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)

    def test_update_bold_single_preview_outward_updates_polygon(self) -> None:
        item = QGraphicsPolygonItem()

        updated = update_bond_preview_items(
            [item],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="bold_out",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertTrue(updated)
        self.assertEqual(len(item.polygon()), 4)

    def test_update_parallel_nonbold_preview_updates_all_line_items(self) -> None:
        items = [
            QGraphicsLineItem(0.0, 0.0, 1.0, 0.0),
            QGraphicsLineItem(0.0, 1.0, 1.0, 1.0),
        ]

        updated = update_bond_preview_items(
            items,
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="single",
            order=2,
            canvas_renderer=_renderer(),
            a_id=1,
            b_id=2,
            bond_renderer=_bond_renderer(),
        )

        self.assertTrue(updated)
        self.assertEqual(
            (
                items[1].line().x1(),
                items[1].line().y1(),
                items[1].line().x2(),
                items[1].line().y2(),
            ),
            (0.0, 1.0, 10.0, 1.0),
        )

    def test_update_plain_double_preview_keeps_long_line_on_single_axis(self) -> None:
        items = [
            QGraphicsLineItem(0.0, 0.0, 1.0, 0.0),
            QGraphicsLineItem(0.0, 0.0, 1.0, 0.0),
        ]
        bond_renderer = _bond_renderer(
            wedge_polygon=lambda *args: QPolygonF([QPointF()]),
            hash_segments=lambda *args: ((0.0, 0.0, 1.0, 0.0),),
            dotted_bond_path=lambda *args: QPainterPath(),
            parallel_bond_segments=lambda *args: (
                (0.0, -2.0, 10.0, -2.0),
                (0.0, 2.0, 10.0, 2.0),
            ),
            line_normal=lambda *args: (0.0, 1.0),
            strip_polygon=lambda *args: QPolygonF([QPointF()]),
        )

        updated = update_bond_preview_items(
            items,
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="double",
            order=2,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=bond_renderer,
        )

        self.assertTrue(updated)
        self.assertEqual((items[0].line().y1(), items[0].line().y2()), (0.0, 0.0))
        self.assertEqual((items[1].line().y1(), items[1].line().y2()), (4.4, 4.4))

    def test_update_parallel_nonbold_preview_returns_false_for_non_line_item(
        self,
    ) -> None:
        updated = update_bond_preview_items(
            [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0), QGraphicsPolygonItem()],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            style="single",
            order=2,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)

    def test_update_plain_double_and_parallel_preview_cover_length_and_type_guards(
        self,
    ) -> None:
        self.assertFalse(
            update_bond_preview_items(
                [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)],
                QPointF(0.0, 0.0),
                QPointF(10.0, 0.0),
                style="double",
                order=2,
                canvas_renderer=_renderer(),
                a_id=None,
                b_id=None,
                bond_renderer=_bond_renderer(),
            )
        )
        self.assertFalse(
            update_bond_preview_items(
                [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0), QGraphicsPolygonItem()],
                QPointF(0.0, 0.0),
                QPointF(10.0, 0.0),
                style="double",
                order=2,
                canvas_renderer=_renderer(),
                a_id=None,
                b_id=None,
                bond_renderer=_bond_renderer(),
            )
        )
        self.assertFalse(
            update_bond_preview_items(
                [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)],
                QPointF(0.0, 0.0),
                QPointF(10.0, 0.0),
                style="single",
                order=2,
                canvas_renderer=_renderer(),
                a_id=None,
                b_id=None,
                bond_renderer=_bond_renderer(),
            )
        )

    def test_update_single_preview_returns_false_for_wrong_item_shape(self) -> None:
        updated = update_bond_preview_items(
            [QGraphicsPolygonItem()],
            QPointF(2.0, 3.0),
            QPointF(16.0, 7.0),
            style="single",
            order=1,
            canvas_renderer=_renderer(),
            a_id=None,
            b_id=None,
            bond_renderer=_bond_renderer(),
        )

        self.assertFalse(updated)


def _renderer():
    return SimpleNamespace(
        style=SimpleNamespace(
            bond_line_width=1.2,
            bold_bond_width=2.4,
            hash_spacing_px=4.0,
        ),
        bond_pen=lambda: QPen(QColor("#224466")),
    )


def _bond_renderer(**overrides):
    def draw_dotted_bond(*_args):
        path = QPainterPath()
        path.addEllipse(QPointF(1.0, 0.0), 0.5, 0.5)
        path.addEllipse(QPointF(2.0, 0.0), 0.5, 0.5)
        item = QGraphicsPathItem(path)
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QColor("#224466"))
        return [item]

    def dotted_bond_path(*_args):
        path = QPainterPath()
        path.addEllipse(QPointF(1.0, 0.0), 0.5, 0.5)
        path.addEllipse(QPointF(2.0, 0.0), 0.5, 0.5)
        return path

    methods = dict(
        draw_wedge_bond=lambda *_args: [
            QGraphicsPolygonItem(
                QPolygonF([QPointF(0.0, 0.0), QPointF(6.0, 0.0), QPointF(3.0, 3.0)])
            )
        ],
        draw_hash_bond=lambda *_args: [
            QGraphicsLineItem(0.0, 0.0, 4.0, 0.0),
            QGraphicsLineItem(0.0, 1.0, 4.0, 1.0),
        ],
        draw_dotted_bond=draw_dotted_bond,
        draw_parallel_bonds=lambda *_args: [
            QGraphicsLineItem(0.0, 0.0, 10.0, 0.0),
            QGraphicsLineItem(0.0, 1.0, 10.0, 1.0),
        ],
        line_normal=lambda *_args: (0.0, 1.0),
        one_sided_bond_strip=lambda *_args: QGraphicsPolygonItem(
            QPolygonF(
                [
                    QPointF(0.0, 0.0),
                    QPointF(10.0, 0.0),
                    QPointF(10.0, 2.0),
                    QPointF(0.0, 2.0),
                ]
            )
        ),
        wedge_polygon=lambda *_args: QPolygonF(
            [QPointF(0.0, 0.0), QPointF(8.0, 0.0), QPointF(4.0, 4.0)]
        ),
        hash_segments=lambda *_args: (
            (0.0, 0.0, 4.0, 0.0),
            (0.0, 1.0, 4.0, 1.0),
            (0.0, 2.0, 4.0, 2.0),
        ),
        dotted_bond_path=dotted_bond_path,
        parallel_bond_segments=lambda *_args: (
            (0.0, 0.0, 10.0, 0.0),
            (0.0, 1.0, 10.0, 1.0),
        ),
        strip_polygon=lambda *_args: QPolygonF(
            [
                QPointF(0.0, 0.0),
                QPointF(10.0, 0.0),
                QPointF(10.0, 2.0),
                QPointF(0.0, 2.0),
            ]
        ),
    )
    methods.update(overrides)
    return SimpleNamespace(**methods)


if __name__ == "__main__":
    unittest.main()
