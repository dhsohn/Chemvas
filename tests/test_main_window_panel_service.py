import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QMainWindow,
        QToolButton,
        QWidget,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_panel_service import MainWindowPanelService
    from ui.main_window_ui_ports import (
        apply_panel_assembly_for_window,
        panel_dock_for_window,
        panel_splitter_for_window,
    )
    from ui.main_window_ui_references import MainWindowUiReferences


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window panel service tests")
class MainWindowPanelServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_init_panels_installs_assembly_and_syncs_preview_button(self) -> None:
        window = QMainWindow()
        window.ui_references = MainWindowUiReferences()
        self.addCleanup(window.close)
        preview_3d = QWidget()
        preview_panel_button = QToolButton()
        preview_panel_button.setCheckable(True)
        service = MainWindowPanelService(
            preview_for_window=mock.Mock(return_value=preview_3d),
            apply_panel_assembly_for_window=apply_panel_assembly_for_window,
            panel_dock_for_window=panel_dock_for_window,
            preview_panel_button_for_window=mock.Mock(return_value=preview_panel_button),
        )

        service.init_panels(window)

        panel_splitter = panel_splitter_for_window(window)
        panel_dock = panel_dock_for_window(window)
        self.assertIsNotNone(panel_splitter)
        self.assertIsNotNone(panel_dock)
        self.assertIs(panel_splitter.widget(0), preview_3d)
        self.assertIs(panel_dock.widget(), panel_splitter)
        self.assertEqual(preview_panel_button.isChecked(), not panel_dock.isHidden())

        panel_dock.hide()
        self.app.processEvents()
        self.assertFalse(preview_panel_button.isChecked())

    def test_toggle_preview_panel_handles_missing_dock_and_syncs_button(self) -> None:
        button = mock.Mock()
        preview_for_window = mock.Mock()
        preview_panel_button_for_window = mock.Mock(return_value=button)
        service = MainWindowPanelService(
            preview_for_window=preview_for_window,
            apply_panel_assembly_for_window=mock.Mock(),
            panel_dock_for_window=panel_dock_for_window,
            preview_panel_button_for_window=preview_panel_button_for_window,
        )
        missing_window = SimpleNamespace(ui_references=MainWindowUiReferences())

        service.toggle_preview_panel(missing_window)

        button.setChecked.assert_not_called()

        dock = mock.Mock()
        dock.isHidden.side_effect = [True, False]
        window = SimpleNamespace(ui_references=SimpleNamespace(panel_dock=dock))

        service.toggle_preview_panel(window)

        dock.setVisible.assert_called_once_with(True)
        dock.raise_.assert_called_once_with()
        button.blockSignals.assert_has_calls([mock.call(True), mock.call(button.blockSignals.return_value)])
        button.setChecked.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
