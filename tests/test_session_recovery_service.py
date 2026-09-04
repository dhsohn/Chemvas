from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtWidgets import QApplication

from chemvas.features.session import RestoredDoc
from chemvas.ui.session_recovery_service import (
    AutosaveSnapshotError,
    SessionRecoveryService,
    collect_open_documents,
)
from chemvas.ui.session_snapshot_store import RestoreResult
from tests.runtime_services import canvas_runtime_services


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeStatusBar:
    def __init__(self) -> None:
        self.messages: list[tuple[str, int]] = []

    def showMessage(self, message: str, timeout: int = 0) -> None:
        self.messages.append((message, timeout))


class _FakeWindow:
    def __init__(self, name: str) -> None:
        self.name = name
        self._status_bar = _FakeStatusBar()

    def statusBar(self) -> _FakeStatusBar:
        return self._status_bar


class _FakeDocService:
    def __init__(self) -> None:
        self.opened: list = []
        self.dirtied: list = []
        self.refreshed: list = []
        self.reusable = True

    def reusable_open_target(self, window):
        return object() if self.reusable else None

    def open_state(self, window, *, state, file_path, display_name=None):
        canvas = SimpleNamespace(
            window=window, state=state, file_path=file_path, display_name=display_name
        )
        self.opened.append(canvas)
        return canvas

    def mark_dirty(self, canvas) -> None:
        self.dirtied.append(canvas)

    def refresh_tab_title(self, window, canvas) -> None:
        self.refreshed.append((window, canvas))


class _FakeStore:
    def __init__(self, result: RestoreResult) -> None:
        self._result = result
        self.begun = False
        self.saved: list = []
        self.pruned: list = []
        self.clean_exit = False
        self.events: list[str] = []

    def consume_previous_sessions(self) -> RestoreResult:
        return self._result

    def begin(self) -> None:
        self.begun = True
        self.events.append("begin")

    def save_documents(self, docs) -> None:
        self.saved.append(docs)
        self.events.append("save")

    def prune_sessions(self, session_ids) -> None:
        self.pruned.append(list(session_ids))
        self.events.append("prune")

    def mark_clean_exit(self) -> None:
        self.clean_exit = True


class _FakeSignal:
    def __init__(self) -> None:
        self.slots: list = []

    def connect(self, slot) -> None:
        self.slots.append(slot)


def _service(
    store,
    *,
    extra_windows=None,
    current_documents=list,
    open_windows=lambda: (),
    status_service=None,
):
    doc_service = _FakeDocService()
    services = canvas_runtime_services(
        canvas_document_service=doc_service,
        status_service=status_service or mock.Mock(),
    )
    spawned = list(extra_windows or [])
    service = SessionRecoveryService(
        store,
        open_new_window=lambda reference: spawned.pop(0),
        open_windows=open_windows,
        services_for_window=lambda window: services,
        current_documents=current_documents,
    )
    return service, doc_service


def test_restore_previous_rebuilds_windows_and_marks_recovered_dirty():
    first = _FakeWindow("first")
    second = _FakeWindow("second")
    result = RestoreResult(
        docs=[
            RestoredDoc(
                state={"m": 1}, file_path=None, display_name="Canvas 1", dirty=True
            ),
            RestoredDoc(
                state={"m": 2},
                file_path="/a/x.chemvas",
                display_name="x.chemvas",
                dirty=False,
            ),
        ],
        recovered_unsaved=1,
    )
    service, doc_service = _service(_FakeStore(result), extra_windows=[second])

    recovered = service.restore_previous(first)

    assert recovered == 1
    # First doc reuses the first window; the second spawns a new one.
    assert [c.window for c in doc_service.opened] == [first, second]
    assert [c.display_name for c in doc_service.opened] == ["Canvas 1", "x.chemvas"]
    # Only the unsaved doc is forced dirty.
    assert doc_service.dirtied == [doc_service.opened[0]]
    assert first.statusBar().messages
    assert "Recovered 1 unsaved document" in first.statusBar().messages[0][0]


def test_restore_gives_each_doc_its_own_window_when_first_is_occupied():
    # e.g. a crash-recovery launch that also opened a startup file: the first
    # window is taken, so recovered docs must not pile up as tabs there.
    first = _FakeWindow("first")
    spawned = [_FakeWindow("w1"), _FakeWindow("w2")]
    result = RestoreResult(
        docs=[
            RestoredDoc(
                state={"m": 1}, file_path="/a.chemvas", display_name="a", dirty=False
            ),
            RestoredDoc(
                state={"m": 2}, file_path="/b.chemvas", display_name="b", dirty=False
            ),
        ]
    )
    service, doc_service = _service(_FakeStore(result), extra_windows=list(spawned))
    doc_service.reusable = False  # first window already holds a document

    service.restore_previous(first)

    assert [canvas.window for canvas in doc_service.opened] == spawned  # never `first`


