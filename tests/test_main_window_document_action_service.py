import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.main_window_document_action_service import MainWindowDocumentActionService
    from ui.main_window_document_dialogs import FigureExportOptions
    from ui.main_window_path_logic import (
        resolve_load_path,
        resolve_save_as_path,
        resolve_save_path,
    )
    from ui.main_window_service_ports import services_for_window


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window document action tests")
class MainWindowDocumentActionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.document_session_service_for_window = mock.Mock(
            side_effect=lambda window: active_canvas_for_window(window).services.canvas_document_session_service,
        )
        self.geometry_controller_for_window = mock.Mock(
            side_effect=lambda window: active_canvas_for_window(window).services.geometry_controller,
        )
        self.bond_length_px_for_window = mock.Mock(return_value=24.0)
        self.current_file_path_for_window = mock.Mock(
            side_effect=lambda window: window.runtime_state.current_file_path,
        )
        self.set_current_file_path_for_window = mock.Mock(
            side_effect=lambda window, path: setattr(window.runtime_state, "current_file_path", path),
        )
        self.workbook_document_service = services_for_window(self.window).workbook_document_service
        self.service = MainWindowDocumentActionService(
            document_session_service_for_window=self.document_session_service_for_window,
            geometry_controller_for_window=self.geometry_controller_for_window,
            bond_length_px_for_window=self.bond_length_px_for_window,
            current_file_path_for_window=self.current_file_path_for_window,
            set_current_file_path_for_window=self.set_current_file_path_for_window,
            workbook_document_service=self.workbook_document_service,
        )

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_save_canvas_to_path_success_updates_state_and_status(self) -> None:
        message_box = mock.Mock()
        self.window.runtime_state.current_file_path = "/tmp/old.chemvas"
        self.workbook_document_service.save_document_state = mock.Mock()

        result = self.service.save_canvas_to_path(self.window, "/tmp/new.chemvas", message_box=message_box)

        self.assertTrue(result)
        self.workbook_document_service.save_document_state.assert_called_once_with(self.window, "/tmp/new.chemvas")
        self.assertEqual(self.window.runtime_state.current_file_path, "/tmp/new.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Saved: /tmp/new.chemvas")
        message_box.warning.assert_not_called()

    def test_save_canvas_to_path_failure_warns_and_keeps_previous_path(self) -> None:
        message_box = mock.Mock()
        self.window.runtime_state.current_file_path = "/tmp/old.chemvas"
        self.workbook_document_service.save_document_state = mock.Mock(side_effect=RuntimeError("boom"))

        result = self.service.save_canvas_to_path(self.window, "/tmp/new.chemvas", message_box=message_box)

        self.assertFalse(result)
        self.assertEqual(self.window.runtime_state.current_file_path, "/tmp/old.chemvas")
        message_box.warning.assert_called_once_with(self.window, "Save Error", "Failed to save file:\nboom")

    def test_save_canvas_prefers_current_path_and_falls_back_to_save_as(self) -> None:
        self.window.runtime_state.current_file_path = "/tmp/existing.chemvas"
        with (
            mock.patch.object(self.service, "save_canvas_to_path") as save_canvas_to_path,
            mock.patch.object(self.service, "save_canvas_as") as save_canvas_as,
        ):
            self.service.save_canvas(self.window, resolve_save_path=resolve_save_path)

        save_canvas_to_path.assert_called_once_with(self.window, "/tmp/existing.chemvas")
        save_canvas_as.assert_not_called()

        self.window.runtime_state.current_file_path = None
        with (
            mock.patch.object(self.service, "save_canvas_to_path") as save_canvas_to_path,
            mock.patch.object(self.service, "save_canvas_as") as save_canvas_as,
        ):
            self.service.save_canvas(self.window, resolve_save_path=resolve_save_path)

        save_canvas_as.assert_called_once_with(self.window)
        save_canvas_to_path.assert_not_called()

    def test_save_canvas_as_uses_default_dialog_path_and_normalizes_extension(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/new-drawing", "")
        self.window.runtime_state.current_file_path = "/tmp/current.chemvas"

        with mock.patch.object(self.service, "save_canvas_to_path") as save_canvas_to_path:
            self.service.save_canvas_as(
                self.window,
                file_dialog=file_dialog,
                resolve_save_as_path=resolve_save_as_path,
            )

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "/tmp/current.chemvas")
        save_canvas_to_path.assert_called_once_with(self.window, "/tmp/new-drawing.chemvas")

    def test_export_xyz_normalizes_path_and_reports_success_and_failure(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/output", "")
        message_box = mock.Mock()
        doc_service = active_canvas_for_window(self.window).services.canvas_document_session_service
        doc_service.export_xyz_async = mock.Mock(
            side_effect=lambda path, *, on_success, on_error: on_success(path)
        )
        active_canvas_for_window(self.window).export_xyz_async = mock.Mock(
            side_effect=AssertionError("canvas export_xyz_async wrapper should not run")
        )

        self.service.export_xyz(self.window, file_dialog=file_dialog, message_box=message_box)

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "")
        self.assertEqual(doc_service.export_xyz_async.call_args.args, ("/tmp/output.xyz",))
        self.document_session_service_for_window.assert_called_once_with(self.window)
        active_canvas_for_window(self.window).export_xyz_async.assert_not_called()
        self.assertEqual(self.window.statusBar().currentMessage(), "Exported XYZ: /tmp/output.xyz")
        message_box.warning.assert_not_called()

        file_dialog.getSaveFileName.reset_mock(return_value=True)
        file_dialog.getSaveFileName.return_value = ("/tmp/output", "")
        doc_service.export_xyz_async = mock.Mock(
            side_effect=lambda path, *, on_success, on_error: on_error("no exporter")
        )

        self.service.export_xyz(self.window, file_dialog=file_dialog, message_box=message_box)

        message_box.warning.assert_called_once_with(self.window, "Export Error", "Failed to export XYZ:\nno exporter")
        self.assertEqual(self.document_session_service_for_window.call_count, 2)

    def test_export_xyz_can_request_selected_structure_only(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/selected", "")
        message_box = mock.Mock()
        doc_service = active_canvas_for_window(self.window).services.canvas_document_session_service
        doc_service.export_xyz_async = mock.Mock(
            side_effect=lambda path, *, on_success, on_error, selected_only=False: on_success(path)
        )

        self.service.export_xyz(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            selected_only=True,
        )

        self.assertEqual(doc_service.export_xyz_async.call_args.args, ("/tmp/selected.xyz",))
        self.assertEqual(doc_service.export_xyz_async.call_args.kwargs["selected_only"], True)
        message_box.warning.assert_not_called()

    def test_export_figure_uses_options_without_style_preset_side_effect(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/figure", "")
        message_box = mock.Mock()
        self.window.runtime_state.current_file_path = "/tmp/current.chemvas"
        doc_service = active_canvas_for_window(self.window).services.canvas_document_session_service
        doc_service.export_figure = mock.Mock()
        active_canvas_for_window(self.window).export_figure = mock.Mock(side_effect=AssertionError("canvas export wrapper should not run"))
        options = FigureExportOptions(
            fmt="png",
            sizing="col1",
            scope="selection",
            dpi=600,
            background="white",
        )

        with mock.patch("ui.main_window_document_action_service.prompt_export_options", return_value=options):
            self.service.export_figure(self.window, file_dialog=file_dialog, message_box=message_box)

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "/tmp/current.png")
        doc_service.export_figure.assert_called_once_with(
            "/tmp/figure.png",
            fmt="png",
            scope="selection",
            dpi=600,
            background="white",
            sizing="col1",
        )
        self.document_session_service_for_window.assert_called_once_with(self.window)
        active_canvas_for_window(self.window).export_figure.assert_not_called()
        self.assertEqual(self.window.statusBar().currentMessage(), "Exported: /tmp/figure.png")
        message_box.warning.assert_not_called()

    def test_export_figure_cancelled_options_skips_file_dialog(self) -> None:
        file_dialog = mock.Mock()
        message_box = mock.Mock()
        doc_service = active_canvas_for_window(self.window).services.canvas_document_session_service
        doc_service.export_figure = mock.Mock()

        with mock.patch("ui.main_window_document_action_service.prompt_export_options", return_value=None):
            self.service.export_figure(self.window, file_dialog=file_dialog, message_box=message_box)

        file_dialog.getSaveFileName.assert_not_called()
        doc_service.export_figure.assert_not_called()
        self.document_session_service_for_window.assert_not_called()
        message_box.warning.assert_not_called()

    def test_export_figure_cancelled_path_skips_export(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("", "")
        message_box = mock.Mock()
        self.window.runtime_state.current_file_path = "/tmp/current.chemvas"
        doc_service = active_canvas_for_window(self.window).services.canvas_document_session_service
        doc_service.export_figure = mock.Mock()
        options = FigureExportOptions(
            fmt="pdf",
            sizing="bond",
            scope="sheet",
            dpi=300,
            background="transparent",
        )

        with mock.patch("ui.main_window_document_action_service.prompt_export_options", return_value=options):
            self.service.export_figure(self.window, file_dialog=file_dialog, message_box=message_box)

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(file_dialog.getSaveFileName.call_args.args[2], "/tmp/current.pdf")
        doc_service.export_figure.assert_not_called()
        self.document_session_service_for_window.assert_not_called()
        message_box.warning.assert_not_called()

    def test_export_figure_failure_warns_and_keeps_previous_status(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/figure", "")
        message_box = mock.Mock()
        self.window.statusBar().showMessage("Before export")
        doc_service = active_canvas_for_window(self.window).services.canvas_document_session_service
        doc_service.export_figure = mock.Mock(side_effect=RuntimeError("render failed"))
        active_canvas_for_window(self.window).export_figure = mock.Mock(side_effect=AssertionError("canvas export wrapper should not run"))
        options = FigureExportOptions(
            fmt="svg",
            sizing="screen",
            scope="sheet",
            dpi=300,
            background="transparent",
        )

        with mock.patch("ui.main_window_document_action_service.prompt_export_options", return_value=options):
            self.service.export_figure(self.window, file_dialog=file_dialog, message_box=message_box)

        doc_service.export_figure.assert_called_once_with(
            "/tmp/figure.svg",
            fmt="svg",
            scope="sheet",
            dpi=300,
            background="transparent",
            sizing="screen",
        )
        self.document_session_service_for_window.assert_called_once_with(self.window)
        active_canvas_for_window(self.window).export_figure.assert_not_called()
        message_box.warning.assert_called_once_with(
            self.window,
            "Export Error",
            "Failed to export figure:\nrender failed",
        )
        self.assertEqual(self.window.statusBar().currentMessage(), "Before export")

    def test_load_canvas_dispatches_single_sheet_and_workbook_states(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getOpenFileName.return_value = ("/tmp/input.chemvas", "")
        message_box = mock.Mock()
        self.workbook_document_service.restore_single_sheet_document = mock.Mock()
        self.workbook_document_service.restore_workbook_document = mock.Mock()

        self.service.load_canvas(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            read_document=mock.Mock(return_value=SimpleNamespace(state={"atoms": []})),
            resolve_load_path=resolve_load_path,
        )

        self.workbook_document_service.restore_single_sheet_document.assert_called_once_with(
            self.window,
            {"atoms": []},
        )
        self.workbook_document_service.restore_workbook_document.assert_not_called()
        self.assertEqual(self.window.runtime_state.current_file_path, "/tmp/input.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Loaded: /tmp/input.chemvas")

        self.workbook_document_service.restore_single_sheet_document.reset_mock()
        self.workbook_document_service.restore_workbook_document.reset_mock()

        self.service.load_canvas(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            read_document=mock.Mock(return_value=SimpleNamespace(state={"sheets": [{"name": "Sheet 1"}]})),
            resolve_load_path=resolve_load_path,
        )

        self.workbook_document_service.restore_workbook_document.assert_called_once_with(
            self.window,
            {"sheets": [{"name": "Sheet 1"}]},
        )
        self.workbook_document_service.restore_single_sheet_document.assert_not_called()

    def test_load_canvas_restores_editable_svg_without_updating_current_path(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getOpenFileName.return_value = ("/tmp/editable.svg", "")
        message_box = mock.Mock()
        self.window.runtime_state.current_file_path = "/tmp/current.chemvas"
        self.workbook_document_service.restore_single_sheet_document = mock.Mock()
        self.workbook_document_service.restore_workbook_document = mock.Mock()
        read_document = mock.Mock(side_effect=AssertionError("JSON reader should not read SVG"))
        read_editable_svg = mock.Mock(return_value=SimpleNamespace(state={"model": {"atoms": {}}}))

        self.service.load_canvas(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            read_document=read_document,
            read_editable_svg=read_editable_svg,
            resolve_load_path=resolve_load_path,
        )

        read_editable_svg.assert_called_once_with("/tmp/editable.svg")
        read_document.assert_not_called()
        self.workbook_document_service.restore_single_sheet_document.assert_called_once_with(
            self.window,
            {"model": {"atoms": {}}},
        )
        self.workbook_document_service.restore_workbook_document.assert_not_called()
        self.assertEqual(self.window.runtime_state.current_file_path, "/tmp/current.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Loaded editable SVG: /tmp/editable.svg")
        message_box.warning.assert_not_called()

    def test_load_canvas_warns_when_editable_svg_metadata_is_missing(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getOpenFileName.return_value = ("/tmp/plain.svg", "")
        message_box = mock.Mock()
        self.window.runtime_state.current_file_path = "/tmp/current.chemvas"

        self.service.load_canvas(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            read_editable_svg=mock.Mock(side_effect=ValueError("No editable Chemvas metadata found in SVG.")),
            resolve_load_path=resolve_load_path,
        )

        message_box.warning.assert_called_once_with(
            self.window,
            "Load Error",
            "Failed to load file:\nNo editable Chemvas metadata found in SVG.",
        )
        self.assertEqual(self.window.runtime_state.current_file_path, "/tmp/current.chemvas")

    def test_load_canvas_warns_on_read_failure(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getOpenFileName.return_value = ("/tmp/broken.chemvas", "")
        message_box = mock.Mock()
        self.window.runtime_state.current_file_path = "/tmp/previous.chemvas"

        self.service.load_canvas(
            self.window,
            file_dialog=file_dialog,
            message_box=message_box,
            read_document=mock.Mock(side_effect=RuntimeError("bad file")),
            resolve_load_path=resolve_load_path,
        )

        message_box.warning.assert_called_once_with(self.window, "Load Error", "Failed to load file:\nbad file")
        self.assertEqual(self.window.runtime_state.current_file_path, "/tmp/previous.chemvas")

    def test_set_bond_length_prompts_with_current_value_and_applies_confirmed_value(self) -> None:
        with (
            mock.patch.object(
                active_canvas_for_window(self.window).services.geometry_controller,
                "set_bond_length",
            ) as controller_set_bond_length,
            mock.patch("ui.main_window_document_action_service.prompt_bond_length", return_value=25.0) as prompt,
        ):
            self.assertFalse(hasattr(active_canvas_for_window(self.window), "set_bond_length"))
            self.service.set_bond_length(self.window)

        prompt.assert_called_once_with(self.window, 24.0)
        self.bond_length_px_for_window.assert_called_once_with(self.window)
        controller_set_bond_length.assert_called_once_with(25.0)
        self.geometry_controller_for_window.assert_called_once_with(self.window)

    def test_set_bond_length_cancel_skips_geometry_controller(self) -> None:
        with (
            mock.patch.object(
                active_canvas_for_window(self.window).services.geometry_controller,
                "set_bond_length",
            ) as controller_set_bond_length,
            mock.patch("ui.main_window_document_action_service.prompt_bond_length", return_value=None),
        ):
            self.service.set_bond_length(self.window)

        self.bond_length_px_for_window.assert_called_once_with(self.window)
        controller_set_bond_length.assert_not_called()
        self.geometry_controller_for_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
