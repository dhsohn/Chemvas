import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QLineEdit, QToolButton
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_history_state import history_state_for
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.main_window_service_ports import services_for_window
    from ui.main_window_ui_ports import panel_dock_for_window


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
        self.window.runtime_state.current_file_path = "/tmp/current.chemvas"
        service = services_for_window(self.window).document_action_service

        self.assertFalse(hasattr(self.window, "default_save_dialog_path"))
        self.assertFalse(hasattr(self.window, "default_xyz_export_path"))
        self.assertEqual(service.default_save_dialog_path(self.window), "/tmp/current.chemvas")
        self.assertEqual(service.default_xyz_export_path(self.window), "/tmp/current.xyz")
        self.assertFalse(hasattr(MainWindow, "normalize_xyz_export_path"))
        self.assertEqual(service.normalize_xyz_export_path(None), None)
        self.assertEqual(service.normalize_xyz_export_path(""), None)
        self.assertEqual(service.normalize_xyz_export_path("/tmp/export"), "/tmp/export.xyz")
        self.assertEqual(service.normalize_xyz_export_path("/tmp/export.xyz"), "/tmp/export.xyz")

    def test_document_action_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "save_canvas_to_path"))
        self.assertFalse(hasattr(self.window, "save_canvas"))
        self.assertFalse(hasattr(self.window, "save_canvas_as"))
        self.assertFalse(hasattr(self.window, "export_xyz"))
        self.assertFalse(hasattr(self.window, "export_figure"))
        self.assertFalse(hasattr(self.window, "load_canvas"))

    def test_save_action_prefers_current_path_and_falls_back_to_save_as(self) -> None:
        save_action = self._find_action("Save")
        save_as_called = mock.Mock()
        save_path = mock.Mock()
        document_service = services_for_window(self.window).document_action_service

        self.window.runtime_state.current_file_path = "/tmp/existing.chemvas"
        document_service.save_canvas_to_path = save_path
        document_service.save_canvas_as = save_as_called
        save_action.trigger()
        save_path.assert_called_once_with(self.window, "/tmp/existing.chemvas")
        save_as_called.assert_not_called()

        save_path.reset_mock()
        save_as_called.reset_mock()
        self.window.runtime_state.current_file_path = None
        save_action.trigger()
        save_as_called.assert_called_once_with(self.window)
        save_path.assert_not_called()

    def test_save_as_action_uses_default_dialog_path_and_normalizes_extension(self) -> None:
        save_as_action = self._find_action("Save As...")
        self.window.runtime_state.current_file_path = "/tmp/current.chemvas"
        save_path = mock.Mock()
        document_service = services_for_window(self.window).document_action_service

        with mock.patch(
            "ui.main_window_document_action_service.QFileDialog.getSaveFileName",
            return_value=("/tmp/new-drawing", ""),
        ) as dialog:
            document_service.save_canvas_to_path = save_path
            save_as_action.trigger()

        dialog.assert_called_once()
        self.assertEqual(dialog.call_args.args[2], "/tmp/current.chemvas")
        save_path.assert_called_once_with(self.window, "/tmp/new-drawing.chemvas")

    def test_load_menu_action_uses_dialog_path_and_handles_failure(self) -> None:
        load_action = self._find_action("Load")
        restore = mock.Mock()
        workbook_service = services_for_window(self.window).workbook_document_service

        with (
            mock.patch(
                "ui.main_window_document_action_service.QFileDialog.getOpenFileName",
                return_value=("/tmp/input.chemvas", ""),
            ) as dialog,
            mock.patch(
                "ui.main_window_document_action_service.default_read_document",
                return_value=SimpleNamespace(state={"atoms": []}),
            ) as read_document,
        ):
            workbook_service.restore_single_sheet_document = restore
            load_action.trigger()

        dialog.assert_called_once()
        read_document.assert_called_once_with("/tmp/input.chemvas")
        restore.assert_called_once_with(self.window, {"atoms": []})
        self.assertEqual(self.window.runtime_state.current_file_path, "/tmp/input.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Loaded: /tmp/input.chemvas")

        with (
            mock.patch(
                "ui.main_window_document_action_service.QFileDialog.getOpenFileName",
                return_value=("/tmp/broken.chemvas", ""),
            ),
            mock.patch(
                "ui.main_window_document_action_service.default_read_document",
                side_effect=RuntimeError("bad file"),
            ),
            mock.patch("ui.main_window_document_action_service.QMessageBox.warning") as warning,
        ):
            self.window.runtime_state.current_file_path = "/tmp/previous.chemvas"
            load_action.trigger()

        warning.assert_called_once_with(self.window, "Load Error", "Failed to load file:\nbad file")
        self.assertEqual(self.window.runtime_state.current_file_path, "/tmp/previous.chemvas")

    def test_export_button_normalizes_path_and_reports_success_and_failure(self) -> None:
        export_button = self._find_button(tool_tip="Export 3D XYZ")
        self.assertFalse(export_button.isEnabled())
        active_canvas_for_window(self.window).model.add_atom("C", 0.0, 0.0)
        services_for_window(self.window).action_availability_service.update_action_availability(self.window)
        self.assertTrue(export_button.isEnabled())

        with mock.patch(
            "ui.main_window_document_action_service.QFileDialog.getSaveFileName",
            return_value=("/tmp/output", ""),
        ) as dialog:
            doc_service = active_canvas_for_window(self.window).services.canvas_document_session_service
            doc_service.export_xyz_async = mock.Mock(
                side_effect=lambda path, *, on_success, on_error: on_success(path)
            )
            active_canvas_for_window(self.window).export_xyz_async = mock.Mock(
                side_effect=AssertionError("canvas export_xyz_async wrapper should not run")
            )
            export_button.click()

        dialog.assert_called_once()
        self.assertEqual(dialog.call_args.args[2], "")
        self.assertEqual(doc_service.export_xyz_async.call_args.args, ("/tmp/output.xyz",))
        active_canvas_for_window(self.window).export_xyz_async.assert_not_called()
        self.assertEqual(self.window.statusBar().currentMessage(), "Exported XYZ: /tmp/output.xyz")

        with (
            mock.patch(
                "ui.main_window_document_action_service.QFileDialog.getSaveFileName",
                return_value=("/tmp/output", ""),
            ),
            mock.patch.object(
                active_canvas_for_window(self.window).services.canvas_document_session_service,
                "export_xyz_async",
                side_effect=lambda path, *, on_success, on_error: on_error("no exporter"),
            ),
            mock.patch("ui.main_window_document_action_service.QMessageBox.warning") as warning,
        ):
            export_button.click()

        warning.assert_called_once_with(self.window, "Export Error", "Failed to export XYZ:\nno exporter")

    def test_preview_panel_button_hides_and_shows_right_dock(self) -> None:
        preview_button = self._find_button(object_name="preview_panel_button")
        panel_dock = panel_dock_for_window(self.window)
        self.assertIsNotNone(panel_dock)
        self.assertTrue(preview_button.isCheckable())
        self.assertTrue(preview_button.isChecked())
        self.assertFalse(panel_dock.isHidden())

        preview_button.click()

        self.assertTrue(panel_dock.isHidden())
        self.assertFalse(preview_button.isChecked())

        preview_button.click()

        self.assertFalse(panel_dock.isHidden())
        self.assertTrue(preview_button.isChecked())

    def test_undo_redo_smiles_and_flip_buttons_call_canvas_and_controllers(self) -> None:
        undo_button = self._find_button(tool_tip="Undo")
        redo_button = self._find_button(tool_tip="Redo")
        flip_h_button = self._find_button(tool_tip="Flip Horizontal (Ctrl+Shift+H)")
        flip_v_button = self._find_button(tool_tip="Flip Vertical (Ctrl+Shift+V)")
        smiles_button = self._find_button(object_name="smiles_render_button")
        smiles_input = self._find_line_edit("SMILES...")

        active_canvas_for_window(self.window).undo = mock.Mock(side_effect=AssertionError("canvas undo wrapper should not run"))
        active_canvas_for_window(self.window).redo = mock.Mock(side_effect=AssertionError("canvas redo wrapper should not run"))
        history_service = active_canvas_for_window(self.window).runtime_state.history_service
        history_service.undo = mock.Mock()
        history_service.redo = mock.Mock()
        active_canvas_for_window(self.window).flip_horizontal = mock.Mock(side_effect=AssertionError("canvas flip wrapper should not run"))
        active_canvas_for_window(self.window).flip_vertical = mock.Mock(side_effect=AssertionError("canvas flip wrapper should not run"))
        active_canvas_for_window(self.window).begin_smiles_insert = mock.Mock(
            side_effect=AssertionError("canvas SMILES wrapper should not run")
        )
        scene_transform = active_canvas_for_window(self.window).services.scene_transform_controller
        scene_transform.flip_selected_items = mock.Mock()
        insert_controller = active_canvas_for_window(self.window).services.insert_controller
        insert_controller.begin_smiles_insert = mock.Mock()
        self.assertFalse(undo_button.isEnabled())
        self.assertFalse(redo_button.isEnabled())
        history_state_for(active_canvas_for_window(self.window)).history = [object()]
        history_state_for(active_canvas_for_window(self.window)).redo_stack = [object()]
        services_for_window(self.window).action_availability_service.update_action_availability(self.window)
        self.assertTrue(undo_button.isEnabled())
        self.assertTrue(redo_button.isEnabled())

        undo_button.click()
        redo_button.click()
        flip_h_button.click()
        flip_v_button.click()
        smiles_input.setText("CCO")
        smiles_button.click()

        history_service.undo.assert_called_once_with()
        history_service.redo.assert_called_once_with()
        active_canvas_for_window(self.window).undo.assert_not_called()
        active_canvas_for_window(self.window).redo.assert_not_called()
        scene_transform.flip_selected_items.assert_has_calls(
            [
                mock.call(horizontal=True),
                mock.call(horizontal=False),
            ]
        )
        active_canvas_for_window(self.window).flip_horizontal.assert_not_called()
        active_canvas_for_window(self.window).flip_vertical.assert_not_called()
        insert_controller.begin_smiles_insert.assert_called_once_with("CCO")
        active_canvas_for_window(self.window).begin_smiles_insert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