def test_restore_previous_is_silent_when_nothing_to_recover():
    first = _FakeWindow("first")
    service, doc_service = _service(_FakeStore(RestoreResult()))

    assert service.restore_previous(first) == 0
    assert doc_service.opened == []
    assert first.statusBar().messages == []


def test_snapshot_now_persists_the_current_documents():
    sentinel = [object()]
    service, _ = _service(
        _FakeStore(RestoreResult()), current_documents=lambda: sentinel
    )

    service.snapshot_now()

    assert service._store.saved == [sentinel]


def test_collect_open_documents_rejects_warning_bearing_snapshot():
    canvas = object()
    window = SimpleNamespace(
        tab_references=SimpleNamespace(all_canvases=lambda: [canvas])
    )
    warning = "The calculation plan was not saved because it is stale."

    with (
        mock.patch(
            "chemvas.ui.session_recovery_service.default_open_windows",
            return_value=(window,),
        ),
        mock.patch(
            "chemvas.ui.session_recovery_service."
            "snapshot_canvas_state_with_warnings_for",
            return_value=({"model": {}}, [warning]),
        ),
        mock.patch(
            "chemvas.ui.session_recovery_service.document_display_name_for",
            return_value="Canvas 1",
        ),
        pytest.raises(AutosaveSnapshotError) as error,
    ):
        collect_open_documents()

    assert str(error.value) == f"Canvas 1: {warning}"


def test_collect_open_documents_does_not_skip_an_unwired_window():
    with (
        mock.patch(
            "chemvas.ui.session_recovery_service.default_open_windows",
            return_value=(object(),),
        ),
        pytest.raises(AttributeError, match="tab_references"),
    ):
        collect_open_documents()


def test_snapshot_now_swallows_store_errors_and_reports_failure():
    store = _FakeStore(RestoreResult())
    window = _FakeWindow("first")
    status_service = mock.Mock()

    def boom(_docs):
        raise RuntimeError("disk full")

    store.save_documents = boom  # type: ignore[method-assign]
    service, _ = _service(
        store,
        open_windows=lambda: (window,),
        status_service=status_service,
    )

    assert service.snapshot_now() is False  # must not raise; reports the failure
    status_service.set_autosave_error.assert_called_once_with(
        window, "Autosave paused: disk full"
    )


def test_snapshot_error_publication_tolerates_a_destroyed_qt_window():
    store = _FakeStore(RestoreResult())
    window = _FakeWindow("destroyed")
    status_service = mock.Mock()
    status_service.set_autosave_error.side_effect = RuntimeError(
        "wrapped C/C++ object has been deleted"
    )
    service, _ = _service(
        store,
        open_windows=lambda: (window,),
        status_service=status_service,
    )

    service._set_snapshot_error("Autosave paused: disk full")

    status_service.set_autosave_error.assert_called_once_with(
        window, "Autosave paused: disk full"
    )


def test_snapshot_error_publication_does_not_hide_wiring_errors():
    store = _FakeStore(RestoreResult())
    window = _FakeWindow("broken")
    status_service = mock.Mock()
    status_service.set_autosave_error.side_effect = RuntimeError(
        "status bar must be initialized before autosave status"
    )
    service, _ = _service(
        store,
        open_windows=lambda: (window,),
        status_service=status_service,
    )

    with pytest.raises(RuntimeError, match="status bar must be initialized"):
        service._set_snapshot_error("Autosave paused: disk full")


def test_successful_retry_clears_the_persistent_snapshot_error():
    store = _FakeStore(RestoreResult())
    window = _FakeWindow("first")
    status_service = mock.Mock()
    attempts = 0

    def current_documents():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AutosaveSnapshotError("Canvas 1: stale calculation plan")
        return ["doc"]

    service, _ = _service(
        store,
        current_documents=current_documents,
        open_windows=lambda: (window,),
        status_service=status_service,
    )

    assert service.snapshot_now() is False
    assert store.saved == []
    assert service.snapshot_now() is True

    assert store.saved == [["doc"]]
    assert status_service.set_autosave_error.call_args_list == [
        mock.call(window, "Autosave paused: Canvas 1: stale calculation plan"),
        mock.call(window, None),
    ]


def test_start_keeps_source_sessions_when_the_snapshot_fails(qapp):
    store = _FakeStore(RestoreResult(prune_ids=["old-1"]))

    def boom(_docs):
        raise RuntimeError("disk full")

    store.save_documents = boom  # type: ignore[method-assign]
    service, _ = _service(store, current_documents=lambda: ["doc"])
    fake_app = SimpleNamespace(aboutToQuit=_FakeSignal())

    service.restore_previous(_FakeWindow("first"))
    service.start(fake_app)

    assert store.pruned == []  # a failed re-snapshot must not delete the sources
    assert service._timer is not None
    service._timer.stop()


