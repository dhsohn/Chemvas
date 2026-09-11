import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_hit_testing_service import CanvasHitTestingService
from chemvas.ui.canvas_scene_items_state import orbital_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_service_ports import handle_overlay_service_for_access
from chemvas.ui.canvas_tool_settings_state import set_tool_setting_for
from chemvas.ui.handle_overlay_access import (
    clear_handles_for,
    show_curved_handles_for,
)
from chemvas.ui.handle_state import active_handles_for, handle_target_for
from chemvas.ui.input_view_access import set_zoom_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_decoration_access import (
    add_arrow_for,
    add_orbital_for,
    add_ts_bracket_for,
)


class GuiHandleInteractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.window.show()
        active_canvas_for_window(self.window).setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_selecting_orbital_twice_exposes_its_resize_handle(self):
        canvas = active_canvas_for_window(self.window)
        canvas_services_for(canvas).input.tool_mode_controller.set_tool("select")
        set_tool_setting_for(canvas, "active_orbital_type", "p")
        add_orbital_for(canvas, QPointF(0, 0))
        orbital = orbital_items_for(canvas)[0]
        point = canvas.mapFromScene(
            orbital.childItems()[0].sceneBoundingRect().center()
        )
        for _ in range(2):
            QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
            self.app.processEvents()
        self.assertEqual(
            [handle.data(1) for handle in active_handles_for(canvas)],
            ["orbital_scale", "orbital_rotate"],
        )
        handle = active_handles_for(canvas)[0]
        start = canvas.mapFromScene(handle.pos())
        end = canvas.mapFromScene(handle.pos() + QPointF(30, 0))
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas.viewport(), end, 30)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertGreater(orbital.scale(), 1.0)
        canvas_services_for(canvas).history_service.undo()
        self.assertAlmostEqual(orbital.scale(), 1.0)

    def test_orbital_options_include_molecular_orbital_kinds(self):
        canvas = active_canvas_for_window(self.window)
        canvas_services_for(canvas).input.tool_mode_controller.set_tool("orbital")
        for label, kind in (
            ("MO bonding", "mo_bonding"),
            ("MO antibonding", "mo_antibonding"),
        ):
            buttons = [
                button
                for button in self.window.findChildren(QToolButton)
                if button.toolTip() == f"Orbital: {label}"
            ]
            self.assertEqual(len(buttons), 1)
            self.assertTrue(buttons[0].isVisible())
            QTest.mouseClick(buttons[0], Qt.MouseButton.LeftButton)
            add_orbital_for(canvas, QPointF(0, 0))
            self.assertEqual(orbital_items_for(canvas)[-1].data(2)["kind"], kind)

    def test_ts_bracket_has_screen_space_pick_margin_and_moves_on_first_drag(self):
        canvas = active_canvas_for_window(self.window)
        canvas_services_for(canvas).input.tool_mode_controller.set_tool("select")
        bracket = add_ts_bracket_for(canvas, QRectF(-100, -60, 100, 120))
        hit = CanvasHitTestingService(canvas)
        for zoom in (0.5, 1.0, 2.0):
            set_zoom_for(canvas, zoom)
            self.assertAlmostEqual(canvas.viewportTransform().m11(), zoom)
            self.assertIs(hit.item_at_scene_pos(QPointF(-100 - 4 / zoom, 0)), bracket)
        set_zoom_for(canvas, 1.0)
        start = canvas.mapFromScene(QPointF(-100, 0))
        end = canvas.mapFromScene(QPointF(-100, 30))
        before = bracket.sceneBoundingRect()
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas.viewport(), end, 30)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertAlmostEqual(bracket.sceneBoundingRect().top() - before.top(), 30)
        canvas_services_for(canvas).history_service.undo()
        self.assertEqual(bracket.sceneBoundingRect(), before)

    def test_show_orbital_handles_and_drag_scale_updates_target_and_clears(
        self,
    ) -> None:
        canvas_services_for(
            active_canvas_for_window(self.window)
        ).scene_view.geometry_controller.set_bond_length(20.0)
        set_tool_setting_for(
            active_canvas_for_window(self.window), "active_orbital_type", "p"
        )
        add_orbital_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        orbital = orbital_items_for(active_canvas_for_window(self.window))[0]

        handle_overlay_service_for_access(
            active_canvas_for_window(self.window)
        ).show_orbital_handles(orbital)

        self.assertEqual(
            len(active_handles_for(active_canvas_for_window(self.window))), 2
        )
        self.assertIs(handle_target_for(active_canvas_for_window(self.window)), orbital)
        scale_handle = next(
            handle
            for handle in active_handles_for(active_canvas_for_window(self.window))
            if handle.data(1) == "orbital_scale"
        )

        active_canvas_for_window(
            self.window
        ).services.handles.handle_controller.update_handle_drag(
            scale_handle, QPointF(40.0, 0.0)
        )

        self.assertGreater(orbital.scale(), 1.0)
        self.assertEqual(
            len(active_handles_for(active_canvas_for_window(self.window))), 2
        )
        self.assertIs(handle_target_for(active_canvas_for_window(self.window)), orbital)

        clear_handles_for(active_canvas_for_window(self.window))

        self.assertEqual(active_handles_for(active_canvas_for_window(self.window)), [])
        self.assertIsNone(handle_target_for(active_canvas_for_window(self.window)))

    def test_show_curved_handles_and_drag_endpoint_updates_arrow_geometry(self) -> None:
        canvas_services_for(
            active_canvas_for_window(self.window)
        ).scene_view.geometry_controller.set_bond_length(20.0)
        curved = add_arrow_for(
            active_canvas_for_window(self.window),
            QPointF(0.0, 0.0),
            QPointF(30.0, 0.0),
            "curved_single",
        )
        move_item_for(active_canvas_for_window(self.window), curved, 40.0, -15.0)

        show_curved_handles_for(active_canvas_for_window(self.window), curved)

        self.assertEqual(
            len(active_handles_for(active_canvas_for_window(self.window))), 3
        )
        start_handle = next(
            handle
            for handle in active_handles_for(active_canvas_for_window(self.window))
            if handle.data(1) == "curved_start"
        )

        active_canvas_for_window(
            self.window
        ).services.handles.handle_controller.update_handle_drag(
            start_handle, QPointF(30.0, -10.0)
        )

        data = curved.data(2)
        self.assertEqual(data["start"], QPointF(30.0, -10.0))
        self.assertEqual(curved.pos(), QPointF())
        self.assertEqual(start_handle.data(2), curved)
        self.assertEqual(
            len(active_handles_for(active_canvas_for_window(self.window))), 3
        )
        self.assertIs(handle_target_for(active_canvas_for_window(self.window)), curved)
