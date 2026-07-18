import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QApplication, QGraphicsPathItem
except ModuleNotFoundError:
    QApplication = None
    QPointF = None
    QRectF = None
    Qt = None
    QColor = None

if QApplication is not None:
    try:
        from chemvas.ui.canvas_scene_decoration_build_service import (
            CanvasSceneDecorationBuildService,
        )
        from chemvas.ui.canvas_tool_settings_state import set_tool_setting_for
        from chemvas.ui.canvas_view import CanvasView
    except SyntaxError:
        CanvasSceneDecorationBuildService = None
        CanvasView = None
else:
    CanvasSceneDecorationBuildService = None
    CanvasView = None


@unittest.skipUnless(
    QApplication is not None
    and CanvasSceneDecorationBuildService is not None
    and CanvasView is not None,
    "PyQt6 and scene decoration build service are required for tests",
)
class CanvasSceneDecorationBuildServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = CanvasView()
        self.service = CanvasSceneDecorationBuildService(self.canvas)

    def tearDown(self) -> None:
        self.canvas.deleteLater()
        self.app.processEvents()

    def test_build_arrow_item_delegates_to_arrow_build_service(self) -> None:
        arrow_service = mock.Mock()
        service = CanvasSceneDecorationBuildService(
            self.canvas, arrow_build_service=arrow_service
        )
        arrow_service.build_arrow_item.return_value = "arrow"

        result = service.build_arrow_item(
            QPointF(1.0, 2.0), QPointF(7.0, 8.0), "dotted"
        )

        self.assertEqual(result, "arrow")
        arrow_service.build_arrow_item.assert_called_once_with(
            QPointF(1.0, 2.0), QPointF(7.0, 8.0), "dotted"
        )

    def test_arrow_helpers_delegate_to_arrow_build_service(self) -> None:
        arrow_service = mock.Mock()
        service = CanvasSceneDecorationBuildService(
            self.canvas, arrow_build_service=arrow_service
        )
        path = object()
        item = object()

        arrow_service.preview_arrow.return_value = item
        arrow_service.build_arrow_item.return_value = item
        arrow_service.build_single_head_arrow.return_value = item
        arrow_service.build_double_head_arrow.return_value = item
        arrow_service.build_dotted_arrow.return_value = item
        arrow_service.build_curved_arrow.return_value = item
        arrow_service.build_inhibition_arrow.return_value = item
        arrow_service.build_equilibrium_item.return_value = item
        arrow_service.arrow_pen.return_value = "pen"

        self.assertIs(
            service.preview_arrow(QPointF(1.0, 2.0), QPointF(3.0, 4.0), "reaction"),
            item,
        )
        self.assertIs(
            service.build_arrow_item(QPointF(5.0, 6.0), QPointF(7.0, 8.0), "dotted"),
            item,
        )
        self.assertIs(
            service.build_single_head_arrow(QPointF(1.0, 1.0), QPointF(2.0, 2.0)), item
        )
        self.assertIs(
            service.build_double_head_arrow(QPointF(1.0, 1.0), QPointF(2.0, 2.0)), item
        )
        self.assertIs(
            service.build_dotted_arrow(QPointF(1.0, 1.0), QPointF(2.0, 2.0)), item
        )
        self.assertIs(
            service.build_curved_arrow(
                QPointF(1.0, 1.0), QPointF(2.0, 2.0), double=True
            ),
            item,
        )
        self.assertIs(
            service.build_inhibition_arrow(QPointF(1.0, 1.0), QPointF(2.0, 2.0)), item
        )
        self.assertIs(
            service.build_equilibrium_item(QPointF(1.0, 1.0), QPointF(2.0, 2.0)), item
        )
        service.add_arrow_head(path, QPointF(3.0, 3.0), QPointF(4.0, 4.0), double=False)
        self.assertEqual(service.arrow_pen(dotted=True), "pen")

        arrow_service.preview_arrow.assert_called_once_with(
            QPointF(1.0, 2.0), QPointF(3.0, 4.0), "reaction"
        )
        arrow_service.build_arrow_item.assert_called_once_with(
            QPointF(5.0, 6.0), QPointF(7.0, 8.0), "dotted"
        )
        arrow_service.build_single_head_arrow.assert_called_once_with(
            QPointF(1.0, 1.0), QPointF(2.0, 2.0)
        )
        arrow_service.build_double_head_arrow.assert_called_once_with(
            QPointF(1.0, 1.0), QPointF(2.0, 2.0)
        )
        arrow_service.build_dotted_arrow.assert_called_once_with(
            QPointF(1.0, 1.0), QPointF(2.0, 2.0)
        )
        arrow_service.build_curved_arrow.assert_called_once_with(
            QPointF(1.0, 1.0), QPointF(2.0, 2.0), True
        )
        arrow_service.build_inhibition_arrow.assert_called_once_with(
            QPointF(1.0, 1.0), QPointF(2.0, 2.0)
        )
        arrow_service.build_equilibrium_item.assert_called_once_with(
            QPointF(1.0, 1.0), QPointF(2.0, 2.0)
        )
        arrow_service.add_arrow_head.assert_called_once_with(
            path, QPointF(3.0, 3.0), QPointF(4.0, 4.0), False
        )
        arrow_service.arrow_pen.assert_called_once_with(dotted=True)

    def test_preview_helpers_add_items_to_scene(self) -> None:
        arrow = self.service.preview_arrow(
            QPointF(0.0, 0.0), QPointF(12.0, 0.0), "reaction"
        )
        bracket = self.service.preview_ts_bracket(QPointF(1.0, 2.0), QPointF(3.0, 4.0))

        self.assertIs(arrow.scene(), self.canvas.scene())
        self.assertIs(bracket.scene(), self.canvas.scene())
        self.assertIn(arrow, self.canvas.scene().items())
        self.assertIn(bracket, self.canvas.scene().items())

    def test_ts_bracket_helpers_normalize_rect_and_attach_metadata(self) -> None:
        rect = self.service.ts_bracket_rect_from_points(
            QPointF(4.0, 5.0), QPointF(5.0, 6.0)
        )
        large_rect = self.service.ts_bracket_rect_from_points(
            QPointF(-30.0, -10.0), QPointF(30.0, 18.0)
        )
        item = self.service.build_ts_bracket_item(QRectF(8.0, 9.0, -4.0, -6.0))

        min_width = self.canvas.renderer.style.bond_length_px * 1.8
        min_height = self.canvas.renderer.style.bond_length_px * 2.4
        self.assertGreaterEqual(rect.width(), min_width)
        self.assertGreaterEqual(rect.height(), min_height)
        self.assertEqual(large_rect, QRectF(-30.0, -20.0, 60.0, 48.0))
        self.assertEqual(item.data(0), "ts_bracket")
        self.assertEqual(item.data(1)["rect"], QRectF(4.0, 3.0, 4.0, 6.0))
        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(
            item.brush().color().name(),
            QColor(self.canvas.renderer.style.bond_color).name(),
        )

    def test_shape_stroke_none_is_drawable_borderless_with_dashed_preview(self) -> None:
        from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for

        # "none" becomes the active drawing default (not just a mutation of the
        # current selection), so background panels can be drawn borderless.
        self.canvas.services.tool_mode_controller.set_shape_stroke("none")
        self.assertEqual(
            tool_settings_state_for(self.canvas).active_shape_stroke, "none"
        )

        item = self.service.build_shape_item(
            QRectF(0.0, 0.0, 40.0, 20.0), "rect", "none"
        )
        preview = self.service.preview_shape(
            QPointF(0.0, 0.0), QPointF(40.0, 20.0), "rect", "none"
        )

        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        # The drag preview substitutes a dashed guide so drawing stays visible.
        self.assertEqual(preview.pen().style(), Qt.PenStyle.DashLine)

    def test_build_shape_item_stacks_behind_default_scene_content(self) -> None:
        item = self.service.build_shape_item(QRectF(0.0, 0.0, 40.0, 20.0), "rect")
        preview = self.service.preview_shape(
            QPointF(0.0, 0.0), QPointF(40.0, 20.0), "circle"
        )

        self.assertEqual(item.data(0), "shape")
        self.assertLess(item.zValue(), 0.0)
        self.assertEqual(item.zValue(), CanvasSceneDecorationBuildService.SHAPE_Z_VALUE)
        self.assertEqual(
            preview.zValue(), CanvasSceneDecorationBuildService.SHAPE_Z_VALUE
        )

    def test_build_orbital_items_respects_phase_fill_and_supported_shapes(self) -> None:
        set_tool_setting_for(self.canvas, "orbital_phase_enabled", False)
        s_items = self.service.build_orbital_items(QPointF(0.0, 0.0), "s")

        self.assertEqual(len(s_items), 1)
        self.assertEqual(s_items[0].brush().style(), Qt.BrushStyle.NoBrush)

        set_tool_setting_for(self.canvas, "orbital_phase_enabled", True)
        p_items = self.service.build_orbital_items(QPointF(0.0, 0.0), "p")
        antibonding_items = self.service.build_orbital_items(
            QPointF(0.0, 0.0), "mo_antibonding"
        )

        self.assertEqual(len(p_items), 2)
        self.assertNotEqual(p_items[0].brush().style(), Qt.BrushStyle.NoBrush)
        self.assertNotEqual(p_items[1].brush().style(), Qt.BrushStyle.NoBrush)
        self.assertNotEqual(p_items[0].brush().color(), p_items[1].brush().color())
        self.assertEqual(len(antibonding_items), 3)
        self.assertEqual(
            antibonding_items[-1].line().x1(), antibonding_items[-1].line().x2()
        )

    def test_build_orbital_items_covers_remaining_orbital_variants_and_unknown_kind(
        self,
    ) -> None:
        set_tool_setting_for(self.canvas, "orbital_phase_enabled", True)

        sp_items = self.service.build_orbital_items(QPointF(0.0, 0.0), "sp")
        sp2_items = self.service.build_orbital_items(QPointF(0.0, 0.0), "sp2")
        sp3_items = self.service.build_orbital_items(QPointF(0.0, 0.0), "sp3")
        d_items = self.service.build_orbital_items(QPointF(0.0, 0.0), "d")
        bonding_items = self.service.build_orbital_items(
            QPointF(0.0, 0.0), "mo_bonding"
        )
        unknown_items = self.service.build_orbital_items(QPointF(0.0, 0.0), "unknown")

        self.assertEqual(len(sp_items), 2)
        self.assertGreater(sp_items[0].rect().width(), sp_items[1].rect().width())
        self.assertEqual(len(sp2_items), 3)
        self.assertTrue(
            all(item.brush().style() != Qt.BrushStyle.NoBrush for item in sp2_items)
        )
        centers = [item.rect().center() for item in sp2_items]
        self.assertEqual(
            len({(round(center.x(), 4), round(center.y(), 4)) for center in centers}), 3
        )
        self.assertTrue(any(center.x() > 0.0 for center in centers))
        self.assertTrue(
            any(center.x() < 0.0 and center.y() > 0.0 for center in centers)
        )
        self.assertTrue(
            any(center.x() < 0.0 and center.y() < 0.0 for center in centers)
        )
        self.assertEqual(len(sp3_items), 4)
        self.assertTrue(
            all(item.brush().style() != Qt.BrushStyle.NoBrush for item in sp3_items)
        )
        self.assertEqual(len(d_items), 4)
        self.assertEqual(
            {item.brush().color().name() for item in d_items},
            {
                QColor(self.canvas.renderer.style.orbital_positive_color).name(),
                QColor(self.canvas.renderer.style.orbital_negative_color).name(),
            },
        )
        self.assertEqual(len(bonding_items), 2)
        self.assertEqual(
            bonding_items[0].brush().color(), bonding_items[1].brush().color()
        )
        self.assertEqual(unknown_items, [])

    def test_mark_helpers_build_supported_items_and_center_text(self) -> None:
        radical = self.service.build_mark_item("radical")
        plus = self.service.build_mark_item("plus")
        circled_plus = self.service.build_mark_item("circled_plus")
        circled_minus = self.service.build_mark_item("circled_minus")

        self.assertIsNotNone(radical)
        self.assertIsNotNone(plus)
        self.assertIsInstance(circled_plus, QGraphicsPathItem)
        self.assertIsInstance(circled_minus, QGraphicsPathItem)
        self.assertIsNone(self.service.build_mark_item("unsupported"))
        self.assertEqual(plus.toPlainText(), "+")
        self.assertEqual(radical.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(circled_plus.brush().style(), Qt.BrushStyle.NoBrush)
        self.assertEqual(circled_minus.brush().style(), Qt.BrushStyle.NoBrush)
        self.assertGreater(
            circled_plus.path().elementCount(), circled_minus.path().elementCount()
        )

        self.service.set_mark_center(plus, QPointF(10.0, 12.0))
        self.service.set_mark_center(radical, QPointF(14.0, 16.0))
        self.service.set_mark_center(circled_plus, QPointF(18.0, 20.0))

        self.assertEqual(self.service.mark_center(plus), QPointF(10.0, 12.0))
        self.assertEqual(self.service.mark_center(radical), QPointF(14.0, 16.0))
        self.assertEqual(self.service.mark_center(circled_plus), QPointF(18.0, 20.0))


if __name__ == "__main__":
    unittest.main()
