from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMainWindow

from ui.main_window_app import forget_window
from ui.main_window_bootstrap import bootstrap_main_window, build_main_window_runtime
from ui.session_autosave_hook import request_snapshot_on_window_close

if TYPE_CHECKING:
    from ui.main_window_state import MainWindowState
    from ui.main_window_tab_references import MainWindowTabReferences
    from ui.main_window_ui_references import MainWindowUiReferences


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        runtime = build_main_window_runtime(self)
        self._state = runtime.state
        self._ui_refs = runtime.ui_refs
        self._tab_refs = runtime.tab_refs
        self._services = runtime.services
        self._preview_3d = runtime.preview_3d
        bootstrap_main_window(self, runtime)

    @property
    def ui_references(self) -> MainWindowUiReferences:
        return self._ui_refs

    @property
    def tab_references(self) -> MainWindowTabReferences:
        return self._tab_refs

    @property
    def runtime_state(self) -> MainWindowState:
        return self._state

    def closeEvent(self, event) -> None:
        if not self._services.document_action_service.confirm_close_window(self):
            event.ignore()
            return
        preview_window = self._ui_refs.preview_window
        if preview_window is not None:
            preview_window.hide()
        shutdown_preview = getattr(self._preview_3d, "shutdown", None)
        if callable(shutdown_preview):
            shutdown_preview()
        forget_window(self)
        # Defer a session refresh: it runs only if the app keeps running (a
        # standalone window close drops the closed document from the restore
        # set). During app-wide quit, aboutToQuit sets the quitting flag before
        # this fires, so it no-ops and the full open set is preserved.
        request_snapshot_on_window_close()
        super().closeEvent(event)
