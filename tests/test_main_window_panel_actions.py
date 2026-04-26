import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QLineEdit, QToolButton
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.main_window import MainWindow


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window tests")
class MainWindowPanelActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def _find_button(self, *, tool_tip: str | None = None, object_name: str | None = None) -> QToolButton:
        for button in self.window.findChildren(QToolButton):
            if tool_tip is not None and button.toolTip() != tool_tip:
                continue
            if object_name is not None and button.objectName() != object_name:
                continue
            return button
        raise AssertionError(f"Could not find button with tool_tip={tool_tip!r} object_name={object_name!r}")

    def _find_action(self, text: str):
        for action in self.window.actions():
            if action.text() == text:
                return action
        raise AssertionError(f"Could not find action with text={text!r}")

    def _find_line_edit(self, placeholder: str) -> QLineEdit:
        for widget in self.window.findChildren(QLineEdit):
            if widget.placeholderText() == placeholder:
                return widget
        raise AssertionError(f"Could not find line edit with placeholder={placeholder!r}")

    def test_xyz_path_helpers_follow_current_file_and_suffix_rules(self) -> None:
        self.window._current_file_path = "/tmp/current.ldraw"
        self.assertEqual(self.window._default_save_dialog_path(), "/tmp/current.ldraw")
        self.assertEqual(self.window._default_xyz_export_path(), "/tmp/current.xyz")
        self.assertEqual(MainWindow._normalize_xyz_export_path(None), None)
        self.assertEqual(MainWindow._normalize_xyz_export_path(""), None)
        self.assertEqual(MainWindow._normalize_xyz_export_path("/tmp/export"), "/tmp/export.xyz")
        self.assertEqual(MainWindow._normalize_xyz_export_path("/tmp/export.xyz"), "/tmp/export.xyz")

    def test_document_action_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        self.window._document_action_service = service

        MainWindow._save_canvas_to_path(self.window, "/tmp/new.ldraw")
        MainWindow._save_canvas(self.window)
        MainWindow._save_canvas_as(self.window)
        MainWindow._export_xyz(self.window)
        MainWindow._load_canvas(self.window)

        self.assertEqual(service.save_canvas_to_path.call_args.args, (self.window, "/tmp/new.ldraw"))
        self.assertIn("message_box", service.save_canvas_to_path.call_args.kwargs)
        self.assertEqual(service.save_canvas.call_args.args, (self.window,))
        self.assertIn("resolve_save_path", service.save_canvas.call_args.kwargs)
        self.assertEqual(service.save_canvas_as.call_args.args, (self.window,))
        self.assertIn("file_dialog", service.save_canvas_as.call_args.kwargs)
        self.assertIn("resolve_save_as_path", service.save_canvas_as.call_args.kwargs)
        self.assertEqual(service.export_xyz.call_args.args, (self.window,))
        self.assertIn("file_dialog", service.export_xyz.call_args.kwargs)
        self.assertIn("message_box", service.export_xyz.call_args.kwargs)
        self.assertEqual(service.load_canvas.call_args.args, (self.window,))
        self.assertIn("file_dialog", service.load_canvas.call_args.kwargs)
        self.assertIn("message_box", service.load_canvas.call_args.kwargs)
        self.assertIn("read_document", service.load_canvas.call_args.kwargs)
        self.assertIn("resolve_load_path", service.load_canvas.call_args.kwargs)

    def test_save_action_prefers_current_path_and_falls_back_to_save_as(self) -> None:
        save_action = self._find_action("Save")
        save_as_called = mock.Mock()
        save_path = mock.Mock()

        self.window._current_file_path = "/tmp/existing.ldraw"
        self.window._save_canvas_to_path = save_path
        self.window._save_canvas_as = save_as_called
        save_action.trigger()
        save_path.assert_called_once_with("/tmp/existing.ldraw")
        save_as_called.assert_not_called()

        save_path.reset_mock()
        save_as_called.reset_mock()
        self.window._current_file_path = None
        save_action.trigger()
        save_as_called.assert_called_once_with()
        save_path.assert_not_called()

    def test_save_as_action_uses_default_dialog_path_and_normalizes_extension(self) -> None:
        save_as_action = self._find_action("Save As...")
        self.window._current_file_path = "/tmp/current.ldraw"
        save_path = mock.Mock()

        with mock.patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("/tmp/new-drawing", "")) as dialog:
            self.window._save_canvas_to_path = save_path
            save_as_action.trigger()

        dialog.assert_called_once()
        self.assertEqual(dialog.call_args.args[2], "/tmp/current.ldraw")
        save_path.assert_called_once_with("/tmp/new-drawing.ldraw")

    def test_load_button_uses_dialog_path_and_handles_failure(self) -> None:
        load_button = self._find_button(tool_tip="Load")
        restore = mock.Mock()

        with (
            mock.patch("ui.main_window.QFileDialog.getOpenFileName", return_value=("/tmp/input.ldraw", "")) as dialog,
            mock.patch("ui.main_window.read_document", return_value=SimpleNamespace(state={"atoms": []})) as read_document,
        ):
            self.window._restore_single_sheet_document = restore
            load_button.click()

        dialog.assert_called_once()
        read_document.assert_called_once_with("/tmp/input.ldraw")
        restore.assert_called_once_with({"atoms": []})
        self.assertEqual(self.window._current_file_path, "/tmp/input.ldraw")
        self.assertEqual(self.window.statusBar().currentMessage(), "Loaded: /tmp/input.ldraw")

        load_button = self._find_button(tool_tip="Load")
        with (
            mock.patch("ui.main_window.QFileDialog.getOpenFileName", return_value=("/tmp/broken.ldraw", "")),
            mock.patch("ui.main_window.read_document", side_effect=RuntimeError("bad file")),
            mock.patch("ui.main_window.QMessageBox.warning") as warning,
        ):
            self.window._current_file_path = "/tmp/previous.ldraw"
            load_button.click()

        warning.assert_called_once_with(self.window, "Load Error", "Failed to load file:\nbad file")
        self.assertEqual(self.window._current_file_path, "/tmp/previous.ldraw")

    def test_export_button_normalizes_path_and_reports_success_and_failure(self) -> None:
        export_button = self._find_button(tool_tip="Export 3D XYZ")
        self.assertFalse(export_button.isEnabled())
        self.window.canvas.model.add_atom("C", 0.0, 0.0)
        self.window._update_action_availability()
        self.assertTrue(export_button.isEnabled())

        with mock.patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("/tmp/output", "")) as dialog:
            self.window.canvas.export_xyz = mock.Mock()
            export_button.click()

        dialog.assert_called_once()
        self.assertEqual(dialog.call_args.args[2], "")
        self.window.canvas.export_xyz.assert_called_once_with("/tmp/output.xyz")
        self.assertEqual(self.window.statusBar().currentMessage(), "Exported XYZ: /tmp/output.xyz")

        with (
            mock.patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("/tmp/output", "")),
            mock.patch.object(self.window.canvas, "export_xyz", side_effect=RuntimeError("no exporter")),
            mock.patch("ui.main_window.QMessageBox.warning") as warning,
        ):
            export_button.click()

        warning.assert_called_once_with(self.window, "Export Error", "Failed to export XYZ:\nno exporter")

    def test_undo_redo_smiles_and_flip_buttons_call_canvas_methods(self) -> None:
        undo_button = self._find_button(tool_tip="Undo")
        redo_button = self._find_button(tool_tip="Redo")
        flip_h_button = self._find_button(tool_tip="Flip Horizontal (Ctrl+Shift+H)")
        flip_v_button = self._find_button(tool_tip="Flip Vertical (Ctrl+Shift+V)")
        smiles_button = self._find_button(object_name="smiles_render_button")
        smiles_input = self._find_line_edit("SMILES...")

        self.window.canvas.undo = mock.Mock()
        self.window.canvas.redo = mock.Mock()
        self.window.canvas.flip_horizontal = mock.Mock()
        self.window.canvas.flip_vertical = mock.Mock()
        self.window.canvas.begin_smiles_insert = mock.Mock()
        self.assertFalse(undo_button.isEnabled())
        self.assertFalse(redo_button.isEnabled())
        self.window.canvas._history = [object()]
        self.window.canvas._redo_stack = [object()]
        self.window._update_action_availability()
        self.assertTrue(undo_button.isEnabled())
        self.assertTrue(redo_button.isEnabled())

        undo_button.click()
        redo_button.click()
        flip_h_button.click()
        flip_v_button.click()
        smiles_input.setText("CCO")
        smiles_button.click()

        self.window.canvas.undo.assert_called_once_with()
        self.window.canvas.redo.assert_called_once_with()
        self.window.canvas.flip_horizontal.assert_called_once_with()
        self.window.canvas.flip_vertical.assert_called_once_with()
        self.window.canvas.begin_smiles_insert.assert_called_once_with("CCO")


if __name__ == "__main__":
    unittest.main()
