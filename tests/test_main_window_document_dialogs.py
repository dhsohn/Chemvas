import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QPushButton,
)

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_document_dialogs import (
    FigureExportOptions,
    SheetSetupSelection,
    prompt_export_options,
    prompt_sheet_setup,
)
from chemvas.ui.main_window_menu_bar import run_sheet_setup_dialog
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    history_service_for_window,
    services_for_window,
)
from chemvas.ui.sheet_setup_access import set_sheet_setup_for, sheet_setup_for


class MainWindowDocumentDialogsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()

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
            editable_check = dialog.findChild(QCheckBox, "exportEditableSvgCheck")
            export_button = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == "Export"
            )
            cancel_button = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == "Cancel"
            )

            self.assertIsNotNone(format_combo)
            self.assertIsNotNone(size_combo)
            self.assertIsNotNone(scope_combo)
            self.assertIsNotNone(background_combo)
            self.assertIsNotNone(dpi_combo)
            self.assertIsNotNone(editable_check)
            self.assertFalse(dpi_combo.isEnabled())
            self.assertTrue(editable_check.isEnabled())
            self.assertFalse(editable_check.isChecked())

            format_combo.setCurrentIndex(format_combo.findData("png"))
            self.assertTrue(dpi_combo.isEnabled())
            self.assertFalse(editable_check.isEnabled())
            size_combo.setCurrentIndex(size_combo.findData("col2"))
            scope_combo.setCurrentIndex(scope_combo.findData("selection"))
            background_combo.setCurrentIndex(background_combo.findData("white"))
            dpi_combo.setCurrentIndex(dpi_combo.findData(600))

            self.assertEqual(export_button.text(), "Export")
            self.assertEqual(cancel_button.text(), "Cancel")
            export_button.click()
            return QDialog.DialogCode.Accepted

        with mock.patch(
            "chemvas.ui.main_window_document_dialogs.QDialog.exec", new=drive_dialog
        ):
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

        with mock.patch(
            "chemvas.ui.main_window_document_dialogs.QDialog.exec", new=drive_dialog
        ):
            self.assertIsNone(prompt_export_options(self.window))

    def test_prompt_sheet_setup_uses_current_settings_and_returns_confirmed_value(
        self,
    ) -> None:
        set_sheet_setup_for(active_canvas_for_window(self.window), "A4", "landscape")

        def drive_dialog(dialog: QDialog):
            self.assertEqual(dialog.windowTitle(), "Canvas Size")

            size_combo = dialog.findChild(QComboBox, "sheetSizeCombo")
            orientation_combo = dialog.findChild(QComboBox, "sheetOrientationCombo")
            ok_button = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == "OK"
            )

            self.assertIsNotNone(size_combo)
            self.assertIsNotNone(orientation_combo)
            self.assertEqual(
                [size_combo.itemText(index) for index in range(size_combo.count())],
                ["A4"],
            )
            self.assertEqual(size_combo.currentText(), "A4")
            self.assertEqual(orientation_combo.currentData(), "landscape")

            portrait_index = orientation_combo.findData("portrait")
            self.assertGreaterEqual(portrait_index, 0)
            orientation_combo.setCurrentIndex(portrait_index)
            ok_button.click()

            return QDialog.DialogCode.Accepted

        with mock.patch(
            "chemvas.ui.main_window_document_dialogs.QDialog.exec", new=drive_dialog
        ):
            selection = prompt_sheet_setup(
                self.window,
                current_size="A4",
                current_orientation="landscape",
            )

        self.assertEqual(
            selection, SheetSetupSelection(size="A4", orientation="portrait")
        )

    def test_prompt_sheet_setup_cancel_returns_none(self) -> None:
        with mock.patch(
            "chemvas.ui.main_window_document_dialogs.QDialog.exec",
            return_value=QDialog.DialogCode.Rejected,
        ):
            self.assertIsNone(
                prompt_sheet_setup(
                    self.window,
                    current_size="A4",
                    current_orientation="landscape",
                )
            )

    def _choose_sheet_orientation(
        self, orientation: str, *, accepted: bool = True
    ) -> None:
        def drive_dialog(dialog: QDialog):
            combo = dialog.findChild(QComboBox, "sheetOrientationCombo")
            self.assertIsNotNone(combo)
            index = combo.findData(orientation)
            self.assertGreaterEqual(index, 0)
            combo.setCurrentIndex(index)
            if accepted:
                dialog.accept()
                return QDialog.DialogCode.Accepted
            dialog.reject()
            return QDialog.DialogCode.Rejected

        with mock.patch(
            "chemvas.ui.main_window_document_dialogs.QDialog.exec", new=drive_dialog
        ):
            run_sheet_setup_dialog(self.window)

    def test_confirmed_sheet_change_updates_document_chrome_without_history(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        services = services_for_window(self.window)
        history = history_service_for_window(self.window).state
        before_history = (tuple(history.history), tuple(history.redo_stack))
        self.window.statusBar().showMessage("Keep this feedback")

        self._choose_sheet_orientation("portrait")

        self.assertEqual(sheet_setup_for(canvas), ("A4", "portrait"))
        self.assertTrue(services.canvas_document_service.is_dirty(canvas))
        self.assertTrue(self.window.isWindowModified())
        self.assertEqual(
            self.window.tab_references.canvas_tabs.tabText(0), "● Canvas 1"
        )
        self.assertEqual(
            services.status_service.status_context_texts()["sheet"],
            "Canvas: ● Canvas 1",
        )
        self.assertEqual(self.window.statusBar().currentMessage(), "Keep this feedback")
        self.assertEqual(
            (tuple(history.history), tuple(history.redo_stack)), before_history
        )

    def test_sheet_change_chrome_tracks_saved_orientation_checkpoint(self) -> None:
        services = services_for_window(self.window)
        canvas = active_canvas_for_window(self.window)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "portrait.chemvas")
            self._choose_sheet_orientation("portrait")
            self.assertTrue(
                services.document_action_service.save_canvas_to_path(self.window, path)
            )
            self.assertFalse(self.window.isWindowModified())

            self._choose_sheet_orientation("landscape")
            self.assertTrue(self.window.isWindowModified())
            self.assertTrue(services.canvas_document_service.is_dirty(canvas))

            self._choose_sheet_orientation("portrait")
            self.assertFalse(self.window.isWindowModified())
            self.assertFalse(services.canvas_document_service.is_dirty(canvas))
            self.assertEqual(
                services.status_service.status_context_texts()["sheet"],
                "Canvas: portrait.chemvas",
            )

    def test_same_sheet_settings_and_cancel_preserve_document_and_chrome(self) -> None:
        canvas = active_canvas_for_window(self.window)
        status = services_for_window(self.window).status_service
        before_document = snapshot_canvas_state_for(canvas)
        before_status = status.status_context_texts()
        before_title = self.window.windowTitle()
        for orientation, accepted in (("landscape", True), ("portrait", False)):
            with self.subTest(orientation=orientation, accepted=accepted):
                self._choose_sheet_orientation(orientation, accepted=accepted)
                self.assertEqual(snapshot_canvas_state_for(canvas), before_document)
                self.assertEqual(status.status_context_texts(), before_status)
                self.assertEqual(self.window.windowTitle(), before_title)
                self.assertFalse(self.window.isWindowModified())
