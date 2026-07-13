"""Runtime glue for autosave & session restore.

Owns the periodic snapshot timer, flips the session's clean-exit flag on
``QApplication.aboutToQuit``, and — on launch — rebuilds the previous session's
windows from the store. All heavy lifting (what to persist, what to restore)
lives in :mod:`ui.session_snapshot_logic` / :mod:`ui.session_snapshot_store`;
this class just wires those to Qt and the window services.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer

from ui.app_data_paths import sessions_dir
from ui.canvas_document_metadata_state import (
    document_display_name_for,
    document_file_path_for,
    document_is_dirty_for,
)
from ui.canvas_window_access import snapshot_canvas_state_for
from ui.main_window_app import open_new_window as default_open_new_window
from ui.main_window_app import open_windows
from ui.main_window_ports import services_for_window as default_services_for_window
from ui.session_autosave_hook import mark_quitting, set_snapshot_hook
from ui.session_snapshot_logic import DocDescriptor
from ui.session_snapshot_store import new_session_store

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
        self._pending_prune: list[str] = []

    def restore_previous(self, first_window, *, include_clean_session: bool = True) -> int:
        """Reopen the previous session's documents, reusing ``first_window``'s
        blank tab for the first one. Returns the count of recovered unsaved
        documents (a crash), which is also surfaced in the status bar.

        ``include_clean_session`` is set False when the launch already has a
        startup file: crashed work is still recovered, but a cleanly-closed
        workspace is not dragged back on top of the requested document.
        """
        result = self._store.consume_previous_sessions(include_clean_session=include_clean_session)
        # Prune the consumed source sessions only after start() re-snapshots the
        # restored docs, so a crash mid-restore keeps the recoverable copies.
        self._pending_prune = result.prune_ids
        for index, document in enumerate(result.docs):
            reuse_first = index == 0 and self._is_reusable(first_window)
            window = first_window if reuse_first else self._open_new_window(first_window)
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

    def _is_reusable(self, window) -> bool:
        # A blank, untitled first window can host the first restored doc; once a
        # startup file (or an earlier restored doc) occupies it, later docs get
        # their own windows so single-document-per-window still holds.
        services = self._services_for_window(window)
        return services.canvas_document_service.reusable_open_target(window) is not None

    def start(self, app) -> None:
        """Begin this session, snapshot immediately, and arm the periodic timer,
        the save hook, and the clean-exit hook."""
        self._store.begin()
        # Release the old source sessions only once the recovered work is
        # *confirmed* persisted here. A failed snapshot (unwritable app-data,
        # full disk, serialization error) leaves them in place so the next
        # launch can still recover.
        if self.snapshot_now():
            self._store.prune_sessions(self._pending_prune)
            self._pending_prune = []
        set_snapshot_hook(self.snapshot_now)
        about_to_quit = getattr(app, "aboutToQuit", None)
        connect = getattr(about_to_quit, "connect", None)
        if callable(connect):
            connect(self._on_about_to_quit)
        self._timer = QTimer()
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self.snapshot_now)
        self._timer.start()

    def snapshot_now(self) -> bool:
        """Persist the current open set. Returns True on success; a failure is
        swallowed (autosave must never disrupt editing) and reported as False so
        callers can avoid destructive follow-ups like pruning source sessions."""
        try:
            self._store.save_documents(self._current_documents())
        except Exception:
            return False
        return True

    def _on_about_to_quit(self) -> None:
        # Signal quit before windows finish closing so their deferred close
        # snapshots become no-ops and the full open set is preserved.
        mark_quitting()
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


def create_session_recovery_service() -> SessionRecoveryService:
    """Build the production recovery service, rooted at the app-data sessions dir.

    A single entry point keeps ``chemvas.main`` decoupled from the store/paths
    modules (it imports only this factory).
    """
    return SessionRecoveryService(new_session_store(sessions_dir()))


__all__ = [
    "AUTOSAVE_INTERVAL_MS",
    "SessionRecoveryService",
    "collect_open_documents",
    "create_session_recovery_service",
]
