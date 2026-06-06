from __future__ import annotations

from pathlib import Path

from core.document_io import read_document as default_read_document
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from ui.export_dialog_logic import (
    default_export_path,
    file_filter_for_format,
    normalize_export_path,
)
from ui.main_window_document_dialogs import (
    prompt_bond_length,
    prompt_export_options,
    prompt_sheet_setup,
)
from ui.main_window_path_logic import (
    resolve_load_path as default_resolve_load_path,
)
from ui.main_window_path_logic import (
    resolve_save_as_path as default_resolve_save_as_path,
)
from ui.main_window_path_logic import (
    resolve_save_path as default_resolve_save_path,
)


class MainWindowDocumentActionService:
    def __init__(
        self,
        *,
        document_session_service_for_window,
        geometry_controller_for_window,
        bond_length_px_for_window,
        sheet_size_for_window,
        sheet_orientation_for_window,
        set_sheet_setup_for_window,
        current_file_path_for_window,
        set_current_file_path_for_window,
        workbook_document_service,
    ) -> None:
        self._document_session_service_for_window = document_session_service_for_window
        self._geometry_controller_for_window = geometry_controller_for_window
        self._bond_length_px_for_window = bond_length_px_for_window
        self._sheet_size_for_window = sheet_size_for_window
        self._sheet_orientation_for_window = sheet_orientation_for_window
        self._set_sheet_setup_for_window = set_sheet_setup_for_window
        self._current_file_path_for_window = current_file_path_for_window
        self._set_current_file_path_for_window = set_current_file_path_for_window
        self._workbook_document = workbook_document_service

    @staticmethod
    def normalize_xyz_export_path(dialog_path: str | None) -> str | None:
        if not dialog_path:
            return None
        path = Path(dialog_path)
        if path.suffix:
            return str(path)
        return str(path.with_suffix(".xyz"))

    def default_xyz_export_path(self, window) -> str:
        current_path = self._current_file_path_for_window(window)
        if current_path:
            return str(Path(current_path).with_suffix(".xyz"))
        return ""

    def default_save_dialog_path(self, window) -> str:
        return self._current_file_path_for_window(window) or ""

    def save_canvas_to_path(self, window, path: str, *, message_box=None) -> bool:
        message_box = QMessageBox if message_box is None else message_box
        try:
            self._workbook_document.save_document_state(window, path)
        except Exception as exc:
            message_box.warning(window, "Save Error", f"Failed to save file:\n{exc}")
            return False
        self._set_current_file_path_for_window(window, path)
        window.statusBar().showMessage(f"Saved: {path}", 4000)
        return True

    def save_canvas(self, window, *, resolve_save_path=None) -> None:
        resolve_save_path = default_resolve_save_path if resolve_save_path is None else resolve_save_path
        path = resolve_save_path(current_path=self._current_file_path_for_window(window))
        if path is None:
            self.save_canvas_as(window)
            return
        self.save_canvas_to_path(window, path)

    def save_canvas_as(self, window, *, file_dialog=None, resolve_save_as_path=None) -> None:
        file_dialog = QFileDialog if file_dialog is None else file_dialog
        resolve_save_as_path = (
            default_resolve_save_as_path if resolve_save_as_path is None else resolve_save_as_path
        )
        dialog_path, _ = file_dialog.getSaveFileName(
            window,
            "Save Drawing As",
            self.default_save_dialog_path(window),
            "Chemvas (*.chemvas);;JSON (*.json);;All Files (*)",
        )
        path = resolve_save_as_path(dialog_path)
        if path is None:
            return
        self.save_canvas_to_path(window, path)

    def export_xyz(self, window, *, file_dialog=None, message_box=None) -> None:
        file_dialog = QFileDialog if file_dialog is None else file_dialog
        message_box = QMessageBox if message_box is None else message_box
        dialog_path, _ = file_dialog.getSaveFileName(
            window,
            "Export 3D XYZ",
            self.default_xyz_export_path(window),
            "XYZ (*.xyz);;All Files (*)",
        )
        path = self.normalize_xyz_export_path(dialog_path)
        if path is None:
            return
        previous_status = window.statusBar().currentMessage()

        def handle_error(message: str) -> None:
            message_box.warning(
                window,
                "Export Error",
                f"Failed to export XYZ:\n{message}",
            )
            window.statusBar().showMessage(previous_status)

        window.statusBar().showMessage(f"Exporting XYZ: {path}")
        self._document_session_service_for_window(window).export_xyz_async(
            path,
            on_success=lambda export_path: window.statusBar().showMessage(f"Exported XYZ: {export_path}", 4000),
            on_error=handle_error,
        )

    def export_figure(self, window, *, file_dialog=None, message_box=None) -> None:
        file_dialog = QFileDialog if file_dialog is None else file_dialog
        message_box = QMessageBox if message_box is None else message_box
        options = prompt_export_options(window)
        if options is None:
            return
        fmt = options.fmt
        dialog_path, _ = file_dialog.getSaveFileName(
            window,
            "Export Figure",
            default_export_path(self._current_file_path_for_window(window), fmt),
            file_filter_for_format(fmt),
        )
        path = normalize_export_path(dialog_path, fmt)
        if path is None:
            return
        try:
            self._document_session_service_for_window(window).export_figure(
                path,
                fmt=fmt,
                scope=options.scope,
                dpi=options.dpi,
                background=options.background,
                sizing=options.sizing,
            )
        except Exception as exc:
            message_box.warning(
                window,
                "Export Error",
                f"Failed to export figure:\n{exc}",
            )
            return
        window.statusBar().showMessage(f"Exported: {path}", 4000)

    def load_canvas(
        self,
        window,
        *,
        file_dialog=None,
        message_box=None,
        read_document=None,
        resolve_load_path=None,
    ) -> None:
        file_dialog = QFileDialog if file_dialog is None else file_dialog
        message_box = QMessageBox if message_box is None else message_box
        read_document = default_read_document if read_document is None else read_document
        resolve_load_path = default_resolve_load_path if resolve_load_path is None else resolve_load_path
        dialog_path, _ = file_dialog.getOpenFileName(
            window,
            "Load Drawing",
            "",
            "Chemvas (*.chemvas);;JSON (*.json);;All Files (*)",
        )
        path = resolve_load_path(dialog_path)
        if path is None:
            return
        try:
            document = read_document(path)
        except Exception as exc:
            message_box.warning(window, "Load Error", f"Failed to load file:\n{exc}")
            return
        state = document.state
        if "sheets" in state:
            self._workbook_document.restore_workbook_document(window, state)
        else:
            self._workbook_document.restore_single_sheet_document(window, state)
        self._set_current_file_path_for_window(window, path)
        window.statusBar().showMessage(f"Loaded: {path}", 4000)

    def set_bond_length(self, window) -> None:
        current = self._bond_length_px_for_window(window)
        selected = prompt_bond_length(window, current)
        if selected is not None:
            self._geometry_controller_for_window(window).set_bond_length(selected)

    def setup_sheet(self, window) -> None:
        current_size = self._sheet_size_for_window(window)
        current_orientation = self._sheet_orientation_for_window(window)
        selected = prompt_sheet_setup(
            window,
            current_size=current_size,
            current_orientation=current_orientation,
        )
        if selected is not None:
            self._set_sheet_setup_for_window(window, selected.size, selected.orientation)


__all__ = ["MainWindowDocumentActionService"]
