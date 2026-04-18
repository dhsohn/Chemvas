import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QDialog, QDoubleSpinBox, QPushButton, QToolButton
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_document_action_service import MainWindowDocumentActionService
    from ui.main_window_path_logic import resolve_load_path, resolve_save_as_path, resolve_save_path


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window document action tests")
class MainWindowDocumentActionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.service = MainWindowDocumentActionService()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_save_canvas_to_path_success_updates_state_and_status(self) -> None:
        message_box = mock.Mock()
        self.window._current_file_path = "/tmp/old.ldraw"
        self.window._save_document_state = mock.Mock()

        result = self.service.save_canvas_to_path(self.window, "/tmp/new.ldraw", message_box=message_box)

        self.assertTrue(result)
        self.window._save_document_state.assert_called_once_with("/tmp/new.ldraw")
        self.assertEqual(self.window._current_file_path, "/tmp/new.ldraw")
        self.assertEqual(self.window.statusBar().currentMessage(), "Saved: /tmp/new.ldraw")
        message_box.warning.assert_not_called()

    def test_save_canvas_to_path_failure_warns_and_keeps_previous_path(self) -> None:
        message_box = mock.Mock()
        self.window._current_file_path = "/tmp/old.ldraw"
        self.window._save_document_state = mock.Mock(side_effect=RuntimeError("boom"))

        result = self.service.save_canvas_to_path(self.window, "/tmp/new.ldraw", message_box=message_box)

        self.assertFalse(result)
        self.assertEqual(self.window._current_file_path, "/tmp/old.ldraw")
        message_box.warning.assert_called_once_with(self.window, "Save Error", "Failed to save file:\nboom")

    def test_save_canvas_prefers_current_path_and_falls_back_to_save_as(self) -> None:
        self.window._current_file_path = "/tmp/existing.ldraw"
        self.window._save_canvas_to_path = mock.Mock()
        self.window._save_canvas_as = mock.Mock()

        self.service.save_canvas(self.window, resolve_save_path=resolve_save_path)

        self.window._save_canvas_to_path.assert_called_once_with("/tmp/existing.ldraw")
        self.window._save_canvas_as.assert_not_called()

        self.window._current_file_path = None
        self.window._save_canvas_to_path.reset_mock()
        self.window._save_canvas_as.reset_mock()

        self.service.save_canvas(self.window, resolve_save_path=resolve_save_path)

        self.window._save_canvas_as.assert_called_once_with()
        self.window._save_canvas_to_path.assert_not_called()

    def test_save_canvas_as_uses_default_dialog_path_and_normalizes_extension(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/new-drawing", "")
        self.window._current_file_path = "/tmp/current.ldraw"
        self.window._save_canvas_to_path = mock.Mock()

        self.service.save_canvas_as(self.window, file_dialog=file_dialog, resolve_save_as_path=resolve_save_as_path)

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "/tmp/current.ldraw")
        self.window._save_canvas_to_path.assert_called_once_with("/tmp/new-drawing.ldraw")

    def test_export_xyz_normalizes_path_and_reports_success_and_failure(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/output", "")
        message_box = mock.Mock()
        self.window.canvas.export_xyz = mock.Mock()

        self.service.export_xyz(self.window, file_dialog=file_dialog, message_box=message_box)

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "")
        self.window.canvas.export_xyz.assert_called_once_with("/tmp/output.xyz")
        self.assertEqual(self.window.statusBar().currentMessage(), "Exported XYZ: /tmp/output.xyz")
        message_box.warning.assert_not_called()

        file_dialog.getSaveFileName.reset_mock(return_value=True)
        file_dialog.getSaveFileName.return_value = ("/tmp/output", "")
        self.window.canvas.export_xyz = mock.Mock(side_effect=RuntimeError("no exporter"))

        self.service.export_xyz(self.window, file_dialog=file_dialog, message_box=message_box)

        message_box.warning.assert_called_once_with(self.window, "Export Error", "Failed to export XYZ:\nno exporter")

    def test_load_canvas_dispatches_single_sheet_and_workbook_states(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getOpenFileName.return_value = ("/tmp/input.ldraw", "")
        message_box = mock.Mock()
        self.window._restore_single_sheet_document = mock.Mock()
        self.window._restore_workbook_document = mock.Mock()

        self.service.load_canvas(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            read_document=mock.Mock(return_value=SimpleNamespace(state={"atoms": []})),
            resolve_load_path=resolve_load_path,
        )

        self.window._restore_single_sheet_document.assert_called_once_with({"atoms": []})
        self.window._restore_workbook_document.assert_not_called()
        self.assertEqual(self.window._current_file_path, "/tmp/input.ldraw")
        self.assertEqual(self.window.statusBar().currentMessage(), "Loaded: /tmp/input.ldraw")

        self.window._restore_single_sheet_document.reset_mock()
        self.window._restore_workbook_document.reset_mock()

        self.service.load_canvas(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            read_document=mock.Mock(return_value=SimpleNamespace(state={"sheets": [{"name": "Sheet 1"}]})),
            resolve_load_path=resolve_load_path,
        )

        self.window._restore_workbook_document.assert_called_once_with({"sheets": [{"name": "Sheet 1"}]})
        self.window._restore_single_sheet_document.assert_not_called()

    def test_load_canvas_warns_on_read_failure(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getOpenFileName.return_value = ("/tmp/broken.ldraw", "")
        message_box = mock.Mock()
        self.window._current_file_path = "/tmp/previous.ldraw"

        self.service.load_canvas(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            read_document=mock.Mock(side_effect=RuntimeError("bad file")),
            resolve_load_path=resolve_load_path,
        )

        message_box.warning.assert_called_once_with(self.window, "Load Error", "Failed to load file:\nbad file")
        self.assertEqual(self.window._current_file_path, "/tmp/previous.ldraw")

    def test_set_bond_length_uses_dialog_controls_and_applies_confirmed_value(self) -> None:
        renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=24.0))

        def drive_dialog(dialog: QDialog):
            self.assertEqual(dialog.windowTitle(), "Bond Length")

            spin = dialog.findChild(QDoubleSpinBox)
            ok_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "OK")
            cancel_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Cancel")
            up_button = dialog.findChild(QToolButton, "spinUpButton")
            down_button = dialog.findChild(QToolButton, "spinDownButton")

            self.assertIsNotNone(spin)
            self.assertIsNotNone(up_button)
            self.assertIsNotNone(down_button)
            self.assertEqual(spin.value(), 24.0)
            self.assertEqual(spin.minimum(), 10.0)
            self.assertEqual(spin.maximum(), 200.0)
            self.assertEqual(spin.decimals(), 1)

            up_button.click()
            up_button.click()
            down_button.click()
            self.assertEqual(spin.value(), 25.0)
            self.assertEqual(ok_button.text(), "OK")
            self.assertEqual(cancel_button.text(), "Cancel")
            ok_button.click()

            return QDialog.DialogCode.Accepted

        with (
            mock.patch.object(self.window.canvas, "renderer", new=renderer),
            mock.patch.object(self.window.canvas, "set_bond_length") as set_bond_length,
            mock.patch("ui.main_window_document_action_service.QDialog.exec", new=drive_dialog),
        ):
            self.service.set_bond_length(self.window)

        set_bond_length.assert_called_once_with(25.0)


if __name__ == "__main__":
    unittest.main()
