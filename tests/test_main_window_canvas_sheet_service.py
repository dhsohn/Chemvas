import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QFont
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QPointF = None
    QFont = None
    QTest = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    try:
        from ui.main_window import MainWindow
        from ui.main_window_canvas_sheet_service import MainWindowCanvasSheetService
    except SyntaxError:
        MainWindow = None
        MainWindowCanvasSheetService = None
else:
    MainWindow = None
    MainWindowCanvasSheetService = None


@unittest.skipUnless(
    QApplication is not None and MainWindow is not None and MainWindowCanvasSheetService is not None,
    "PyQt6 and canvas sheet service are required for tests",
)
class MainWindowCanvasSheetServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        QTest.qWait(20)
        self.service = MainWindowCanvasSheetService()
        self._extra_canvases = []

    def tearDown(self) -> None:
        for canvas in self._extra_canvases:
            canvas.deleteLater()
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_create_canvas_copies_template_settings_and_clears_frame_style(self) -> None:
        template = self.window.canvas
        template.renderer.set_bond_length(42.0)
        template.arrow_line_width = 3.25
        template.arrow_head_scale = 0.55
        template.orbital_phase_enabled = True
        template.text_font_size = 16
        template.text_font_weight = QFont.Weight.Bold
        template.text_italic = True
        template.mark_kind = "minus"

        canvas = self.service.create_canvas(self.window, template=template)
        self._extra_canvases.append(canvas)

        self.assertEqual(canvas.frameStyle(), 0)
        self.assertEqual(canvas.renderer.style.bond_length_px, 42.0)
        self.assertEqual(canvas.arrow_line_width, 3.25)
        self.assertEqual(canvas.arrow_head_scale, 0.55)
        self.assertTrue(canvas.orbital_phase_enabled)
        self.assertEqual(canvas.text_font_size, 16)
        self.assertEqual(canvas.text_font_weight, QFont.Weight.Bold)
        self.assertTrue(canvas.text_italic)
        self.assertEqual(canvas.mark_kind, "minus")

    def test_add_canvas_sheet_inserts_before_plus_tab_restores_state_and_keeps_selection(self) -> None:
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        state = self.window.canvas.snapshot_state()

        with mock.patch.object(self.window, "_bind_active_canvas") as bind_active_canvas:
            canvas = self.service.add_canvas_sheet(
                self.window,
                name="Imported",
                state=state,
                select=False,
                template=self.window.canvas,
            )

        self.assertEqual(self.window.canvas_tabs.tabText(1), "Imported")
        self.assertEqual(self.window.canvas_tabs.tabText(self.window.canvas_tabs.count() - 1), "+")
        self.assertEqual(self.window.canvas_tabs.currentIndex(), 0)
        self.assertEqual(len(canvas.model.bonds), 1)
        bind_active_canvas.assert_called_once_with()

    def test_open_result_canvas_sheet_supports_exact_name_and_generated_prefix(self) -> None:
        self.window.canvas.arrow_line_width = 4.5

        exact_name, exact_canvas = self.service.open_result_canvas_sheet(
            self.window,
            "Mechanism Summary",
            select=True,
            exact_name=True,
        )
        prefixed_name, prefixed_canvas = self.service.open_result_canvas_sheet(
            self.window,
            "Product",
            select=False,
            exact_name=False,
        )

        self.assertEqual(exact_name, "Mechanism Summary")
        self.assertEqual(self.window.canvas_tabs.tabText(1), "Mechanism Summary")
        self.assertIsNotNone(exact_canvas)
        self.assertTrue(prefixed_name.startswith("Product "))
        self.assertEqual(self.window.canvas_tabs.tabText(2), prefixed_name)
        self.assertEqual(prefixed_canvas.arrow_line_width, 4.5)
        self.assertEqual(self.window.canvas_tabs.tabText(self.window.canvas_tabs.count() - 1), "+")

    def test_new_canvas_sheet_uses_active_canvas_template_and_next_sheet_name(self) -> None:
        self.window.canvas.mark_kind = "radical"

        canvas = self.service.new_canvas_sheet(self.window)

        self.assertEqual(self.window.canvas_tabs.tabText(1), "Sheet 2")
        self.assertEqual(canvas.mark_kind, "radical")
        self.assertIs(self.window.canvas_tabs.currentWidget(), canvas)


if __name__ == "__main__":
    unittest.main()
