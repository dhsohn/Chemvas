"""Runtime glue for autosave & session restore.

Owns the periodic snapshot timer, flips the session's clean-exit flag on
``QApplication.aboutToQuit``, and — on launch — rebuilds the previous session's
windows from the store. All heavy lifting (what to persist, what to restore)
lives in :mod:`ui.session_snapshot_logic` / :mod:`ui.session_snapshot_store`;
this class just wires those to Qt and the window services.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer

from ui.canvas_document_metadata_state import (
    document_display_name_for,
    document_file_path_for,
    document_is_dirty_for,
)
from ui.canvas_window_access import snapshot_canvas_state_for
from ui.main_window_app import open_new_window as default_open_new_window
from ui.main_window_app import open_windows
from ui.main_window_ports import services_for_window as default_services_for_window
from ui.session_snapshot_logic import DocDescriptor

AUTOSAVE_INTERVAL_MS = 15_000


def collect_open_documents() -> list[DocDescriptor]:
    """Snapshot every open canvas across every window into plain descriptors."""
    documents: list[DocDescriptor] = []
    for window in open_windows():
        tab_references = getattr(window, "tab_references", None)
        if tab_references is None:
            continue
        for canvas in tab_references.all_canvases():
            state = snapshot_canvas_state_for(canvas)
            documents.append(
                DocDescriptor(
                    state=state,
                    file_path=document_file_path_for(canvas),
                    display_name=document_display_name_for(canvas),
                    dirty=document_is_dirty_for(canvas, state),
                )
            )
    return documents


class SessionRecoveryService:
    def __init__(
        self,
        store,
        *,
        open_new_window=default_open_new_window,
        services_for_window=default_services_for_window,
        current_documents=collect_open_documents,
        interval_ms: int = AUTOSAVE_INTERVAL_MS,
    ) -> None:
        self._store = store
        self._open_new_window = open_new_window
        self._services_for_window = services_for_window
        self._current_documents = current_documents
        self._interval_ms = interval_ms
        self._timer: QTimer | None = None

    def restore_previous(self, first_window) -> int:
        """Reopen the previous session's documents, reusing ``first_window``'s
        blank tab for the first one. Returns the count of recovered unsaved
        documents (a crash), which is also surfaced in the status bar."""
        result = self._store.consume_previous_sessions()
        for index, document in enumerate(result.docs):
            window = first_window if index == 0 else self._open_new_window(first_window)
            services = self._services_for_window(window)
            canvas = services.canvas_document_service.open_state(
                window,
                state=document.state,
                file_path=document.file_path,
                display_name=document.display_name,
            )
            if document.dirty:
                services.canvas_document_service.mark_dirty(canvas)
                services.canvas_document_service.refresh_tab_title(window, canvas)
        if result.recovered_unsaved:
            self._show_recovered_note(first_window, result.recovered_unsaved)
        return result.recovered_unsaved

    def start(self, app) -> None:
        """Begin this session, snapshot immediately, and arm the periodic timer
        plus the clean-exit hook."""
        self._store.begin()
        self.snapshot_now()
        about_to_quit = getattr(app, "aboutToQuit", None)
        connect = getattr(about_to_quit, "connect", None)
        if callable(connect):
            connect(self._on_about_to_quit)
        self._timer = QTimer()
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self.snapshot_now)
        self._timer.start()

    def snapshot_now(self) -> None:
        try:
            self._store.save_documents(self._current_documents())
        except Exception:
            # Autosave is a safety net; a failure here must never disrupt editing.
            pass

    def _on_about_to_quit(self) -> None:
        try:
            self._store.mark_clean_exit()
        except Exception:
            pass

    def _show_recovered_note(self, window, count: int) -> None:
        status_bar = getattr(window, "statusBar", None)
        if not callable(status_bar):
            return
        noun = "document" if count == 1 else "documents"
        status_bar().showMessage(f"Recovered {count} unsaved {noun} from your last session.", 8000)


__all__ = ["AUTOSAVE_INTERVAL_MS", "SessionRecoveryService", "collect_open_documents"]
