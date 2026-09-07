import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.selection.handles import HANDLE_ACCENT_COLOR
from chemvas.ui.canvas_arrow_build_service import SNAP_MARK_ROLE
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.endpoint_snap_access import (
    ENDPOINT_SNAP_SCREEN_PX,
    endpoint_snap_radius_for,
    snapped_points_among_for,
)
from chemvas.ui.handle_state import active_handles_for
from chemvas.ui.input_view_access import set_zoom_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_state_serialization import arrow_state_dict


class SnapRadiusTest(unittest.TestCase):
    def test_the_catch_is_measured_on_the_smaller_axis(self) -> None:
        # The perspective tool squashes the view's vertical scale, and the reach
        # has to stay at least the nominal distance in every direction, so the
        # smaller scale governs.
        squashed = SimpleNamespace(transform=lambda: QTransform().scale(2.0, 0.5))

        self.assertAlmostEqual(
            endpoint_snap_radius_for(squashed), ENDPOINT_SNAP_SCREEN_PX / 0.5
        )

    def test_a_degenerate_view_scale_falls_back_to_one(self) -> None:
        flat = SimpleNamespace(transform=lambda: QTransform().scale(1.0, 0.0))

        self.assertAlmostEqual(endpoint_snap_radius_for(flat), ENDPOINT_SNAP_SCREEN_PX)


class SnapFeedbackTest(unittest.TestCase):
    """The endpoint snap has to be reachable, and it has to be visible."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.window.show()
        self.canvas = active_canvas_for_window(self.window)
        self.canvas.setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _press_and_move(self, start: QPointF, end: QPointF) -> None:
        QTest.mousePress(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.canvas.mapFromScene(start),
        )
        self.app.processEvents()
        QTest.mouseMove(self.canvas.viewport(), self.canvas.mapFromScene(end))
        self.app.processEvents()

    def _release(self, scene_pos: QPointF) -> None:
        QTest.mouseRelease(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.canvas.mapFromScene(scene_pos),
        )
        self.app.processEvents()
        QTest.qWait(10)

    def _drag(self, start: QPointF, end: QPointF) -> None:
        self._press_and_move(start, end)
        self._release(end)

    def _drag_onto(self, end: QPointF) -> None:
        """Drag to ``end`` from far enough away that it is never a click."""
        self._drag(QPointF(end.x() + 60.0, end.y() + 60.0), end)

    def _last_end(self) -> tuple[float, float]:
        return arrow_state_dict(arrow_items_for(self.canvas)[-1])["end"]

    def _snap_marks(self):
        return [
            child
            for item in self.canvas.scene().items()
            for child in item.childItems()
            if child.data(0) == SNAP_MARK_ROLE
        ]

    def test_the_catch_is_the_same_distance_on_screen_at_every_zoom(self) -> None:
        for zoom in (0.5, 1.0, 2.0, 4.0):
            set_zoom_for(self.canvas, zoom)
            self.app.processEvents()
            scale = abs(self.canvas.transform().m11())
            on_screen = endpoint_snap_radius_for(self.canvas) * scale
            self.assertAlmostEqual(on_screen, ENDPOINT_SNAP_SCREEN_PX, places=6)

    def test_an_end_released_inside_the_catch_takes_the_endpoint(self) -> None:
        target = QPointF(-20.0, 0.0)
        add_arrow_for(self.canvas, QPointF(-100.0, 0.0), target, "line_bold")
        canvas_services_for(self.canvas).input.tool_mode_controller.set_line_kind(
            "line_dashed"
        )

        # The default zoom is 1:1, so a scene unit is a screen pixel here and
        # the catch is twelve of them.
        self._drag_onto(QPointF(target.x() + 11.0, target.y()))
        self.assertEqual(self._last_end(), (target.x(), target.y()))

        outside = QPointF(target.x() + 13.0, target.y())
        self._drag_onto(outside)
        self.assertEqual(self._last_end(), (outside.x(), outside.y()))

    def test_the_preview_rings_an_end_that_took_an_endpoint(self) -> None:
        add_arrow_for(
            self.canvas, QPointF(-100.0, 0.0), QPointF(-20.0, 0.0), "line_bold"
        )
        canvas_services_for(self.canvas).input.tool_mode_controller.set_line_kind(
            "line_dashed"
        )

        onto = QPointF(-22.0, 2.0)
        self._press_and_move(QPointF(onto.x() + 60.0, onto.y() + 60.0), onto)
        self.assertEqual(len(self._snap_marks()), 1)
        self._release(onto)
        # The ring belongs to the preview, so it goes when the preview does.
        self.assertEqual(self._snap_marks(), [])

        away = QPointF(120.0, 90.0)
        self._press_and_move(QPointF(away.x() + 60.0, away.y() + 60.0), away)
        self.assertEqual(self._snap_marks(), [])
        self._release(away)

    def test_a_handle_that_took_another_endpoint_is_filled(self) -> None:
        add_arrow_for(
            self.canvas, QPointF(-60.0, 0.0), QPointF(-20.0, 0.0), "line_bold"
        )
        connector = add_arrow_for(
            self.canvas, QPointF(40.0, 40.0), QPointF(80.0, 40.0), "line_dashed"
        )
        handles = canvas_services_for(self.canvas).handles
        handles.handle_overlay_service.show_endpoint_handles(connector)
        self.assertEqual(self._handle_fills(), ["#ffffff", "#ffffff"])

        handles.handle_controller.update_handle_drag(
            active_handles_for(self.canvas)[0], QPointF(-24.0, 3.0)
        )

        self.assertEqual(arrow_state_dict(connector)["start"], (-20.0, 0.0))
        self.assertEqual(self._handle_fills(), [HANDLE_ACCENT_COLOR, "#ffffff"])

    def _handle_fills(self) -> list[str]:
        return [
            handle.brush().color().name() for handle in active_handles_for(self.canvas)
        ]

    def test_snapped_points_among_reports_only_points_on_an_endpoint(self) -> None:
        level = add_arrow_for(
            self.canvas, QPointF(-60.0, 0.0), QPointF(-20.0, 0.0), "line_bold"
        )
        on_it, beside_it = QPointF(-20.0, 0.0), QPointF(-19.0, 0.0)

        caught = snapped_points_among_for(self.canvas, [on_it, beside_it])

        self.assertEqual([(point.x(), point.y()) for point in caught], [(-20.0, 0.0)])
        # An item's own ends are not evidence that it took anything.
        self.assertEqual(
            snapped_points_among_for(self.canvas, [on_it], exclude=level), []
        )


if __name__ == "__main__":
    unittest.main()
