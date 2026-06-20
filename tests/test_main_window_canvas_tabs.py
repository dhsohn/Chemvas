import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QTest = None

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.main_window_preview_ports import preview_for_window
    from ui.main_window_service_ports import services_for_window


@unittest.skipUnless(QApplication is not None, "PyQt6 and MainWindow are required for GUI canvas tab tests")
class MainWindowCanvasTabsTest(unittest.TestCase):
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
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_new_canvas_creates_independent_document_tab(self) -> None:
        first_canvas = active_canvas_for_window(self.window)

        second_canvas = services_for_window(self.window).canvas_document_service.new_canvas(self.window)

        self.assertIsNot(first_canvas, second_canvas)
        self.assertEqual(self.window.tab_references.canvas_count(), 2)
        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(2)],
            ["Canvas 1", "Canvas 2"],
        )
        self.assertIs(active_canvas_for_window(self.window), second_canvas)

    def test_preview_panel_tracks_active_canvas_rdkit_adapter(self) -> None:
        first_canvas = active_canvas_for_window(self.window)
        self.assertIs(preview_for_window(self.window).rdkit_adapter, first_canvas.rdkit)

        second_canvas = services_for_window(self.window).canvas_document_service.new_canvas(self.window)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertIs(preview_for_window(self.window).rdkit_adapter, second_canvas.rdkit)

        self.window.tab_references.canvas_tabs.setCurrentIndex(0)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertIs(preview_for_window(self.window).rdkit_adapter, first_canvas.rdkit)


if __name__ == "__main__":
    unittest.main()