def test_start_begins_session_snapshots_and_arms_hooks(qapp):
    store = _FakeStore(RestoreResult())
    service, _ = _service(store, current_documents=lambda: ["doc"])
    fake_app = SimpleNamespace(aboutToQuit=_FakeSignal())

    service.start(fake_app)

    assert store.begun is True
    assert store.saved == [["doc"]]  # immediate snapshot after begin
    assert service._timer is not None and service._timer.isActive()
    assert fake_app.aboutToQuit.slots == [service._on_about_to_quit]
    service._timer.stop()


def test_production_qobject_owns_the_autosave_timer(qapp):
    store = _FakeStore(RestoreResult())
    service, _ = _service(store, current_documents=list)

    service.start(qapp)

    assert service._timer is not None
    assert service._timer.parent() is qapp
    service._timer.stop()


def test_last_window_close_marks_quitting_before_deferred_snapshot() -> None:
    script = textwrap.dedent(
        """
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtWidgets import QApplication, QWidget
        import weakref

        from chemvas.features.session import is_quitting, snapshot_unless_quitting
        from chemvas.ui.session_recovery_service import SessionRecoveryService

        class Store:
            def __init__(self):
                self.saves = 0
                self.clean_exit = False

            def begin(self):
                pass

            def save_documents(self, _docs):
                self.saves += 1

            def mark_clean_exit(self):
                self.clean_exit = True

        class ClosingWindow(QWidget):
            def closeEvent(self, event):
                events.append("close")
                QTimer.singleShot(0, deferred_snapshot)
                super().closeEvent(event)

        def deferred_snapshot():
            events.append(f"snapshot:{is_quitting()}")
            snapshot_unless_quitting()

        app = QApplication([])
        app_reference = weakref.ref(app)
        store = Store()
        events = []
        service = SessionRecoveryService(
            store,
            open_windows=tuple,
            current_documents=list,
        )
        service.start(app)
        window = ClosingWindow()
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        app.lastWindowClosed.connect(
            lambda: events.append(f"last:{is_quitting()}")
        )
        app.aboutToQuit.connect(
            lambda: events.append(f"about:{is_quitting()}")
        )
        window.show()
        QTimer.singleShot(0, window.close)
        exit_code = app.exec()
        print(events, store.saves, store.clean_exit, exit_code)
        assert "last:True" in events
        assert store.saves == 1
        assert store.clean_exit
        assert exit_code == 0
        del app
        assert app_reference() is None
        """
    )
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_consumed_sessions_are_pruned_only_after_resnapshot(qapp):
    # A crash mid-restore must not destroy the recovered work: the old source
    # sessions are deleted only after start() snapshots them into the new one.
    store = _FakeStore(RestoreResult(prune_ids=["old-1", "old-2"]))
    service, _ = _service(store, current_documents=lambda: ["doc"])
    fake_app = SimpleNamespace(aboutToQuit=_FakeSignal())

    service.restore_previous(_FakeWindow("first"))  # captures the deferred prune list
    assert store.pruned == []  # nothing deleted yet

    service.start(fake_app)

    assert store.pruned == [["old-1", "old-2"]]
    assert store.events.index("save") < store.events.index(
        "prune"
    )  # snapshot, then prune
    service._timer.stop()


def test_consumed_sessions_are_pruned_after_a_successful_retry(qapp):
    store = _FakeStore(RestoreResult(prune_ids=["old-1"]))
    attempts = 0

    def save_documents(docs):
        nonlocal attempts
        attempts += 1
        store.events.append("save")
        if attempts == 1:
            raise RuntimeError("disk full")
        store.saved.append(docs)

    store.save_documents = save_documents  # type: ignore[method-assign]
    service, _ = _service(store, current_documents=lambda: ["doc"])
    fake_app = SimpleNamespace(aboutToQuit=_FakeSignal())

    service.restore_previous(_FakeWindow("first"))
    service.start(fake_app)
    assert store.pruned == []

    assert service.snapshot_now() is True
    assert store.pruned == [["old-1"]]
    assert store.events[-2:] == ["save", "prune"]
    service._timer.stop()


def test_about_to_quit_marks_the_session_clean():
    store = _FakeStore(RestoreResult())
    service, _ = _service(store)

    service._on_about_to_quit()

    assert store.clean_exit is True


def test_about_to_quit_sets_the_quitting_flag():
    from chemvas.features.session import autosave as session_autosave_hook

    session_autosave_hook.reset_quitting()
    store = _FakeStore(RestoreResult())
    service, _ = _service(store)

    service._on_about_to_quit()

    # So deferred window-close snapshots become no-ops and the open set is kept.
    assert session_autosave_hook.is_quitting() is True
