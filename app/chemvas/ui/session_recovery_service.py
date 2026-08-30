"""Runtime glue for autosave & session restore.

Owns the periodic snapshot timer, flips the session's clean-exit flag on
``QApplication.aboutToQuit``, and — on launch — rebuilds the previous session's
windows from the store. All heavy lifting (what to persist, what to restore)
lives in :mod:`chemvas.features.session` / :mod:`chemvas.ui.session_snapshot_store`;
this class just wires those to Qt and the window services.
"""

from __future__ import annotations

import contextlib

from PyQt6.QtCore import QTimer

from chemvas.bootstrap.window_registry import (
    open_new_window as default_open_new_window,
)
from chemvas.bootstrap.window_registry import open_windows as default_open_windows
from chemvas.features.session import DocDescriptor, mark_quitting, set_snapshot_hook
from chemvas.ui.app_data_paths import sessions_dir
from chemvas.ui.canvas_document_metadata_state import (
    document_display_name_for,
    document_file_path_for,
    document_is_dirty_for,
)
from chemvas.ui.canvas_window_access import snapshot_canvas_state_with_warnings_for
from chemvas.ui.main_window_ports import all_canvases_for_window
from chemvas.ui.main_window_ports import (
    services_for_window as default_services_for_window,
)
from chemvas.ui.session_snapshot_store import new_session_store

AUTOSAVE_INTERVAL_MS = 15_000


class AutosaveSnapshotError(RuntimeError):
    """The live document cannot be serialized without adjustment or omission."""


def collect_open_documents() -> list[DocDescriptor]:
    """Snapshot every open canvas, rejecting any adjusted or incomplete state."""
    documents: list[DocDescriptor] = []
    for window in default_open_windows():
        for canvas in all_canvases_for_window(window):
            state, warnings = snapshot_canvas_state_with_warnings_for(canvas)
            display_name = document_display_name_for(canvas)
            if warnings:
                detail = " ".join(warnings)
                raise AutosaveSnapshotError(f"{display_name}: {detail}")
            documents.append(
                DocDescriptor(
                    state=state,
                    file_path=document_file_path_for(canvas),
                    display_name=display_name,
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
        open_windows=default_open_windows,
        services_for_window=default_services_for_window,
        current_documents=collect_open_documents,
        interval_ms: int = AUTOSAVE_INTERVAL_MS,
    ) -> None:
        self._store = store
        self._open_new_window = open_new_window
        self._open_windows = open_windows
        self._services_for_window = services_for_window
        self._current_documents = current_documents
        self._interval_ms = interval_ms
        self._timer: QTimer | None = None
        self._pending_prune: list[str] = []

    def restore_previous(self, first_window) -> int:
        """Reopen the previous session's documents, reusing ``first_window``'s
        blank tab for the first one. Returns the count of recovered unsaved
        documents (a crash), which is also surfaced in the status bar.

        This runs on every launch; a startup file is then opened on top of the
        restored workspace through the duplicate-open guard.
        """
        result = self._store.consume_previous_sessions()
        # Prune the consumed source sessions only after start() re-snapshots the
        # restored docs, so a crash mid-restore keeps the recoverable copies.
        self._pending_prune = result.prune_ids
        for index, document in enumerate(result.docs):
            reuse_first = index == 0 and self._is_reusable(first_window)
            window = (
                first_window if reuse_first else self._open_new_window(first_window)
            )
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
        # launch can still recover. A later successful timer tick both clears
        # the warning and releases the old source sessions.
        self.snapshot_now()
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
        """Persist the current open set without interrupting editing.

        Failures return False, retain source recovery sessions, and remain visible
        in each window until a later snapshot succeeds.
        """
        try:
            self._store.save_documents(self._current_documents())
            if self._pending_prune:
                self._store.prune_sessions(self._pending_prune)
                self._pending_prune = []
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            self._set_snapshot_error(f"Autosave paused: {detail}")
            return False
        self._set_snapshot_error(None)
        return True

    def _set_snapshot_error(self, message: str | None) -> None:
        for window in self._open_windows():
            try:
                self._services_for_window(window).status_service.set_autosave_error(
                    window, message
                )
            except RuntimeError as exc:
                # A window can disappear between the registry read and Qt update.
                # A failed next tick republishes the error; a success clears it.
                detail = str(exc)
                if "wrapped C/C++ object" in detail and "has been deleted" in detail:
                    continue
                raise

    def _on_about_to_quit(self) -> None:
        # Signal quit before windows finish closing so their deferred close
        # snapshots become no-ops and the full open set is preserved.
        mark_quitting()
        # Unwritable or full app-data is the one failure this can hit: the
        # manifest read already returns None for anything it cannot parse,
        # and the write is the atomic text writer. Quitting must not abort,
        # and the consequence is conservative — without the flag the next
        # launch treats this session as a crash and offers the work back.
        # Anything else here is a bug and now propagates.
        with contextlib.suppress(OSError):
            self._store.mark_clean_exit()

    def _show_recovered_note(self, window, count: int) -> None:
        status_bar = getattr(window, "statusBar", None)
        if not callable(status_bar):
            return
        noun = "document" if count == 1 else "documents"
        status_bar().showMessage(
            f"Recovered {count} unsaved {noun} from your last session.", 8000
        )


def create_session_recovery_service() -> SessionRecoveryService:
    """Build the production recovery service, rooted at the app-data sessions dir.

    A single entry point keeps bootstrap startup decoupled from the store/paths
    modules (it imports only this factory).
    """
    return SessionRecoveryService(new_session_store(sessions_dir()))


__all__ = [
    "AUTOSAVE_INTERVAL_MS",
    "AutosaveSnapshotError",
    "SessionRecoveryService",
    "collect_open_documents",
    "create_session_recovery_service",
]
