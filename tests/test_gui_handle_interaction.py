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
    from ui.main_window import MainWindow


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI handle tests")
class GuiHandleInteractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.window.canvas.setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_show_orbital_handles_and_drag_scale_updates_target_and_clears(self) -> None:
        self.window.canvas.set_bond_length(20.0)
        self.window.canvas.active_orbital_type = "p"
        self.window.canvas.add_orbital(QPointF(0.0, 0.0))
        orbital = self.window.canvas.orbital_items[0]

        self.window.canvas.show_orbital_handles(orbital)

        self.assertEqual(len(self.window.canvas._active_handles), 2)
        self.assertIs(self.window.canvas._handle_target, orbital)
        scale_handle = next(
            handle for handle in self.window.canvas._active_handles if handle.data(1) == "orbital_scale"
        )

        self.window.canvas.update_handle_drag(scale_handle, QPointF(40.0, 0.0))

        self.assertGreater(orbital.scale(), 1.0)
        self.assertEqual(len(self.window.canvas._active_handles), 2)
        self.assertIs(self.window.canvas._handle_target, orbital)

        self.window.canvas.clear_handles()

        self.assertEqual(self.window.canvas._active_handles, [])
        self.assertIsNone(self.window.canvas._handle_target)

    def test_show_curved_handles_and_drag_endpoint_updates_arrow_geometry(self) -> None:
        self.window.canvas.set_bond_length(20.0)
        curved = self.window.canvas.add_arrow(QPointF(0.0, 0.0), QPointF(30.0, 0.0), "curved_single")
        self.window.canvas.move_item(curved, 40.0, -15.0)

        self.window.canvas.show_curved_handles(curved)

        self.assertEqual(len(self.window.canvas._active_handles), 3)
        start_handle = next(handle for handle in self.window.canvas._active_handles if handle.data(1) == "curved_start")

        self.window.canvas.update_handle_drag(start_handle, QPointF(30.0, -10.0))

        data = curved.data(2)
        self.assertEqual(data["start"], QPointF(30.0, -10.0))
        self.assertEqual(curved.pos(), QPointF())
        self.assertEqual(start_handle.data(2), curved)
        self.assertEqual(len(self.window.canvas._active_handles), 3)
        self.assertIs(self.window.canvas._handle_target, curved)


if __name__ == "__main__":
    unittest.main()
