import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QAction, QPainter, QPixmap, QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu

from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.rendering import snapped_to_grid
from chemvas.ui.canvas_background_painter import (
    MIN_GRID_SPACING_PX,
    draw_canvas_background_for,
)
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.endpoint_snap_access import (
    grid_snap_enabled_for,
    grid_step_for,
    set_grid_snap_enabled_for,
    snap_drawing_point_for,
    snap_to_endpoint_for,
)
from chemvas.ui.handle_state import active_handles_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_state_serialization import arrow_state_dict
from chemvas.ui.sheet_setup_access import sheet_rect_for


class GridGeometryTest(unittest.TestCase):
    def test_points_round_to_the_nearest_intersection(self) -> None:
        self.assertEqual(snapped_to_grid((11.0, -4.0), step=10.0), (10.0, -0.0))
        self.assertEqual(snapped_to_grid((-16.0, 26.0), step=10.0), (-20.0, 30.0))
        self.assertEqual(snapped_to_grid((5.0, 5.0), step=10.0), (0.0, 0.0))

    def test_a_non_positive_step_is_no_grid(self) -> None:
        for step in (0.0, -5.0):
            self.assertEqual(snapped_to_grid((3.3, 7.7), step=step), (3.3, 7.7))


class GridSnapCanvasTest(unittest.TestCase):
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

    def _drag(self, start: QPointF, end: QPointF) -> None:
        start_pos = self.canvas.mapFromScene(start)
        end_pos = self.canvas.mapFromScene(end)
        QTest.mousePress(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start_pos,
        )
        self.app.processEvents()
        QTest.mouseMove(self.canvas.viewport(), end_pos)
        self.app.processEvents()
        QTest.mouseRelease(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            end_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def _click(self, scene_pos: QPointF) -> None:
        pos = self.canvas.mapFromScene(scene_pos)
        QTest.mousePress(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        self.app.processEvents()
        QTest.mouseRelease(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def test_the_grid_step_follows_the_bond_length_and_is_off_by_default(self) -> None:
        self.assertFalse(grid_snap_enabled_for(self.canvas))
        self.assertAlmostEqual(grid_step_for(self.canvas), 10.0)

    def test_a_drawing_point_passes_through_until_the_grid_is_on(self) -> None:
        raw = QPointF(13.0, -6.0)
        self.assertEqual(snap_drawing_point_for(self.canvas, raw), raw)

        set_grid_snap_enabled_for(self.canvas, True)

        self.assertEqual(snap_drawing_point_for(self.canvas, raw), QPointF(10.0, -10.0))

    def test_an_endpoint_snap_still_wins_over_the_grid(self) -> None:
        add_arrow_for(self.canvas, QPointF(-33.0, 7.0), QPointF(40.0, 0.0), "arrow")
        set_grid_snap_enabled_for(self.canvas, True)

        # (-33, 7) is not on the grid, but it is an existing endpoint.
        snapped = snap_drawing_point_for(self.canvas, QPointF(-31.0, 8.0))

        self.assertEqual(snapped, QPointF(-33.0, 7.0))

    def test_drawing_a_line_lands_on_the_grid(self) -> None:
        set_grid_snap_enabled_for(self.canvas, True)
        canvas_services_for(self.canvas).input.tool_mode_controller.set_line_kind(
            "line_bold"
        )

        self._drag(QPointF(-37.0, 3.0), QPointF(24.0, -6.0))

        (item,) = arrow_items_for(self.canvas)
        state = arrow_state_dict(item)
        self.assertEqual(state["start"], (-40.0, 0.0))
        self.assertEqual(state["end"], (20.0, -10.0))

    def test_an_endpoint_handle_drag_lands_on_the_grid(self) -> None:
        item = add_arrow_for(
            self.canvas, QPointF(-40.0, 0.0), QPointF(40.0, 0.0), "arrow"
        )
        set_grid_snap_enabled_for(self.canvas, True)
        handles = canvas_services_for(self.canvas).handles
        handles.handle_overlay_service.show_endpoint_handles(item)

        handles.handle_controller.update_handle_drag(
            active_handles_for(self.canvas)[1], QPointF(63.0, 24.0)
        )

        self.assertEqual(arrow_state_dict(item)["end"], (60.0, 20.0))

    def test_a_click_still_refuses_an_arrow_and_places_a_level(self) -> None:
        # The press point is snapped, so a click must compare snapped to
        # snapped; comparing it against the raw release point used to commit a
        # stub arrow and to swallow the level preset.
        set_grid_snap_enabled_for(self.canvas, True)
        tool_mode = canvas_services_for(self.canvas).input.tool_mode_controller

        tool_mode.set_arrow_type("reaction")
        self._click(QPointF(13.0, -7.0))
        self.assertEqual(arrow_items_for(self.canvas), [])

        tool_mode.set_line_kind("line_bold")
        self._click(QPointF(-133.0, 47.0))
        (level,) = arrow_items_for(self.canvas)
        state = arrow_state_dict(level)
        self.assertEqual(state["start"], (-130.0, 50.0))
        self.assertEqual(state["end"], (-90.0, 50.0))

    def test_a_drag_shorter_than_one_grid_step_reads_as_a_click(self) -> None:
        set_grid_snap_enabled_for(self.canvas, True)
        canvas_services_for(self.canvas).input.tool_mode_controller.set_line_kind(
            "line_bold"
        )

        self._drag(QPointF(-83.0, -37.0), QPointF(-81.0, -35.0))

        (item,) = arrow_items_for(self.canvas)
        state = arrow_state_dict(item)
        self.assertEqual(state["start"], (-80.0, -40.0))
        self.assertEqual(state["end"], (-40.0, -40.0))

    def test_the_shift_angle_lock_outranks_the_grid(self) -> None:
        set_grid_snap_enabled_for(self.canvas, True)
        canvas_services_for(self.canvas).input.tool_mode_controller.set_line_kind(
            "line_bold"
        )
        start, end = QPointF(40.0, 40.0), QPointF(97.0, 63.0)
        start_pos = self.canvas.mapFromScene(start)
        end_pos = self.canvas.mapFromScene(end)
        shift = Qt.KeyboardModifier.ShiftModifier

        QTest.mousePress(
            self.canvas.viewport(), Qt.MouseButton.LeftButton, shift, start_pos
        )
        self.app.processEvents()
        QTest.mouseMove(self.canvas.viewport(), end_pos)
        self.app.processEvents()
        QTest.mouseRelease(
            self.canvas.viewport(), Qt.MouseButton.LeftButton, shift, end_pos
        )
        self.app.processEvents()
        QTest.qWait(10)

        (item,) = arrow_items_for(self.canvas)
        state = arrow_state_dict(item)
        angle = math.degrees(
            math.atan2(
                state["end"][1] - state["start"][1],
                state["end"][0] - state["start"][0],
            )
        )
        self.assertAlmostEqual(angle, 15.0, places=6)
        # Shift wins outright, so the end is not pulled back onto the lattice.
        self.assertNotAlmostEqual(state["end"][1] % grid_step_for(self.canvas), 0.0)

    def test_a_cursor_exactly_on_an_off_grid_endpoint_keeps_it(self) -> None:
        add_arrow_for(self.canvas, QPointF(-33.0, 7.0), QPointF(40.0, 0.0), "arrow")
        set_grid_snap_enabled_for(self.canvas, True)

        # The cursor is on the endpoint, so the endpoint stage must report a
        # hit rather than leaving the grid to drag the point off it.
        snapped = snap_drawing_point_for(self.canvas, QPointF(-33.0, 7.0))

        self.assertEqual(snapped, QPointF(-33.0, 7.0))

    def test_an_endpoint_is_never_the_end_a_drag_started_from(self) -> None:
        add_arrow_for(self.canvas, QPointF(0.0, 0.0), QPointF(40.0, 0.0), "line")
        set_grid_snap_enabled_for(self.canvas, True)
        start = QPointF(0.0, 0.0)

        self.assertIsNone(
            snap_to_endpoint_for(self.canvas, QPointF(1.0, 1.0), avoid=start)
        )
        self.assertEqual(snap_to_endpoint_for(self.canvas, QPointF(1.0, 1.0)), start)

    def test_a_click_on_an_existing_endpoint_is_still_a_click(self) -> None:
        # The press takes the endpoint, so putting the release through the
        # funnel again — where that endpoint is the one point it may not take —
        # answered with a grid intersection and committed a stub.
        add_arrow_for(
            self.canvas, QPointF(-103.0, -107.0), QPointF(-33.0, -107.0), "arrow"
        )
        set_grid_snap_enabled_for(self.canvas, True)
        canvas_services_for(self.canvas).input.tool_mode_controller.set_arrow_type(
            "reaction"
        )

        self._click(QPointF(-103.0, -107.0))

        self.assertEqual(len(arrow_items_for(self.canvas)), 1)

        # The Line tool keeps its own copy of the short-circuit, and a
        # click on an existing object is never a request for a new level.
        canvas_services_for(self.canvas).input.tool_mode_controller.set_line_kind(
            "line_bold"
        )
        self._click(QPointF(-103.0, -107.0))

        self.assertEqual(len(arrow_items_for(self.canvas)), 1)

    def test_a_click_on_an_existing_endpoint_is_a_click_with_the_grid_off(self) -> None:
        # The endpoint stage runs whether or not the grid does, so the same
        # click committed a stub the size of the cursor's own offset.
        add_arrow_for(
            self.canvas, QPointF(-103.0, -107.0), QPointF(-33.0, -107.0), "arrow"
        )
        canvas_services_for(self.canvas).input.tool_mode_controller.set_arrow_type(
            "reaction"
        )

        self.assertFalse(grid_snap_enabled_for(self.canvas))
        self._click(QPointF(-101.0, -106.0))

        self.assertEqual(len(arrow_items_for(self.canvas)), 1)

    def test_a_curved_endpoint_handle_lands_on_the_grid(self) -> None:
        item = add_arrow_for(
            self.canvas, QPointF(200.0, 0.0), QPointF(260.0, 0.0), "curved_single"
        )
        set_grid_snap_enabled_for(self.canvas, True)
        handles = canvas_services_for(self.canvas).handles
        handles.handle_overlay_service.show_curved_handles(item)

        handles.handle_controller.update_handle_drag(
            active_handles_for(self.canvas)[0], QPointF(203.0, 7.0)
        )

        self.assertEqual(arrow_state_dict(item)["start"], (200.0, 10.0))

    def _paint_background(self, *, scale: float) -> QPixmap:
        pixmap = QPixmap(120, 120)
        pixmap.fill()
        painter = QPainter(pixmap)
        painter.setTransform(QTransform().scale(scale, scale))
        sheet = sheet_rect_for(self.canvas)
        draw_canvas_background_for(
            self.canvas, painter, QRectF(sheet.center(), sheet.bottomRight())
        )
        painter.end()
        return pixmap

    def _distinct_colors(self, pixmap: QPixmap) -> int:
        image = pixmap.toImage()
        return len(
            {
                image.pixel(x, y)
                for x in range(image.width())
                for y in range(image.height())
            }
        )

    def test_a_squashed_vertical_scale_also_hides_the_grid(self) -> None:
        # Perspective squashes only the vertical scale; the denser axis has to
        # decide, or the rows collapse into the wash the guard exists to stop.
        set_grid_snap_enabled_for(self.canvas, True)
        squashed = QTransform().scale(
            1.0, (MIN_GRID_SPACING_PX / grid_step_for(self.canvas)) * 0.5
        )
        pixmap = QPixmap(120, 120)
        pixmap.fill()
        painter = QPainter(pixmap)
        painter.setTransform(squashed)
        sheet = sheet_rect_for(self.canvas)
        draw_canvas_background_for(
            self.canvas, painter, QRectF(sheet.center(), sheet.bottomRight())
        )
        painter.end()
        squashed_colors = self._distinct_colors(pixmap)

        set_grid_snap_enabled_for(self.canvas, False)
        pixmap = QPixmap(120, 120)
        pixmap.fill()
        painter = QPainter(pixmap)
        painter.setTransform(squashed)
        draw_canvas_background_for(
            self.canvas, painter, QRectF(sheet.center(), sheet.bottomRight())
        )
        painter.end()

        self.assertEqual(squashed_colors, self._distinct_colors(pixmap))

    def test_the_grid_is_painted_only_when_enabled_and_readable(self) -> None:
        # Each pair is compared at one scale, so only the grid setting differs.
        dense_scale = (MIN_GRID_SPACING_PX / grid_step_for(self.canvas)) * 0.5
        plain = self._distinct_colors(self._paint_background(scale=1.0))
        plain_dense = self._distinct_colors(self._paint_background(scale=dense_scale))

        set_grid_snap_enabled_for(self.canvas, True)

        self.assertGreater(
            self._distinct_colors(self._paint_background(scale=1.0)), plain
        )
        # Zoomed far out the dots would merge into a wash, so they are skipped.
        self.assertEqual(
            self._distinct_colors(self._paint_background(scale=dense_scale)),
            plain_dense,
        )


class GridSnapMenuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def _grid_action(self) -> QAction:
        view_menu = next(
            menu
            for action in self.window.menuBar().actions()
            if (menu := action.menu()) is not None and menu.title() == "View"
        )
        assert isinstance(view_menu, QMenu)
        return next(
            action for action in view_menu.actions() if action.text() == "Snap to Grid"
        )

    def test_the_menu_item_is_a_checkbox_that_drives_the_active_canvas(self) -> None:
        action = self._grid_action()
        canvas = active_canvas_for_window(self.window)
        self.assertTrue(action.isCheckable())
        self.assertFalse(action.isChecked())
        self.assertFalse(grid_snap_enabled_for(canvas))

        action.trigger()
        self.assertTrue(action.isChecked())
        self.assertTrue(grid_snap_enabled_for(canvas))

        action.trigger()
        self.assertFalse(grid_snap_enabled_for(canvas))

    def test_the_checkbox_follows_the_canvas_the_user_is_on(self) -> None:
        services = services_for_window(self.window)
        first = active_canvas_for_window(self.window)
        self._grid_action().trigger()
        self.assertTrue(grid_snap_enabled_for(first))

        services.canvas_document_service.new_canvas(self.window)
        self.app.processEvents()
        second = active_canvas_for_window(self.window)
        self.assertIsNot(second, first)

        self.assertFalse(grid_snap_enabled_for(second))
        self.assertFalse(self._grid_action().isChecked())
