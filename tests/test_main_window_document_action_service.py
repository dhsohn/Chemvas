import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QPushButton,
        QToolButton,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_document_action_service import MainWindowDocumentActionService
    from ui.main_window_path_logic import (
        resolve_load_path,
        resolve_save_as_path,
        resolve_save_path,
    )


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
        self.window._current_file_path = "/tmp/old.chemvas"
        self.window._save_document_state = mock.Mock()

        result = self.service.save_canvas_to_path(self.window, "/tmp/new.chemvas", message_box=message_box)

        self.assertTrue(result)
        self.window._save_document_state.assert_called_once_with("/tmp/new.chemvas")
        self.assertEqual(self.window._current_file_path, "/tmp/new.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Saved: /tmp/new.chemvas")
        message_box.warning.assert_not_called()

    def test_save_canvas_to_path_failure_warns_and_keeps_previous_path(self) -> None:
        message_box = mock.Mock()
        self.window._current_file_path = "/tmp/old.chemvas"
        self.window._save_document_state = mock.Mock(side_effect=RuntimeError("boom"))

        result = self.service.save_canvas_to_path(self.window, "/tmp/new.chemvas", message_box=message_box)

        self.assertFalse(result)
        self.assertEqual(self.window._current_file_path, "/tmp/old.chemvas")
        message_box.warning.assert_called_once_with(self.window, "Save Error", "Failed to save file:\nboom")

    def test_save_canvas_prefers_current_path_and_falls_back_to_save_as(self) -> None:
        self.window._current_file_path = "/tmp/existing.chemvas"
        self.window._save_canvas_to_path = mock.Mock()
        self.window._save_canvas_as = mock.Mock()

        self.service.save_canvas(self.window, resolve_save_path=resolve_save_path)

        self.window._save_canvas_to_path.assert_called_once_with("/tmp/existing.chemvas")
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
        self.window._current_file_path = "/tmp/current.chemvas"
        self.window._save_canvas_to_path = mock.Mock()

        self.service.save_canvas_as(self.window, file_dialog=file_dialog, resolve_save_as_path=resolve_save_as_path)

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "/tmp/current.chemvas")
        self.window._save_canvas_to_path.assert_called_once_with("/tmp/new-drawing.chemvas")

    def test_export_xyz_normalizes_path_and_reports_success_and_failure(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/output", "")
        message_box = mock.Mock()
        self.window.canvas.export_xyz_async = mock.Mock(
            side_effect=lambda path, *, on_success, on_error: on_success(path)
        )

        self.service.export_xyz(self.window, file_dialog=file_dialog, message_box=message_box)

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "")
        self.assertEqual(self.window.canvas.export_xyz_async.call_args.args, ("/tmp/output.xyz",))
        self.assertEqual(self.window.statusBar().currentMessage(), "Exported XYZ: /tmp/output.xyz")
        message_box.warning.assert_not_called()

        file_dialog.getSaveFileName.reset_mock(return_value=True)
        file_dialog.getSaveFileName.return_value = ("/tmp/output", "")
        self.window.canvas.export_xyz_async = mock.Mock(
            side_effect=lambda path, *, on_success, on_error: on_error("no exporter")
        )

        self.service.export_xyz(self.window, file_dialog=file_dialog, message_box=message_box)

        message_box.warning.assert_called_once_with(self.window, "Export Error", "Failed to export XYZ:\nno exporter")

    def test_export_figure_uses_options_without_style_preset_side_effect(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/figure", "")
        message_box = mock.Mock()
        self.window._current_file_path = "/tmp/current.chemvas"
        self.window.canvas.export_figure = mock.Mock()
        options = {
            "fmt": "png",
            "sizing": "col1",
            "scope": "selection",
            "dpi": 600,
            "background": "white",
        }

        with mock.patch.object(self.service, "_prompt_export_options", return_value=options):
            self.service.export_figure(self.window, file_dialog=file_dialog, message_box=message_box)

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "/tmp/current.png")
        self.window.canvas.export_figure.assert_called_once_with(
            "/tmp/figure.png",
            fmt="png",
            scope="selection",
            dpi=600,
            background="white",
            sizing="col1",
        )
        self.assertEqual(self.window.statusBar().currentMessage(), "Exported: /tmp/figure.png")
        message_box.warning.assert_not_called()

    def test_export_figure_cancelled_options_skips_file_dialog(self) -> None:
        file_dialog = mock.Mock()
        message_box = mock.Mock()
        self.window.canvas.export_figure = mock.Mock()

        with mock.patch.object(self.service, "_prompt_export_options", return_value=None):
            self.service.export_figure(self.window, file_dialog=file_dialog, message_box=message_box)

        file_dialog.getSaveFileName.assert_not_called()
        self.window.canvas.export_figure.assert_not_called()
        message_box.warning.assert_not_called()

    def test_export_figure_cancelled_path_skips_export(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("", "")
        message_box = mock.Mock()
        self.window._current_file_path = "/tmp/current.chemvas"
        self.window.canvas.export_figure = mock.Mock()
        options = {
            "fmt": "pdf",
            "sizing": "bond",
            "scope": "sheet",
            "dpi": 300,
            "background": "transparent",
        }

        with mock.patch.object(self.service, "_prompt_export_options", return_value=options):
            self.service.export_figure(self.window, file_dialog=file_dialog, message_box=message_box)

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "/tmp/current.pdf")
        self.window.canvas.export_figure.assert_not_called()
        message_box.warning.assert_not_called()

    def test_export_figure_failure_warns_and_keeps_previous_status(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/figure", "")
        message_box = mock.Mock()
        self.window.statusBar().showMessage("Before export")
        self.window.canvas.export_figure = mock.Mock(side_effect=RuntimeError("render failed"))
        options = {
            "fmt": "svg",
            "sizing": "screen",
            "scope": "sheet",
            "dpi": 300,
            "background": "transparent",
        }

        with mock.patch.object(self.service, "_prompt_export_options", return_value=options):
            self.service.export_figure(self.window, file_dialog=file_dialog, message_box=message_box)

        self.window.canvas.export_figure.assert_called_once_with(
            "/tmp/figure.svg",
            fmt="svg",
            scope="sheet",
            dpi=300,
            background="transparent",
            sizing="screen",
        )
        message_box.warning.assert_called_once_with(
            self.window,
            "Export Error",
            "Failed to export figure:\nrender failed",
        )
        self.assertEqual(self.window.statusBar().currentMessage(), "Before export")

    def test_prompt_export_options_returns_selected_values_and_syncs_dpi(self) -> None:
        def drive_dialog(dialog: QDialog):
            self.assertEqual(dialog.windowTitle(), "Export Figure")

            format_combo = dialog.findChild(QComboBox, "exportFormatCombo")
            size_combo = dialog.findChild(QComboBox, "exportSizeCombo")
            scope_combo = dialog.findChild(QComboBox, "exportScopeCombo")
            background_combo = dialog.findChild(QComboBox, "exportBackgroundCombo")
            dpi_combo = dialog.findChild(QComboBox, "exportDpiCombo")
            export_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")
            cancel_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Cancel")

            self.assertIsNotNone(format_combo)
            self.assertIsNotNone(size_combo)
            self.assertIsNotNone(scope_combo)
            self.assertIsNotNone(background_combo)
            self.assertIsNotNone(dpi_combo)
            self.assertFalse(dpi_combo.isEnabled())

            format_combo.setCurrentIndex(format_combo.findData("png"))
            self.assertTrue(dpi_combo.isEnabled())
            size_combo.setCurrentIndex(size_combo.findData("col2"))
            scope_combo.setCurrentIndex(scope_combo.findData("selection"))
            background_combo.setCurrentIndex(background_combo.findData("white"))
            dpi_combo.setCurrentIndex(dpi_combo.findData(600))

            self.assertEqual(export_button.text(), "Export")
            self.assertEqual(cancel_button.text(), "Cancel")
            export_button.click()
            return QDialog.DialogCode.Accepted

        with mock.patch("ui.main_window_document_action_service.QDialog.exec", new=drive_dialog):
            options = self.service._prompt_export_options(self.window)

        self.assertEqual(
            options,
            {
                "fmt": "png",
                "sizing": "col2",
                "scope": "selection",
                "dpi": 600,
                "background": "white",
            },
        )

    def test_prompt_export_options_cancel_returns_none(self) -> None:
        def drive_dialog(dialog: QDialog):
            self.assertEqual(dialog.windowTitle(), "Export Figure")
            self.assertIsNotNone(dialog.findChild(QComboBox, "exportFormatCombo"))
            return QDialog.DialogCode.Rejected

        with mock.patch("ui.main_window_document_action_service.QDialog.exec", new=drive_dialog):
            self.assertIsNone(self.service._prompt_export_options(self.window))

    def test_load_canvas_dispatches_single_sheet_and_workbook_states(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getOpenFileName.return_value = ("/tmp/input.chemvas", "")
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
        self.assertEqual(self.window._current_file_path, "/tmp/input.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Loaded: /tmp/input.chemvas")

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
        file_dialog.getOpenFileName.return_value = ("/tmp/broken.chemvas", "")
        message_box = mock.Mock()
        self.window._current_file_path = "/tmp/previous.chemvas"

        self.service.load_canvas(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            read_document=mock.Mock(side_effect=RuntimeError("bad file")),
            resolve_load_path=resolve_load_path,
        )

        message_box.warning.assert_called_once_with(self.window, "Load Error", "Failed to load file:\nbad file")
        self.assertEqual(self.window._current_file_path, "/tmp/previous.chemvas")

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

    def test_setup_sheet_uses_current_canvas_settings_and_applies_confirmed_value(self) -> None:
        self.window.canvas.set_sheet_setup("A4", "landscape")

        def drive_dialog(dialog: QDialog):
            self.assertEqual(dialog.windowTitle(), "Setup Sheet")

            size_combo = dialog.findChild(QComboBox, "sheetSizeCombo")
            orientation_combo = dialog.findChild(QComboBox, "sheetOrientationCombo")
            ok_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "OK")

            self.assertIsNotNone(size_combo)
            self.assertIsNotNone(orientation_combo)
            self.assertEqual([size_combo.itemText(index) for index in range(size_combo.count())], ["A4"])
            self.assertEqual(size_combo.currentText(), "A4")
            self.assertEqual(orientation_combo.currentData(), "landscape")

            portrait_index = orientation_combo.findData("portrait")
            self.assertGreaterEqual(portrait_index, 0)
            orientation_combo.setCurrentIndex(portrait_index)
            ok_button.click()

            return QDialog.DialogCode.Accepted

        with (
            mock.patch.object(self.window.canvas, "set_sheet_setup") as set_sheet_setup,
            mock.patch("ui.main_window_document_action_service.QDialog.exec", new=drive_dialog),
        ):
            self.service.setup_sheet(self.window)

        set_sheet_setup.assert_called_once_with("A4", "portrait")


if __name__ == "__main__":
    unittest.main()
