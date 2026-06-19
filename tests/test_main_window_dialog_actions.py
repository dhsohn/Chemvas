import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.main_window_service_ports import services_for_window


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window tests")
class MainWindowDialogActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_document_dialog_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "set_bond_length"))
        self.assertFalse(hasattr(self.window, "setup_sheet"))

    def test_canvas_and_sheet_name_helpers_cover_missing_active_canvas_paths(self) -> None:
        with mock.patch.object(type(self.window.tab_references), "active_canvas_or_none", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "No active canvas sheet."):
                _ = active_canvas_for_window(self.window)

        with mock.patch.object(type(self.window.tab_references), "active_canvas_tab_index", return_value=-1):
            self.assertEqual(self.window.tab_references.active_canvas_sheet_name(active_canvas_for_window(self.window)), "")

        self.assertEqual(self.window.runtime_state.next_result_canvas_name("Result"), "Result 1")
        self.assertEqual(self.window.runtime_state.next_result_canvas_name("Result"), "Result 2")

    def test_zoom_and_icon_factory_cover_residual_main_window_helpers(self) -> None:
        status_service = services_for_window(self.window).status_service

        self.assertFalse(hasattr(self.window, "update_zoom_label"))
        self.assertFalse(hasattr(self.window, "status_context_texts"))
        status_service.update_zoom_label(275)
        self.assertEqual(status_service.status_context_texts()["zoom"], "275%")

        icon_factory = mock.Mock()
        add_sheet_icon = object()
        setup_sheet_icon = object()
        preview_panel_icon = object()
        info_icon = object()
        double_icon = object()
        triple_icon = object()
        preview_icon = object()
        orbital_icon = object()
        move_icon = object()
        icon_factory.icon_add_sheet.return_value = add_sheet_icon
        icon_factory.icon_setup_sheet.return_value = setup_sheet_icon
        icon_factory.icon_preview_panel.return_value = preview_panel_icon
        icon_factory.icon_info.return_value = info_icon
        icon_factory.icon_bond_double.return_value = double_icon
        icon_factory.icon_bond_triple.return_value = triple_icon
        icon_factory.icon_orbital_preview.return_value = preview_icon
        icon_factory.icon_orbital.return_value = orbital_icon
        icon_factory.icon_move.return_value = move_icon
        self.window.ui_references.icon_factory = icon_factory

        self.assertFalse(hasattr(self.window, "_icon_add_sheet"))
        self.assertFalse(hasattr(self.window, "icon_factory"))
        factory = self.window.ui_references.require_icon_factory()
        self.assertIs(factory.icon_add_sheet(), add_sheet_icon)
        self.assertIs(factory.icon_setup_sheet(), setup_sheet_icon)
        self.assertIs(factory.icon_preview_panel(), preview_panel_icon)
        self.assertIs(factory.icon_info(), info_icon)
        self.assertIs(factory.icon_bond_double(), double_icon)
        self.assertIs(factory.icon_bond_triple(), triple_icon)
        self.assertIs(factory.icon_orbital_preview("sp2"), preview_icon)
        self.assertIs(factory.icon_orbital(), orbital_icon)
        self.assertIs(factory.icon_move(), move_icon)

    def test_status_bar_exposes_structured_context_and_transient_messages(self) -> None:
        status_service = services_for_window(self.window).status_service

        self.assertEqual(
            status_service.status_context_texts(),
            {
                "tool": "Tool: Bond",
                "sheet": "Sheet: Sheet 1 (1/1)",
                "selection": "Selection: 0",
                "chemical": "",
                "zoom_caption": "Zoom",
                "zoom": "100%",
            },
        )

        self.assertFalse(hasattr(self.window, "zoom_status_tip"))
        status_service.update_zoom_label(175)
        self.assertEqual(status_service.status_context_texts()["zoom"], "175%")
        self.assertEqual(status_service.zoom_status_tip(), "Zoom: 175%")

        self.assertFalse(hasattr(self.window, "show_status_message"))
        self.window.statusBar().showMessage("Saved")
        self.assertEqual(self.window.statusBar().currentMessage(), "Saved")


if __name__ == "__main__":
    unittest.main()
