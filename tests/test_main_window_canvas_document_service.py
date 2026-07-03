import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QPointF = None
    QTest = None

if QApplication is not None:
    from ui.canvas_document_metadata_state import document_file_path_for
    from ui.canvas_window_access import snapshot_canvas_state_for
    from ui.main_window import MainWindow
    from ui.main_window_ports import active_canvas_for_window, services_for_window
    from ui.structure_mutation_access import add_bond_between_points_for


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas document service tests")
class MainWindowCanvasDocumentServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        QTest.qWait(20)
        self.service = services_for_window(self.window).canvas_document_service

    def tearDown(self) -> None:
        for canvas in self.window.tab_references.all_canvases():
            self.service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_bootstrap_creates_clean_canvas_one(self) -> None:
        canvas = active_canvas_for_window(self.window)

        self.assertEqual(self.window.tab_references.canvas_count(), 1)
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(0), "Canvas 1")
        self.assertIsNone(document_file_path_for(canvas))
        self.assertFalse(self.service.is_dirty(canvas))

    def test_new_canvas_creates_independent_clean_canvas_with_template_settings(self) -> None:
        first = active_canvas_for_window(self.window)
        first.renderer.set_bond_length(42.0)

        second = self.service.new_canvas(self.window)

        self.assertIsNot(first, second)
        self.assertEqual(self.window.tab_references.canvas_count(), 2)
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(1), "Canvas 2")
        self.assertIs(self.window.tab_references.canvas_tabs.currentWidget(), second)
        self.assertEqual(second.renderer.style.bond_length_px, 42.0)
        self.assertFalse(self.service.is_dirty(second))

    def test_open_state_reuses_only_clean_untitled_single_canvas(self) -> None:
        first = active_canvas_for_window(self.window)
        add_bond_between_points_for(first, QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        state = snapshot_canvas_state_for(first)
        services_for_window(self.window).document_action_service.save_canvas_to_path(
            self.window,
            "/tmp/first.chemvas",
        )

        opened = self.service.open_state(self.window, state=state, file_path="/tmp/opened.chemvas")

        self.assertIsNot(opened, first)
        self.assertEqual(self.window.tab_references.canvas_count(), 2)
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(1), "opened.chemvas")
        self.assertEqual(document_file_path_for(opened), "/tmp/opened.chemvas")

    def test_dirty_state_uses_snapshot_digest(self) -> None:
        canvas = active_canvas_for_window(self.window)
        self.assertFalse(self.service.is_dirty(canvas))

        add_bond_between_points_for(canvas, QPointF(-20.0, 0.0), QPointF(20.0, 0.0))

        self.assertTrue(self.service.is_dirty(canvas))
        self.service.mark_clean(canvas)
        self.assertFalse(self.service.is_dirty(canvas))


if __name__ == "__main__":
    unittest.main()
