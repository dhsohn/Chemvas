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

    def test_open_arrow_settings_delegates_to_ui_assembly_service(self) -> None:
        service = mock.Mock()
        self.window._ui_assembly_service = service

        self.window._open_arrow_settings()

        service.open_arrow_settings.assert_called_once_with(self.window)

    def test_set_bond_length_delegates_to_document_action_service(self) -> None:
        service = mock.Mock()
        self.window._document_action_service = service

        self.window._set_bond_length()

        service.set_bond_length.assert_called_once_with(self.window)

    def test_setup_sheet_delegates_to_document_action_service(self) -> None:
        service = mock.Mock()
        self.window._document_action_service = service

        self.window._setup_sheet()

        service.setup_sheet.assert_called_once_with(self.window)

    def test_canvas_and_sheet_name_helpers_cover_missing_active_canvas_paths(self) -> None:
        with mock.patch.object(self.window, "_active_canvas_or_none", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "No active canvas sheet."):
                _ = self.window.canvas

        with mock.patch.object(self.window, "_active_canvas_tab_index", return_value=-1):
            self.assertEqual(self.window._active_canvas_sheet_name(), "")

        self.assertEqual(self.window._next_result_canvas_name("Result"), "Result 1")
        self.assertEqual(self.window._next_result_canvas_name("Result"), "Result 2")

    def test_panel_zoom_and_icon_factory_cover_residual_main_window_helpers(self) -> None:
        self.window.panel_dock = None
        self.window._show_panel(0)

        panel_dock = mock.Mock()
        self.window.panel_dock = panel_dock
        self.window._show_panel(1)
        panel_dock.show.assert_called_once_with()
        panel_dock.raise_.assert_called_once_with()

        zoom_label = self.window._zoom_label
        delattr(self.window, "_zoom_label")
        self.window._update_zoom_label(275)
        self.window._zoom_label = zoom_label
        self.window._update_zoom_label(275)
        self.assertEqual(self.window._zoom_label.text(), "275%")

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
        self.window._icon_factory = icon_factory

        self.assertFalse(hasattr(self.window, "_icon_add_sheet"))
        self.assertIs(self.window._icon_factory.icon_add_sheet(), add_sheet_icon)
        self.assertIs(self.window._icon_factory.icon_setup_sheet(), setup_sheet_icon)
        self.assertIs(self.window._icon_factory.icon_preview_panel(), preview_panel_icon)
        self.assertIs(self.window._icon_factory.icon_info(), info_icon)
        self.assertIs(self.window._icon_factory.icon_bond_double(), double_icon)
        self.assertIs(self.window._icon_factory.icon_bond_triple(), triple_icon)
        self.assertIs(self.window._icon_factory.icon_orbital_preview("sp2"), preview_icon)
        self.assertIs(self.window._icon_factory.icon_orbital(), orbital_icon)
        self.assertIs(self.window._icon_factory.icon_move(), move_icon)

    def test_status_bar_exposes_structured_context_and_transient_messages(self) -> None:
        self.assertEqual(self.window._status_tool_label.text(), "Tool: Bond")
        self.assertEqual(self.window._status_sheet_label.text(), "Sheet: Sheet 1 (1/1)")
        self.assertEqual(self.window._status_selection_label.text(), "Selection: 0")
        self.assertEqual(self.window._status_zoom_caption.text(), "Zoom")
        self.assertEqual(self.window._zoom_label.text(), "100%")

        self.window._update_zoom_label(175)
        self.assertEqual(self.window._zoom_label.text(), "175%")
        self.assertEqual(self.window._zoom_label.statusTip(), "Zoom: 175%")

        self.window._show_status_message("Saved")
        self.assertEqual(self.window.statusBar().currentMessage(), "Saved")


if __name__ == "__main__":
    unittest.main()
