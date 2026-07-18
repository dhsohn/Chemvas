import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.main_window_panel_service import MainWindowPanelService
    from chemvas.ui.main_window_ports import (
        apply_preview_window_assembly_for_window,
        preview_window_for_window,
    )
    from chemvas.ui.main_window_ui_references import MainWindowUiReferences

    class _PreviewWidget(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.set_export_xyz_action = mock.Mock()


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for main window panel service tests"
)
class MainWindowPanelServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_init_panels_installs_hidden_preview_window(self) -> None:
        window = QMainWindow()
        window.ui_references = MainWindowUiReferences()
        self.addCleanup(window.close)
        preview_3d = _PreviewWidget()
        export_xyz_for_window = mock.Mock()
        service = MainWindowPanelService(
            preview_for_window=mock.Mock(return_value=preview_3d),
            active_canvas_for_window=mock.Mock(),
            export_xyz_for_window=export_xyz_for_window,
            apply_preview_window_assembly_for_window=apply_preview_window_assembly_for_window,
            preview_window_for_window=preview_window_for_window,
        )

        service.init_panels(window)

        preview_window = preview_window_for_window(window)
        self.assertIsNotNone(preview_window)
        self.assertIs(preview_3d.parent(), preview_window)
        self.assertFalse(preview_window.isVisible())
        export_callback = preview_3d.set_export_xyz_action.call_args.args[0]
        export_callback()
        export_xyz_for_window.assert_called_once_with(
            window,
            selected_only=True,
            dialog_parent=preview_window,
            status_sink=preview_window.show_export_status,
        )

    def test_open_preview_window_handles_missing_window_and_refreshes_selected_canvas(
        self,
    ) -> None:
        preview = mock.Mock()
        preview_for_window = mock.Mock(return_value=preview)
        active_canvas_for_window = mock.Mock(
            return_value=SimpleNamespace(rdkit=object())
        )
        service = MainWindowPanelService(
            preview_for_window=preview_for_window,
            active_canvas_for_window=active_canvas_for_window,
            export_xyz_for_window=mock.Mock(),
            apply_preview_window_assembly_for_window=mock.Mock(),
            preview_window_for_window=preview_window_for_window,
        )
        missing_window = SimpleNamespace(ui_references=MainWindowUiReferences())

        service.open_preview_window(missing_window)

        preview.set_rdkit_adapter.assert_not_called()

        preview_window = mock.Mock()
        window = SimpleNamespace(
            ui_references=SimpleNamespace(preview_window=preview_window)
        )

        service.open_preview_window(window)

        preview.set_rdkit_adapter.assert_called_once_with(
            active_canvas_for_window.return_value.rdkit
        )
        preview.refresh_selected_from_canvas.assert_called_once_with(
            active_canvas_for_window.return_value
        )
        preview_window.show.assert_called_once_with()
        preview_window.raise_.assert_called_once_with()
        preview_window.activateWindow.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
