import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QComboBox,
        QDialog,
        QPushButton,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.main_window_document_dialogs import (
        FigureExportOptions,
        SheetSetupSelection,
        prompt_export_options,
        prompt_sheet_setup,
    )
    from ui.main_window_service_ports import services_for_window
    from ui.sheet_setup_access import set_sheet_setup_for


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window document dialog tests")
class MainWindowDocumentDialogsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()

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

        with mock.patch("ui.main_window_document_dialogs.QDialog.exec", new=drive_dialog):
            options = prompt_export_options(self.window)

        self.assertEqual(
            options,
            FigureExportOptions(
                fmt="png",
                sizing="col2",
                scope="selection",
                dpi=600,
                background="white",
            ),
        )

    def test_prompt_export_options_cancel_returns_none(self) -> None:
        def drive_dialog(dialog: QDialog):
            self.assertEqual(dialog.windowTitle(), "Export Figure")
            self.assertIsNotNone(dialog.findChild(QComboBox, "exportFormatCombo"))
            return QDialog.DialogCode.Rejected

        with mock.patch("ui.main_window_document_dialogs.QDialog.exec", new=drive_dialog):
            self.assertIsNone(prompt_export_options(self.window))

    def test_prompt_sheet_setup_uses_current_settings_and_returns_confirmed_value(self) -> None:
        set_sheet_setup_for(active_canvas_for_window(self.window), "A4", "landscape")

        def drive_dialog(dialog: QDialog):
            self.assertEqual(dialog.windowTitle(), "Canvas Size")

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

        with mock.patch("ui.main_window_document_dialogs.QDialog.exec", new=drive_dialog):
            selection = prompt_sheet_setup(
                self.window,
                current_size="A4",
                current_orientation="landscape",
            )

        self.assertEqual(selection, SheetSetupSelection(size="A4", orientation="portrait"))

    def test_prompt_sheet_setup_cancel_returns_none(self) -> None:
        with mock.patch("ui.main_window_document_dialogs.QDialog.exec", return_value=QDialog.DialogCode.Rejected):
            self.assertIsNone(
                prompt_sheet_setup(
                    self.window,
                    current_size="A4",
                    current_orientation="landscape",
                )
            )


if __name__ == "__main__":
    unittest.main()
