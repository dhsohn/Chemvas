"""Runtime glue for autosave & session restore.

Owns the periodic snapshot timer, marks app-wide last-window shutdown before
deferred close snapshots run, records clean exit on ``QApplication.aboutToQuit``,
and — on launch — rebuilds the previous session's windows from the store. All
heavy lifting (what to persist, what to restore) lives in
:mod:`chemvas.features.session` / :mod:`chemvas.ui.session_snapshot_store`; this
class just wires those to Qt and the window services.
"""

from __future__ import annotations

import contextlib
from typing import override

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer

from chemvas.bootstrap.window_registry import (
    next_document_name,
    reserve_document_name,
)
from chemvas.bootstrap.window_registry import (
    open_new_window as default_open_new_window,
)
from chemvas.bootstrap.window_registry import (
    open_windows as default_open_windows,
)
from chemvas.features.session import (
    DocDescriptor,
    is_quit_pending,
    is_quitting,
    mark_quitting,
    set_quit_preparing,
    set_snapshot_hook,
)
from chemvas.ui.app_data_paths import existing_session_roots, sessions_dir
from chemvas.ui.canvas_document_metadata_state import (
    document_display_name_for,
    document_file_path_for,
    document_is_dirty_for,
    set_document_source_sha256_for,
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


class _QuitEventFilter(QObject):
    def __init__(self, service, parent: QObject) -> None:
        super().__init__(parent)
        self._service = service

    @override
    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if (
            watched is QCoreApplication.instance()
            and event is not None
            and event.type() == QEvent.Type.Quit
        ):
            return self._service.intercept_application_quit()
        return False


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
        recovery_warnings: tuple[str, ...] = (),
    ) -> None:
        self._store = store
        self._open_new_window = open_new_window
        self._open_windows = open_windows
        self._services_for_window = services_for_window
        self._current_documents = current_documents
        self._interval_ms = interval_ms
        self._timer: QTimer | None = None
        self._pending_prune: list[str] = []
        self._recovery_warning = " ".join(recovery_warnings) or None
        self._recovered_unsaved = 0
        self._quit_filter: _QuitEventFilter | None = None
        self._closing_application = False

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
        self._recovered_unsaved = result.recovered_unsaved
        for document in result.docs:
            reserve_document_name(document.display_name)
        restored_names: set[str] = set()
        reference_window = first_window
        for index, document in enumerate(result.docs):
            reuse_first = index == 0 and self._is_reusable(first_window)
            window = (
                first_window if reuse_first else self._open_new_window(reference_window)
            )
            reference_window = window
            display_name = document.display_name
            if document.file_path is None and display_name in restored_names:
                display_name = next_document_name()
            restored_names.add(display_name)
            services = self._services_for_window(window)
            canvas = services.canvas_document_service.open_state(
                window,
                state=document.state,
                file_path=document.file_path,
                display_name=display_name,
            )
            if document.source_sha256 is not None:
                set_document_source_sha256_for(canvas, document.source_sha256)
            if document.dirty:
                services.canvas_document_service.mark_dirty(canvas)
                services.canvas_document_service.refresh_tab_title(window, canvas)
        if result.warnings:
            self._recovery_warning = " ".join(
                part for part in (self._recovery_warning, *result.warnings) if part
            )
        self._show_startup_notice(first_window)
        if self._recovery_warning:
            self._set_snapshot_error(None)
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
        windows = self._open_windows()
        if windows:
            # Startup file opening happens between restore_previous and start.
            # Its duplicate-open status must not erase the recovery result.
            self._show_startup_notice(windows[0])
        set_snapshot_hook(self.snapshot_now)
        about_to_quit = getattr(app, "aboutToQuit", None)
        connect = getattr(about_to_quit, "connect", None)
        if callable(connect):
            connect(self._on_about_to_quit)
        last_window_closed = getattr(app, "lastWindowClosed", None)
        connect = getattr(last_window_closed, "connect", None)
        if callable(connect):
            connect(self._on_last_window_closed)
        self._timer = QTimer()
        if isinstance(app, QObject):
            self._timer.setParent(app)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self.snapshot_now)
        self._timer.start()
        if isinstance(app, QObject):
            self._quit_filter = _QuitEventFilter(self, app)
            app.installEventFilter(self._quit_filter)

    def intercept_application_quit(self) -> bool:
        """Resolve all close prompts before Qt can remove the first window.

        Modal prompts run nested event loops, so deferred close snapshots and
        post-save snapshots otherwise see a progressively smaller workspace.
        After confirmation, the complete final snapshot stays frozen while the
        existing per-window preview shutdown finishes asynchronously.
        """
        if self._closing_application:
            return bool(self._open_windows())
        windows = list(self._open_windows())
        if not windows:
            return False
        if is_quit_pending():
            return True
        set_quit_preparing(True)
        try:
            for window in windows:
                actions = self._services_for_window(window).document_action_service
                if not actions.confirm_close_window(window):
                    return True
            if list(self._open_windows()) != windows:
                self._set_snapshot_error(
                    "Quit paused: the open windows changed. Try Quit again."
                )
                return True
            # Every canvas is now saved or explicitly discarded. Clean-exit
            # recovery needs only saved paths; serializing live discarded data
            # could reject stale plans and undo the user's close decision.
            confirmed_documents = [
                DocDescriptor(
                    state={},
                    file_path=document_file_path_for(canvas),
                    display_name=document_display_name_for(canvas),
                    dirty=False,
                )
                for window in windows
                for canvas in all_canvases_for_window(window)
            ]
            if not self.snapshot_now(documents=confirmed_documents):
                # Keep the previous snapshots and every live document. The
                # persistent autosave error explains why Quit could not finish.
                return True
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            self._set_snapshot_error(f"Quit paused: {detail}")
            return True
        finally:
            set_quit_preparing(False)
        self._closing_application = True
        mark_quitting()
        for window in windows:
            window.setEnabled(False)
        for window in windows:
            window.close_after_confirmation()
        return True

    def snapshot_now(self, *, documents: list[DocDescriptor] | None = None) -> bool:
        """Persist the current open set without interrupting editing.

        Failures return False, retain source recovery sessions, and remain visible
        in each window until a later snapshot succeeds. The Quit coordinator may
        supply path-only descriptors after all close decisions are confirmed;
        ordinary autosave always collects and validates the full live state.
        """
        if is_quitting():
            return True
        try:
            self._store.save_documents(
                self._current_documents() if documents is None else documents
            )
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
        if self._recovery_warning:
            message = "\n".join(
                part for part in (message, self._recovery_warning) if part
            )
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
        # Explicit Quit has already resolved every prompt and frozen the final
        # workspace. Automatic last-window exit retains its last open set.
        mark_quitting()
        # Unwritable or full app-data is the one failure this can hit: the
        # manifest read already returns None for anything it cannot parse,
        # and the write is the atomic text writer. Quitting must not abort,
        # and the consequence is conservative — without the flag the next
        # launch treats this session as a crash and offers the work back.
        # Anything else here is a bug and now propagates.
        with contextlib.suppress(OSError):
            self._store.mark_clean_exit()

    def _on_last_window_closed(self) -> None:
        """Mark an automatic last-window quit before deferred close snapshots.

        Qt emits ``lastWindowClosed`` before the zero-delay snapshot scheduled
        by the window close handler, while ``aboutToQuit`` can arrive after it.
        Without this earlier hook, closing the final window can overwrite the
        session manifest with an empty open set just before a clean exit.
        """
        app = QCoreApplication.instance()
        quit_on_last_window_closed = getattr(app, "quitOnLastWindowClosed", None)
        if callable(quit_on_last_window_closed) and quit_on_last_window_closed():
            mark_quitting()
        if self._closing_application:
            # Explicit Quit also finishes on platforms configured to keep the
            # application running after the final ordinary window close.
            QTimer.singleShot(0, QCoreApplication.quit)

    def _show_recovered_note(self, window, count: int) -> None:
        status_bar = getattr(window, "statusBar", None)
        if not callable(status_bar):
            return
        noun = "document" if count == 1 else "documents"
        status_bar().showMessage(
            f"Recovered {count} unsaved {noun} from your last session.", 8000
        )

    def _show_startup_notice(self, window) -> None:
        if self._recovery_warning:
            window.statusBar().showMessage(self._recovery_warning)
        elif self._recovered_unsaved:
            self._show_recovered_note(window, self._recovered_unsaved)


def create_session_recovery_service() -> SessionRecoveryService:
    """Build the production recovery service, rooted at the app-data sessions dir.

    A single entry point keeps bootstrap startup decoupled from the store/paths
    modules (it imports only this factory).
    """
    root = sessions_dir()
    warnings = []
    for candidate in existing_session_roots():
        if candidate == root.resolve():
            continue
        for directory in new_session_store(candidate).unrestored_snapshot_directories():
            warnings.append(
                f"Unsaved recovery files were found in {directory} and kept there. "
                "They were not opened automatically. To recover, copy a doc-*.json "
                "snapshot to a new .chemvas file and open that copy; keep the original."
            )
    return SessionRecoveryService(
        new_session_store(root), recovery_warnings=tuple(warnings)
    )


__all__ = [
    "AUTOSAVE_INTERVAL_MS",
    "AutosaveSnapshotError",
    "SessionRecoveryService",
    "collect_open_documents",
    "create_session_recovery_service",
]
