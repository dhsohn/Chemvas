from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication
from ui.session_recovery_service import SessionRecoveryService
from ui.session_snapshot_logic import RestoredDoc
from ui.session_snapshot_store import RestoreResult


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
        canvas = SimpleNamespace(window=window, state=state, file_path=file_path, display_name=display_name)
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
        self.include_clean_session: bool | None = None
        self.events: list[str] = []

    def consume_previous_sessions(self, *, include_clean_session: bool = True) -> RestoreResult:
        self.include_clean_session = include_clean_session
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


def _service(store, *, extra_windows=None, current_documents=lambda: []):
    doc_service = _FakeDocService()
    services = SimpleNamespace(canvas_document_service=doc_service)
    spawned = list(extra_windows or [])
    service = SessionRecoveryService(
        store,
        open_new_window=lambda reference: spawned.pop(0),
        services_for_window=lambda window: services,
        current_documents=current_documents,
    )
    return service, doc_service


def test_restore_previous_rebuilds_windows_and_marks_recovered_dirty():
    first = _FakeWindow("first")
    second = _FakeWindow("second")
    result = RestoreResult(
        docs=[
            RestoredDoc(state={"m": 1}, file_path=None, display_name="Canvas 1", dirty=True),
            RestoredDoc(state={"m": 2}, file_path="/a/x.chemvas", display_name="x.chemvas", dirty=False),
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
            RestoredDoc(state={"m": 1}, file_path="/a.chemvas", display_name="a", dirty=False),
            RestoredDoc(state={"m": 2}, file_path="/b.chemvas", display_name="b", dirty=False),
        ]
    )
    service, doc_service = _service(_FakeStore(result), extra_windows=list(spawned))
    doc_service.reusable = False  # first window already holds a document

    service.restore_previous(first)

    assert [canvas.window for canvas in doc_service.opened] == spawned  # never `first`


def test_restore_previous_forwards_include_clean_session():
    store = _FakeStore(RestoreResult())
    service, _ = _service(store)

    service.restore_previous(_FakeWindow("first"), include_clean_session=False)

    assert store.include_clean_session is False


def test_restore_previous_is_silent_when_nothing_to_recover():
    first = _FakeWindow("first")
    service, doc_service = _service(_FakeStore(RestoreResult()))

    assert service.restore_previous(first) == 0
    assert doc_service.opened == []
    assert first.statusBar().messages == []


def test_snapshot_now_persists_the_current_documents():
    sentinel = [object()]
    service, _ = _service(_FakeStore(RestoreResult()), current_documents=lambda: sentinel)

    service.snapshot_now()

    assert service._store.saved == [sentinel]


def test_snapshot_now_swallows_store_errors():
    store = _FakeStore(RestoreResult())

    def boom(_docs):
        raise RuntimeError("disk full")

    store.save_documents = boom  # type: ignore[method-assign]
    service, _ = _service(store)

    service.snapshot_now()  # must not raise


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
    assert store.events.index("save") < store.events.index("prune")  # snapshot, then prune
    service._timer.stop()


def test_about_to_quit_marks_the_session_clean():
    store = _FakeStore(RestoreResult())
    service, _ = _service(store)

    service._on_about_to_quit()

    assert store.clean_exit is True
