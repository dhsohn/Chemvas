from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMainWindow

from ui.main_window_app import forget_window
from ui.main_window_bootstrap import bootstrap_main_window, build_main_window_runtime
from ui.session_autosave_hook import request_snapshot

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
        # Refresh the session now that this window is gone, so a document closed
        # while others remain drops out of the restore set. When this is the last
        # window (a quit), snapshot_now sees no windows and leaves the manifest
        # intact, so the session that was open is still restored next launch.
        request_snapshot()
        super().closeEvent(event)
