import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QMessageBox
except ModuleNotFoundError:
    QApplication = None
    QPointF = None
    QMessageBox = None
    QTest = None

if QApplication is not None:
    from core.document_io import write_document
    from ui.canvas_document_metadata_state import document_file_path_for
    from ui.canvas_window_access import snapshot_canvas_state_for
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.main_window_path_logic import (
        resolve_save_as_path,
        resolve_save_path,
    )
    from ui.main_window_service_ports import services_for_window
    from ui.structure_mutation_access import add_bond_between_points_for


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window document action tests")
class MainWindowDocumentActionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        QTest.qWait(20)
        self.service = services_for_window(self.window).document_action_service

    def tearDown(self) -> None:
        for canvas in self.window.tab_references.all_canvases():
            services_for_window(self.window).canvas_document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_save_canvas_to_path_updates_only_active_canvas_path_title_and_clean_state(self) -> None:
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(-20.0, 0.0), QPointF(20.0, 0.0))

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "new.chemvas"
            result = self.service.save_canvas_to_path(self.window, str(path))

            self.assertTrue(result)
            self.assertTrue(path.exists())
            canvas = active_canvas_for_window(self.window)
            self.assertEqual(document_file_path_for(canvas), str(path))
            self.assertEqual(self.window.tab_references.canvas_tabs.tabText(0), "new.chemvas")
            self.assertFalse(services_for_window(self.window).canvas_document_service.is_dirty(canvas))

    def test_save_canvas_prefers_current_path_and_falls_back_to_save_as(self) -> None:
        canvas = active_canvas_for_window(self.window)
        services_for_window(self.window).canvas_document_service.set_file_path(canvas, "/tmp/existing.chemvas")

        with (
            mock.patch.object(self.service, "save_canvas_to_path", return_value=True) as save_canvas_to_path,
            mock.patch.object(self.service, "save_canvas_as", return_value=True) as save_canvas_as,
        ):
            self.assertTrue(self.service.save_canvas(self.window, resolve_save_path=resolve_save_path))

        save_canvas_to_path.assert_called_once_with(self.window, "/tmp/existing.chemvas", canvas=None)
        save_canvas_as.assert_not_called()

        services_for_window(self.window).canvas_document_service.set_file_path(canvas, None)
        with (
            mock.patch.object(self.service, "save_canvas_to_path", return_value=True) as save_canvas_to_path,
            mock.patch.object(self.service, "save_canvas_as", return_value=False) as save_canvas_as,
        ):
            self.assertFalse(self.service.save_canvas(self.window, resolve_save_path=resolve_save_path))

        save_canvas_as.assert_called_once_with(self.window, canvas=None)
        save_canvas_to_path.assert_not_called()

    def test_save_canvas_as_uses_default_dialog_path_and_normalizes_extension(self) -> None:
        canvas = active_canvas_for_window(self.window)
        services_for_window(self.window).canvas_document_service.set_file_path(canvas, "/tmp/current.chemvas")
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/new-drawing", "")

        with mock.patch.object(self.service, "save_canvas_to_path", return_value=True) as save_canvas_to_path:
            self.assertTrue(
                self.service.save_canvas_as(
                    self.window,
                    file_dialog=file_dialog,
                    resolve_save_as_path=resolve_save_as_path,
                )
            )

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "/tmp/current.chemvas")
        save_canvas_to_path.assert_called_once_with(self.window, "/tmp/new-drawing.chemvas", canvas=None)

    def test_load_canvas_from_path_reuses_clean_untitled_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "input.chemvas"
            state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
            write_document(path, state, version=1)

            result = self.service.load_canvas_from_path(self.window, str(path))

        self.assertTrue(result)
        self.assertEqual(self.window.tab_references.canvas_count(), 1)
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(0), "input.chemvas")
        self.assertEqual(document_file_path_for(active_canvas_for_window(self.window)), str(path))

    def test_load_canvas_rejects_workbook_payload_without_importing(self) -> None:
        state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
        read_document = mock.Mock(
            return_value=SimpleNamespace(
                state={"active_sheet_index": 0, "sheets": [{"name": "Canvas 1", "kind": "canvas", "content": state}]}
            )
        )
        message_box = mock.Mock()

        result = self.service.load_canvas_from_path(
            self.window,
            "/tmp/workbook.chemvas",
            message_box=message_box,
            read_document=read_document,
        )

        self.assertFalse(result)
        self.assertEqual(self.window.tab_references.canvas_count(), 1)
        message_box.warning.assert_called_once()

    def test_confirm_close_canvas_handles_save_discard_and_cancel(self) -> None:
        canvas = active_canvas_for_window(self.window)
        add_bond_between_points_for(canvas, QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        message_box = mock.Mock()
        message_box.question.return_value = QMessageBox.StandardButton.Cancel

        self.assertFalse(self.service.confirm_close_canvas(self.window, canvas, message_box=message_box))

        message_box.question.return_value = QMessageBox.StandardButton.Discard
        self.assertTrue(self.service.confirm_close_canvas(self.window, canvas, message_box=message_box))

        message_box.question.return_value = QMessageBox.StandardButton.Save
        with mock.patch.object(self.service, "save_canvas", return_value=True) as save_canvas:
            self.assertTrue(self.service.confirm_close_canvas(self.window, canvas, message_box=message_box))
        save_canvas.assert_called_once_with(self.window, canvas=canvas)


if __name__ == "__main__":
    unittest.main()
