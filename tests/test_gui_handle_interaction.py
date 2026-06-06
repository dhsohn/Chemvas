import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QTest = None
    QPointF = None

if QApplication is not None:
    from ui.canvas_scene_items_state import orbital_items_for
    from ui.canvas_service_access import canvas_services_for
    from ui.canvas_tool_settings_state import set_tool_setting_for
    from ui.handle_overlay_access import (
        clear_handles_for,
        show_curved_handles_for,
        show_orbital_handles_for,
    )
    from ui.handle_state import active_handles_for, handle_target_for
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.move_access import move_item_for
    from ui.scene_decoration_access import add_arrow_for, add_orbital_for


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI handle tests")
class GuiHandleInteractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        active_canvas_for_window(self.window).setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_show_orbital_handles_and_drag_scale_updates_target_and_clears(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).geometry_controller.set_bond_length(20.0)
        set_tool_setting_for(active_canvas_for_window(self.window), "active_orbital_type", "p")
        add_orbital_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        orbital = orbital_items_for(active_canvas_for_window(self.window))[0]

        show_orbital_handles_for(active_canvas_for_window(self.window), orbital)

        self.assertEqual(len(active_handles_for(active_canvas_for_window(self.window))), 2)
        self.assertIs(handle_target_for(active_canvas_for_window(self.window)), orbital)
        scale_handle = next(
            handle for handle in active_handles_for(active_canvas_for_window(self.window)) if handle.data(1) == "orbital_scale"
        )

        active_canvas_for_window(self.window).services.handle_controller.update_handle_drag(scale_handle, QPointF(40.0, 0.0))

        self.assertGreater(orbital.scale(), 1.0)
        self.assertEqual(len(active_handles_for(active_canvas_for_window(self.window))), 2)
        self.assertIs(handle_target_for(active_canvas_for_window(self.window)), orbital)

        clear_handles_for(active_canvas_for_window(self.window))

        self.assertEqual(active_handles_for(active_canvas_for_window(self.window)), [])
        self.assertIsNone(handle_target_for(active_canvas_for_window(self.window)))

    def test_show_curved_handles_and_drag_endpoint_updates_arrow_geometry(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).geometry_controller.set_bond_length(20.0)
        curved = add_arrow_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0), QPointF(30.0, 0.0), "curved_single")
        move_item_for(active_canvas_for_window(self.window), curved, 40.0, -15.0)

        show_curved_handles_for(active_canvas_for_window(self.window), curved)

        self.assertEqual(len(active_handles_for(active_canvas_for_window(self.window))), 3)
        start_handle = next(handle for handle in active_handles_for(active_canvas_for_window(self.window)) if handle.data(1) == "curved_start")

        active_canvas_for_window(self.window).services.handle_controller.update_handle_drag(start_handle, QPointF(30.0, -10.0))

        data = curved.data(2)
        self.assertEqual(data["start"], QPointF(30.0, -10.0))
        self.assertEqual(curved.pos(), QPointF())
        self.assertEqual(start_handle.data(2), curved)
        self.assertEqual(len(active_handles_for(active_canvas_for_window(self.window))), 3)
        self.assertIs(handle_target_for(active_canvas_for_window(self.window)), curved)


if __name__ == "__main__":
    unittest.main()
