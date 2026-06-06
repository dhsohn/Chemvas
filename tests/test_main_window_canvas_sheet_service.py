import os
import unittest
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

if QApplication is not None:
    try:
        from ui.canvas_text_style_state import set_text_style_for, text_style_state_for
        from ui.canvas_tool_settings_state import (
            set_tool_setting_for,
            tool_settings_state_for,
        )
        from ui.canvas_window_access import snapshot_canvas_state_for
        from ui.main_window import MainWindow
        from ui.main_window_canvas_ports import active_canvas_for_window
        from ui.main_window_canvas_sheet_service import MainWindowCanvasSheetService
        from ui.main_window_service_ports import services_for_window
        from ui.sheet_setup_access import set_sheet_setup_for
        from ui.structure_mutation_access import add_bond_between_points_for
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
        self.tab_ui = mock.Mock(wraps=services_for_window(self.window).canvas_tab_ui_service)
        self.active_canvas_ui = mock.Mock(wraps=services_for_window(self.window).active_canvas_ui_service)
        self.service = MainWindowCanvasSheetService(
            tab_ui=self.tab_ui,
            active_canvas_ui=self.active_canvas_ui,
            tab_refs_for_window=lambda window: window.tab_references,
            active_canvas_for_window=active_canvas_for_window,
            next_canvas_sheet_name_for_window=lambda window, prefix="Sheet": window.runtime_state.next_canvas_sheet_name(
                prefix
            ),
        )
        self._extra_canvases = []

    def tearDown(self) -> None:
        for canvas in self._extra_canvases:
            canvas.deleteLater()
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_create_canvas_copies_template_settings_and_clears_frame_style(self) -> None:
        template = active_canvas_for_window(self.window)
        template.renderer.set_bond_length(42.0)
        set_tool_setting_for(template, "arrow_line_width", 3.25)
        set_tool_setting_for(template, "arrow_head_scale", 0.55)
        set_tool_setting_for(template, "orbital_phase_enabled", True)
        set_text_style_for(template, "text_font_size", 16)
        set_text_style_for(template, "text_font_weight", QFont.Weight.Bold)
        set_text_style_for(template, "text_italic", True)
        set_tool_setting_for(template, "mark_kind", "minus")
        set_sheet_setup_for(template, "A4", "portrait")

        canvas = self.service.create_canvas(self.window, template=template)
        self._extra_canvases.append(canvas)

        self.assertEqual(canvas.frameStyle(), 0)
        self.assertEqual(canvas.renderer.style.bond_length_px, 42.0)
        self.assertEqual(canvas.sheet_size, "A4")
        self.assertEqual(canvas.sheet_orientation, "portrait")
        self.assertEqual(tool_settings_state_for(canvas).arrow_line_width, 3.25)
        self.assertEqual(tool_settings_state_for(canvas).arrow_head_scale, 0.55)
        self.assertTrue(tool_settings_state_for(canvas).orbital_phase_enabled)
        self.assertEqual(text_style_state_for(canvas).text_font_size, 16)
        self.assertEqual(text_style_state_for(canvas).text_font_weight, QFont.Weight.Bold)
        self.assertTrue(text_style_state_for(canvas).text_italic)
        self.assertEqual(tool_settings_state_for(canvas).mark_kind, "minus")

    def test_add_canvas_sheet_inserts_before_plus_tab_restores_state_and_keeps_selection(self) -> None:
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        state = snapshot_canvas_state_for(active_canvas_for_window(self.window))

        canvas = self.service.add_canvas_sheet(
            self.window,
            name="Imported",
            state=state,
            select=False,
            template=active_canvas_for_window(self.window),
        )

        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(1), "Imported")
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(self.window.tab_references.canvas_tabs.count() - 1), "+")
        self.assertEqual(self.window.tab_references.canvas_tabs.currentIndex(), 0)
        self.assertEqual(len(canvas.model.bonds), 1)
        self.tab_ui.ensure_add_sheet_tab.assert_called_once_with(self.window)
        self.active_canvas_ui.bind_active_canvas.assert_called_once_with(self.window)

    def test_open_result_canvas_sheet_supports_exact_name_and_generated_prefix(self) -> None:
        set_tool_setting_for(active_canvas_for_window(self.window), "arrow_line_width", 4.5)

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
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(1), "Mechanism Summary")
        self.assertIsNotNone(exact_canvas)
        self.assertTrue(prefixed_name.startswith("Product "))
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(2), prefixed_name)
        self.assertEqual(tool_settings_state_for(prefixed_canvas).arrow_line_width, 4.5)
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(self.window.tab_references.canvas_tabs.count() - 1), "+")

    def test_new_canvas_sheet_uses_active_canvas_template_and_next_sheet_name(self) -> None:
        set_tool_setting_for(active_canvas_for_window(self.window), "mark_kind", "radical")

        canvas = self.service.new_canvas_sheet(self.window)

        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(1), "Sheet 2")
        self.assertEqual(tool_settings_state_for(canvas).mark_kind, "radical")
        self.assertIs(self.window.tab_references.canvas_tabs.currentWidget(), canvas)


if __name__ == "__main__":
    unittest.main()
