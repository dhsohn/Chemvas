from __future__ import annotations

from pathlib import Path

from core.document_io import read_document as default_read_document
from core.svg_roundtrip import (
    extract_chemvas_document_from_svg as default_read_editable_svg,
)
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from ui.canvas_view import CanvasView
from ui.canvas_window_access import save_canvas_to_file_for
from ui.export_dialog_logic import (
    default_export_path,
    file_filter_for_format,
    normalize_export_path,
)
from ui.main_window_document_dialogs import (
    prompt_export_options,
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
from ui.open_document_lookup import find_open_document
from ui.rdkit_export_job_state import rdkit_export_jobs_for
from ui.recent_documents_store import record_recent
from ui.session_autosave_hook import request_snapshot


class MainWindowDocumentActionService:
    def __init__(
        self,
        *,
        document_session_service_for_window,
        active_canvas_for_window,
        active_canvas_or_none_for_window,
        canvas_document_service,
    ) -> None:
        self._document_session_service_for_window = document_session_service_for_window
        self._active_canvas_for_window = active_canvas_for_window
        self._active_canvas_or_none_for_window = active_canvas_or_none_for_window
        self._canvas_documents = canvas_document_service

    @staticmethod
    def normalize_xyz_export_path(dialog_path: str | None) -> str | None:
        if not dialog_path:
            return None
        path = Path(dialog_path)
        if path.suffix:
            return str(path)
        return str(path.with_suffix(".xyz"))

    def current_file_path(self, window, *, canvas: CanvasView | None = None) -> str | None:
        target = self._active_canvas_for_window(window) if canvas is None else canvas
        return self._canvas_documents.file_path(target)

    def default_xyz_export_path(self, window) -> str:
        current_path = self.current_file_path(window)
        if current_path:
            return str(Path(current_path).with_suffix(".xyz"))
        return ""

    @staticmethod
    def normalize_mol_export_path(dialog_path: str | None) -> str | None:
        if not dialog_path:
            return None
        path = Path(dialog_path)
        if path.suffix:
            return str(path)
        return str(path.with_suffix(".mol"))

    def default_mol_export_path(self, window) -> str:
        current_path = self.current_file_path(window)
        if current_path:
            return str(Path(current_path).with_suffix(".mol"))
        return ""

    def default_save_dialog_path(self, window, *, canvas: CanvasView | None = None) -> str:
        return self.current_file_path(window, canvas=canvas) or ""

    def save_canvas_to_path(
        self,
        window,
        path: str,
        *,
        canvas: CanvasView | None = None,
        message_box=None,
    ) -> bool:
        message_box = QMessageBox if message_box is None else message_box
        target = self._active_canvas_for_window(window) if canvas is None else canvas
        try:
            warnings = save_canvas_to_file_for(target, path)
        except Exception as exc:
            message_box.warning(window, "Save Error", f"Failed to save file:\n{exc}")
            return False
        self._canvas_documents.set_file_path(target, path)
        self._canvas_documents.set_display_name(target, self._canvas_documents.display_name_for_path(path) or path)
        self._canvas_documents.mark_clean(target)
        self._canvas_documents.refresh_tab_title(window, target)
        record_recent(path)
        # Refresh the autosave manifest now that this document has a (new) path,
        # so a Save chosen from the quit close-prompt is reflected before the
        # clean-exit flag is written.
        request_snapshot()
        window.statusBar().showMessage(f"Saved: {path}", 4000)
        if warnings:
            message_box.warning(
                window,
                "Save Adjusted Document",
                "Saved file, but Chemvas adjusted document data before writing:\n\n- "
                + "\n- ".join(warnings),
            )
        return True

    def save_canvas(
        self,
        window,
        *,
        canvas: CanvasView | None = None,
        resolve_save_path=None,
    ) -> bool:
        resolve_save_path = default_resolve_save_path if resolve_save_path is None else resolve_save_path
        path = resolve_save_path(current_path=self.current_file_path(window, canvas=canvas))
        if path is None:
            return self.save_canvas_as(window, canvas=canvas)
        return self.save_canvas_to_path(window, path, canvas=canvas)

    def save_canvas_as(
        self,
        window,
        *,
        canvas: CanvasView | None = None,
        file_dialog=None,
        resolve_save_as_path=None,
    ) -> bool:
        file_dialog = QFileDialog if file_dialog is None else file_dialog
        resolve_save_as_path = (
            default_resolve_save_as_path if resolve_save_as_path is None else resolve_save_as_path
        )
        dialog_path, _ = file_dialog.getSaveFileName(
            window,
            "Save Drawing As",
            self.default_save_dialog_path(window, canvas=canvas),
            "Chemvas (*.chemvas);;JSON (*.json);;All Files (*)",
        )
        path = resolve_save_as_path(dialog_path)
        if path is None:
            return False
        return self.save_canvas_to_path(window, path, canvas=canvas)

    def export_xyz(
        self,
        window,
        *,
        file_dialog=None,
        message_box=None,
        selected_only: bool = False,
        dialog_parent=None,
        status_sink=None,
    ) -> None:
        file_dialog = QFileDialog if file_dialog is None else file_dialog
        message_box = QMessageBox if message_box is None else message_box
        dialog_parent = window if dialog_parent is None else dialog_parent
        dialog_path, _ = file_dialog.getSaveFileName(
            dialog_parent,
            "Export 3D XYZ",
            self.default_xyz_export_path(window),
            "XYZ (*.xyz);;All Files (*)",
        )
        path = self.normalize_xyz_export_path(dialog_path)
        if path is None:
            return
        previous_status = window.statusBar().currentMessage()

        def report(message: str) -> None:
            if status_sink is not None:
                status_sink(message)

        def on_success(export_path: str) -> None:
            window.statusBar().showMessage(f"Exported XYZ: {export_path}", 4000)
            report(f"Exported XYZ: {export_path}")

        def handle_error(message: str) -> None:
            message_box.warning(
                dialog_parent,
                "Export Error",
                f"Failed to export XYZ:\n{message}",
            )
            window.statusBar().showMessage(previous_status)
            report(f"Export failed: {message}")

        window.statusBar().showMessage(f"Exporting XYZ: {path}")
        report(f"Exporting XYZ: {path}")
        export_kwargs = {"selected_only": True} if selected_only else {}
        self._document_session_service_for_window(window).export_xyz_async(
            path,
            on_success=on_success,
            on_error=handle_error,
            **export_kwargs,
        )

    def export_mol(
        self,
        window,
        *,
        file_dialog=None,
        message_box=None,
        selected_only: bool = False,
        dialog_parent=None,
        status_sink=None,
    ) -> None:
        file_dialog = QFileDialog if file_dialog is None else file_dialog
        message_box = QMessageBox if message_box is None else message_box
        dialog_parent = window if dialog_parent is None else dialog_parent
        dialog_path, _ = file_dialog.getSaveFileName(
            dialog_parent,
            "Export MOL",
            self.default_mol_export_path(window),
            "MDL Molfile (*.mol);;All Files (*)",
        )
        path = self.normalize_mol_export_path(dialog_path)
        if path is None:
            return

        def report(message: str) -> None:
            if status_sink is not None:
                status_sink(message)

        try:
            self._document_session_service_for_window(window).export_mol(
                path, selected_only=selected_only
            )
        except Exception as exc:
            message = str(exc) or "Failed to export MOL."
            message_box.warning(dialog_parent, "Export Error", f"Failed to export MOL:\n{message}")
            report(f"Export failed: {message}")
            return
        window.statusBar().showMessage(f"Exported MOL: {path}", 4000)
        report(f"Exported MOL: {path}")

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
            default_export_path(self.current_file_path(window), fmt),
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
                editable_svg=options.editable_svg,
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
        read_editable_svg=None,
        resolve_load_path=None,
        target_provider=None,
    ) -> bool:
        file_dialog = QFileDialog if file_dialog is None else file_dialog
        dialog_path, _ = file_dialog.getOpenFileName(
            window,
            "Load Drawing",
            "",
            "Chemvas / Editable SVG (*.chemvas *.json *.svg);;Chemvas (*.chemvas);;Editable SVG (*.svg);;JSON (*.json);;All Files (*)",
        )
        path = resolve_load_path(dialog_path) if resolve_load_path is not None else default_resolve_load_path(dialog_path)
        if path is None:
            return False
        return self.load_canvas_from_path(
            window,
            path,
            message_box=message_box,
            read_document=read_document,
            read_editable_svg=read_editable_svg,
            target_provider=target_provider,
        )

    def load_canvas_from_path(
        self,
        window,
        path: str,
        *,
        message_box=None,
        read_document=None,
        read_editable_svg=None,
        target_provider=None,
    ) -> bool:
        message_box = QMessageBox if message_box is None else message_box
        read_document = default_read_document if read_document is None else read_document
        read_editable_svg = default_read_editable_svg if read_editable_svg is None else read_editable_svg
        # If this exact file is already open, switch to that window instead of
        # spawning a second, independently-editable copy. (Editable SVGs open
        # unbound to their path, so this only matches real .chemvas documents.)
        already_open = find_open_document(path)
        if already_open is not None:
            open_window, open_canvas = already_open
            self._activate_open_document(open_window, open_canvas, path)
            return True
        # Resolve the destination window only after the file reads successfully so
        # a missing or unreadable file never spawns an empty window.
        target = window
        try:
            if Path(path).suffix.lower() == ".svg":
                document = read_editable_svg(path)
                target = target_provider() if target_provider is not None else window
                self._canvas_documents.open_state(
                    target,
                    state=document.state,
                    file_path=None,
                    display_name=Path(path).name,
                )
                target.statusBar().showMessage(f"Loaded editable SVG: {path}", 4000)
                record_recent(path)
                return True
            document = read_document(path)
            target = target_provider() if target_provider is not None else window
            self._canvas_documents.open_state(target, state=document.state, file_path=path)
        except Exception as exc:
            message_box.warning(window, "Load Error", f"Failed to load file:\n{exc}")
            return False
        target.statusBar().showMessage(f"Loaded: {path}", 4000)
        record_recent(path)
        return True

    def _activate_open_document(self, window, canvas: CanvasView, path: str) -> None:
        """Bring the window already showing ``path`` to the front and select its
        tab, then note it — used instead of opening a duplicate."""
        tab_references = getattr(window, "tab_references", None)
        if tab_references is not None:
            tab_references.canvas_tabs.setCurrentWidget(canvas)
        for method_name in ("show", "raise_", "activateWindow"):
            method = getattr(window, method_name, None)
            if callable(method):
                method()
        status_bar = getattr(window, "statusBar", None)
        if callable(status_bar):
            status_bar().showMessage(f"Already open: {path}", 4000)

    def close_canvas_tab(self, window, index: int) -> bool:
        tab_refs = window.tab_references
        widget = tab_refs.canvas_tabs.widget(index)
        if not isinstance(widget, CanvasView):
            return False
        if not self.confirm_close_canvas(window, widget):
            return False
        self._canvas_documents.remove_canvas(window, widget)
        return True

    def confirm_close_window(self, window) -> bool:
        for canvas in list(window.tab_references.all_canvases()):
            index = window.tab_references.active_canvas_tab_index(canvas)
            if index >= 0:
                window.tab_references.canvas_tabs.setCurrentIndex(index)
            if not self.confirm_close_canvas(window, canvas):
                return False
        return True

    def confirm_close_canvas(self, window, canvas: CanvasView, *, message_box=None) -> bool:
        message_box = QMessageBox if message_box is None else message_box
        if rdkit_export_jobs_for(canvas):
            name = self._canvas_documents.display_name(canvas)
            message_box.warning(
                window,
                "XYZ Export in Progress",
                f"Wait for the 3D XYZ export from {name} to finish before closing it.",
            )
            return False
        if not self._canvas_documents.is_dirty(canvas):
            return True
        name = self._canvas_documents.display_name(canvas)
        choice = message_box.question(
            window,
            "Save Changes",
            f"Save changes to {name} before closing?",
            (
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel
            ),
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save_canvas(window, canvas=canvas)
        if choice == QMessageBox.StandardButton.Discard:
            return True
        return False


__all__ = ["MainWindowDocumentActionService"]
