"""Runtime glue for autosave & session restore.

Owns the periodic snapshot timer, marks app-wide last-window shutdown before
deferred close snapshots run, records clean exit on ``QApplication.aboutToQuit``,
and supports explicit reconstruction of previous session windows. All
heavy lifting (what to persist, what to restore) lives in
:mod:`chemvas.features.session` / :mod:`chemvas.ui.session.session_snapshot_store`; this
class just wires those to Qt and the window services.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, override

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer
from PyQt6.QtWidgets import QMessageBox

from chemvas.features.session import (
    DocDescriptor,
    is_quit_pending,
    is_quitting,
    mark_quitting,
    set_quit_preparing,
    set_snapshot_hook,
)
from chemvas.shell.window_registry import (
    next_document_name,
    reserve_document_name,
)
from chemvas.shell.window_registry import open_windows as default_open_windows
from chemvas.ui.canvas.canvas_document_metadata_state import document_dirty_status_for
from chemvas.ui.session.app_data_paths import existing_session_roots, sessions_dir
from chemvas.ui.session.session_snapshot_store import new_session_store
from chemvas.ui.window.main_window_ports import status_bar_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.ui.window.main_window_like import MainWindowLike

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
        for canvas in window.tab_references.all_canvases():
            state, warnings = (
                canvas.services.canvas_document_session_service.snapshot_state_with_warnings()
            )
            display_name = canvas.runtime_state.document_metadata_state.display_name
            if warnings:
                detail = " ".join(warnings)
                raise AutosaveSnapshotError(f"{display_name}: {detail}")
            dirty, state_digest = document_dirty_status_for(canvas, state)
            documents.append(
                DocDescriptor(
                    state=state,
                    file_path=canvas.runtime_state.document_metadata_state.file_path,
                    display_name=display_name,
                    dirty=dirty,
                    state_digest=state_digest,
                )
            )
    return documents


def _window_services(window: MainWindowLike) -> Any:
    return window.services


class SessionRecoveryService:
    def __init__(
        self,
        store,
        *,
        open_new_window: Callable[..., Any],
        open_windows=default_open_windows,
        services_for_window=_window_services,
        current_documents=collect_open_documents,
        interval_ms: int = AUTOSAVE_INTERVAL_MS,
        recovery_warnings: tuple[str, ...] = (),
        recovery_stores: tuple = (),
    ) -> None:
        self._store = store
        self._open_new_window = open_new_window
        self._open_windows = open_windows
        self._services_for_window = services_for_window
        self._current_documents = current_documents
        self._interval_ms = interval_ms
        self._timer: QTimer | None = None
        self._recovery_stores = (store, *recovery_stores)
        self._pending_prune: list[tuple[Any, list[str]]] = []
        self._recovering = False
        self._opened_recoveries: dict[tuple[int, str], str] = {}
        self._snapshot_error: str | None = None
        self._quit_warning: str | None = None
        self._recovery_warning = " ".join(recovery_warnings) or None
        self._recovered_unsaved = 0
        self._quit_filter: _QuitEventFilter | None = None
        self._closing_application = False

    def restore_previous(self, first_window) -> int:
        """Reopen the previous session's documents, reusing ``first_window``'s
        blank tab for the first one. Returns the count of recovered unsaved
        documents (a crash), which is also surfaced in the status bar.

        Explicit recovery entry point; desktop startup does not call this.
        """
        if self._recovering or is_quit_pending():
            return 0
        if self._pending_prune:
            # These copies are already open. Retry only their durable handoff.
            self.snapshot_now()
            return 0
        self._recovering = True
        pending: list[tuple[Any, list[str]]] = []
        recovered = 0
        warnings: list[str] = []
        restored_names = set(self._opened_recoveries.values())
        reference_window = first_window
        try:
            for store in self._recovery_stores:
                result = store.consume_previous_sessions()
                warnings.extend(result.warnings)
                for document in result.docs:
                    if not document.dirty:
                        continue
                    key = (id(store), document.recovery_key)
                    if (
                        document.recovery_key is not None
                        and key in self._opened_recoveries
                    ):
                        continue
                    reserve_document_name(document.display_name)
                    window = (
                        first_window
                        if recovered == 0 and self._is_reusable(first_window)
                        else self._open_new_window(reference_window)
                    )
                    reference_window = window
                    display_name = document.display_name
                    if document.file_path:
                        display_name = f"{display_name} (recovered copy)"
                    if display_name in restored_names:
                        display_name = next_document_name()
                    restored_names.add(display_name)
                    services = self._services_for_window(window)
                    canvas = services.canvas_document_service.open_state(
                        window,
                        state=document.state,
                        file_path=None,
                        display_name=display_name,
                    )
                    services.canvas_document_service.mark_dirty(canvas)
                    services.canvas_document_service.refresh_tab_title(window, canvas)
                    if document.recovery_key is not None:
                        self._opened_recoveries[(id(store), document.recovery_key)] = (
                            display_name
                        )
                    recovered += 1
                pending.append((store, result.prune_ids))
        except Exception:
            self._recovery_warning = (
                "Recovery stopped. Original recovery files have been kept; "
                "any drawings already opened remain available."
            )
            self._publish_recovery_notice()
            raise
        finally:
            self._recovering = False
        # Publish source deletion eligibility only after every open succeeded.
        self._pending_prune = [(store, ids) for store, ids in pending if ids]
        self._recovered_unsaved = recovered
        self._recovery_warning = " ".join(warnings) or None
        self._publish_recovery_notice()
        if self._timer is not None:
            self.snapshot_now()
        self._show_startup_notice(first_window)
        return recovered

    def recover_with_dialog(self, window: MainWindowLike) -> None:
        if self._recovering or is_quit_pending():
            return
        if self._pending_prune:
            self.snapshot_now()
            QMessageBox.information(
                window,
                "Recover Unsaved Work",
                "Recovered drawings are already open. Save them to keep your work.",
            )
            return
        answer = QMessageBox.question(
            window,
            "Recover Unsaved Work",
            "Open unsaved drawings from interrupted sessions as new copies? "
            "Your open drawings and saved files will stay unchanged.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            count = self.restore_previous(window)
        except Exception as error:
            QMessageBox.warning(
                window, "Recovery Stopped", f"{self._recovery_warning}\n{error}"
            )
            return
        if self._recovery_warning:
            QMessageBox.warning(window, "Recovery Incomplete", self._recovery_warning)
        elif not count:
            QMessageBox.information(
                window, "Recover Unsaved Work", "No unsaved drawings were found."
            )

    def bind_window(self, window: MainWindowLike) -> None:
        status = self._services_for_window(window).status_service
        status.set_recovery_notice(window, self._recovery_warning)
        status.set_autosave_error(window, self._snapshot_error)
        status.set_quit_notice(window, self._quit_warning)

    def _publish_recovery_notice(self) -> None:
        for window in self._open_windows():
            self._services_for_window(window).status_service.set_recovery_notice(
                window, self._recovery_warning
            )

    def _is_reusable(self, window: MainWindowLike) -> bool:
        # A blank, untitled first window can host the first restored doc; once a
        # startup file (or an earlier restored doc) occupies it, later docs get
        # their own windows so single-document-per-window still holds.
        services = self._services_for_window(window)
        return services.canvas_document_service.reusable_open_target(window) is not None

    def start(self, app) -> None:
        """Begin this session, snapshot immediately, and arm the periodic timer,
        the save hook, and the clean-exit hook."""
        if isinstance(app, QObject):
            app.setProperty("chemvasSessionRecovery", self)
        self._store.begin()
        for window in self._open_windows():
            self.bind_window(window)
        # Release the old source sessions only once the recovered work is
        # *confirmed* persisted here. A failed snapshot (unwritable app-data,
        # full disk, serialization error) leaves them in place so the next
        # launch can still recover. A later successful timer tick both clears
        # the warning and releases the old source sessions.
        self.snapshot_now()
        windows = self._open_windows()
        if windows:
            # Show recovery availability after any startup file's status message.
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
        self._set_quit_notice(None)
        set_quit_preparing(True)
        try:
            for window in windows:
                actions = self._services_for_window(window).document_action_service
                if not actions.confirm_close_window(window):
                    return True
            if list(self._open_windows()) != windows:
                self._set_quit_notice(
                    "Quit paused: the open windows changed. Try Quit again."
                )
                return True
            # Every canvas is now saved or explicitly discarded. Clean-exit
            # recovery needs only saved paths; serializing live discarded data
            # could reject stale plans and undo the user's close decision.
            confirmed_documents = [
                DocDescriptor(
                    state={},
                    file_path=canvas.runtime_state.document_metadata_state.file_path,
                    display_name=canvas.runtime_state.document_metadata_state.display_name,
                    dirty=False,
                )
                for window in windows
                for canvas in window.tab_references.all_canvases()
            ]
            if not self.snapshot_now(documents=confirmed_documents):
                # Keep the previous snapshots and every live document. The
                # persistent autosave error explains why Quit could not finish.
                return True
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            self._set_quit_notice(f"Quit paused: {detail}")
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
        if self._recovering:
            return False
        if is_quitting():
            return True
        try:
            self._store.save_documents(
                self._current_documents() if documents is None else documents
            )
            if self._pending_prune:
                for store, ids in self._pending_prune:
                    store.prune_sessions(ids)
                self._pending_prune = []
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            self._set_snapshot_error(f"Autosave paused: {detail}")
            return False
        self._set_snapshot_error(None)
        return True

    def _set_snapshot_error(self, message: str | None) -> None:
        self._snapshot_error = message
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

    def _set_quit_notice(self, message: str | None) -> None:
        self._quit_warning = message
        for window in self._open_windows():
            self._services_for_window(window).status_service.set_quit_notice(
                window, message
            )

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

    def _show_recovered_note(self, window: MainWindowLike, count: int) -> None:
        status_bar = getattr(window, "statusBar", None)
        if not callable(status_bar):
            return
        noun = "document" if count == 1 else "documents"
        status_bar().showMessage(
            f"Recovered {count} unsaved {noun} from your last session.", 8000
        )

    def _show_startup_notice(self, window: MainWindowLike) -> None:
        if self._recovery_warning:
            status_bar_for(window).showMessage(self._recovery_warning)
        elif self._recovered_unsaved:
            self._show_recovered_note(window, self._recovered_unsaved)


def create_session_recovery_service(
    *, open_new_window: Callable[..., Any]
) -> SessionRecoveryService:
    """Build the production recovery service, rooted at the app-data sessions dir.

    A single entry point keeps bootstrap startup decoupled from the store/paths
    modules (it imports only this factory).
    """
    root = sessions_dir()
    store = new_session_store(root)
    store.prune_completed_sessions()
    recovery_stores = tuple(
        new_session_store(candidate)
        for candidate in dict.fromkeys(existing_session_roots())
        if candidate.resolve() != root.resolve()
    )
    available = any(
        candidate.unrestored_snapshot_directories()
        for candidate in (store, *recovery_stores)
    )
    warnings = (
        (
            "Unsaved work is available. Choose File → Recover Unsaved Work… to open copies.",
        )
        if available
        else ()
    )
    return SessionRecoveryService(
        store,
        open_new_window=open_new_window,
        recovery_warnings=warnings,
        recovery_stores=recovery_stores,
    )


def bind_recovery_for_window(window: MainWindowLike) -> None:
    app = QCoreApplication.instance()
    service = app.property("chemvasSessionRecovery") if app is not None else None
    if isinstance(service, SessionRecoveryService):
        service.bind_window(window)


def recover_unsaved_work_for_window(window: MainWindowLike) -> None:
    app = QCoreApplication.instance()
    service = app.property("chemvasSessionRecovery") if app is not None else None
    if isinstance(service, SessionRecoveryService):
        service.recover_with_dialog(window)


__all__ = [
    "AUTOSAVE_INTERVAL_MS",
    "AutosaveSnapshotError",
    "SessionRecoveryService",
    "bind_recovery_for_window",
    "collect_open_documents",
    "create_session_recovery_service",
    "recover_unsaved_work_for_window",
]
