"""Recovery publishes copies before retiring the last on-disk source."""

import errno
import json
from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtWidgets import QMessageBox

from chemvas.bootstrap.window_registry import open_new_window
from chemvas.core.document_io import write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.session import DocDescriptor, RestoredDoc, WithheldDoc
from chemvas.shell.window_registry import forget_window, open_windows
from chemvas.ui.session import session_snapshot_store as store_module
from chemvas.ui.session.session_recovery_service import SessionRecoveryService
from chemvas.ui.session.session_snapshot_store import (
    RestoreResult,
    SessionSnapshotStore,
)
from chemvas.ui.window.main_window_canvas_document_service import (
    MainWindowCanvasDocumentService,
)
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from tests.test_session_recovery_service import _FakeStore, _FakeWindow, _service
from tests.test_session_snapshot_store import _valid_state


@pytest.mark.parametrize("same_name", [False, True])
def test_partial_restore_retries_only_unopened_copies_and_never_prunes_early(same_name):
    docs = [
        RestoredDoc(
            _valid_state(str(i)),
            None,
            "Draft" if same_name else f"Copy {i}",
            True,
            recovery_key=f"old/{i}",
        )
        for i in range(2)
    ]
    store = _FakeStore(RestoreResult(docs=docs, release={"old": ("0", "1")}))
    first, second, third = (_FakeWindow(name) for name in ("1", "2", "3"))
    service, owner = _service(store, extra_windows=[second, third])
    original = owner.open_state
    count = 0

    def fail(window, **kwargs):
        nonlocal count
        count += 1
        # Autosave must not make a partly opened batch eligible for deletion.
        assert not service.snapshot_now()
        if count == 2:
            raise RuntimeError("cannot construct second drawing")
        return original(window, **kwargs)

    owner.open_state = fail
    with pytest.raises(RuntimeError, match="second drawing"):
        service.restore_previous(first)
    assert not store.released
    assert not store.saved
    # The window opened for the failed copy closes instead of staying blank.
    assert second.closed and not first.closed
    owner.reusable = False
    assert service.restore_previous(first) == 1
    assert [doc.window for doc in owner.opened] == [first, third]
    assert not third.closed
    names = [doc.display_name for doc in owner.opened]
    assert len(set(names)) == 2
    if not same_name:
        # The failed attempt must not keep the name it claimed for its copy.
        assert names == ["Copy 0", "Copy 1"]
    assert [doc.state["notes"][0]["text"] for doc in owner.opened] == ["0", "1"]
    assert service.snapshot_now()
    assert store.released == [{"old": ("0", "1")}]


def test_clean_exit_removes_discarded_payload_after_manifest_commit(
    tmp_path,
):
    store = SessionSnapshotStore(tmp_path, session_id="old", pid=4242)
    store.begin()
    store.save_documents(
        [DocDescriptor(_valid_state("discarded"), None, "Draft", True)]
    )
    snapshot = next(store.session_dir.glob("doc-*.json"))
    with mock.patch.object(store, "_write_manifest", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            store.mark_clean_exit()
    assert snapshot.exists()
    assert not json.loads((store.session_dir / "session.json").read_bytes())[
        "clean_exit"
    ]
    store.mark_clean_exit()
    assert not snapshot.exists()
    assert json.loads((store.session_dir / "session.json").read_bytes())["docs"] == []


def test_cleanup_failure_retries_without_reopening_copies():
    store = _FakeStore(
        RestoreResult(
            docs=[RestoredDoc(_valid_state(), None, "Draft", True)],
            release={"old": ()},
        )
    )
    first = _FakeWindow("first")
    status = mock.Mock()
    service, owner = _service(
        store, open_windows=lambda: (first,), status_service=status
    )
    with mock.patch.object(store, "release_sessions", side_effect=OSError("locked")):
        assert service.restore_previous(first) == 1
        # The copies are persisted: cleanup is a recovery notice, not autosave.
        assert service.snapshot_now()
    status.set_autosave_error.assert_called_with(first, None)
    assert "locked" in status.set_recovery_notice.call_args.args[1]
    assert store.saved and not store.released
    assert service.restore_previous(first) == 0
    assert len(owner.opened) == 1
    assert store.released == [{"old": ()}]
    status.set_recovery_notice.assert_called_with(first, None)


def test_cleanup_failure_is_painted_ahead_of_recovery_warnings():
    warning = "Could not recover unsaved edits for Bad. Recovery files are kept."
    store = _FakeStore(
        RestoreResult(
            docs=[RestoredDoc(_valid_state(), None, "Good", True)],
            release={"old": ("doc-1-0.json",)},
            warnings=[warning],
        )
    )
    first = _FakeWindow("first")
    status = mock.Mock()
    service, _owner = _service(
        store, open_windows=lambda: (first,), status_service=status
    )
    with mock.patch.object(store, "release_sessions", side_effect=OSError("locked")):
        assert service.restore_previous(first) == 1

    # The Recover dialog showed the warning; the notice alone reports cleanup.
    notice = status.set_recovery_notice.call_args.args[1]
    assert notice.startswith("Recovery cleanup paused: locked"), notice
    assert warning in notice


@pytest.mark.parametrize("kind", ["relative", "absolute", "symlink"])
def test_recovery_keeps_unsafe_snapshot_references(tmp_path, monkeypatch, kind):
    outside = tmp_path / "outside.chemvas"
    write_document(outside, _valid_state("Outside"), CANVAS_FILE_VERSION)
    outside_bytes = outside.read_bytes()
    root = tmp_path / "sessions"
    previous = SessionSnapshotStore(root, session_id="previous", pid=4242)
    previous.begin()
    previous.save_documents([DocDescriptor(_valid_state(), None, "Draft", True)])
    manifest_path = previous.session_dir / "session.json"
    manifest = json.loads(manifest_path.read_bytes())
    if kind == "symlink":
        snapshot = previous.session_dir / manifest["docs"][0]["snapshot"]
        snapshot.unlink()
        try:
            snapshot.symlink_to(outside)
        except OSError:
            pytest.skip("This host cannot create symbolic links")
    else:
        manifest["docs"][0]["snapshot"] = (
            "../../outside.chemvas" if kind == "relative" else str(outside)
        )
        manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    current = SessionSnapshotStore(root, session_id="current", pid=4243)
    with mock.patch.object(current, "_read_state") as reader:
        result = current.consume_previous_sessions()
    reader.assert_not_called()
    assert not result.docs and not result.release
    assert result.warnings
    assert previous.session_dir.exists()
    assert outside.read_bytes() == outside_bytes


@pytest.mark.parametrize("alternate_root", [False, True])
@pytest.mark.parametrize("retry_via_menu", [False, True])
def test_file_menu_recovers_copy_and_retries_failed_handoff(
    qt_application, tmp_path, monkeypatch, alternate_root, retry_via_menu
):
    previous = SessionSnapshotStore(tmp_path, session_id="crashed", pid=4242)
    previous.begin()
    previous.save_documents(
        [
            DocDescriptor(
                _valid_state("Recovered"), "/original.chemvas", "Original", True
            )
        ]
    )
    previous_stores = [previous]
    recovery_stores = ()
    if alternate_root:
        root = tmp_path / "fallback"
        other = SessionSnapshotStore(root, session_id="crashed", pid=4242)
        other.begin()
        other.save_documents(
            [
                DocDescriptor(
                    _valid_state("Other"), "/original.chemvas", "Original", True
                )
            ]
        )
        previous_stores.append(other)
        recovery_stores = (SessionSnapshotStore(root, session_id="reader", pid=4243),)
    current = SessionSnapshotStore(tmp_path, session_id="current", pid=4243)
    window = open_new_window()
    recovery = SessionRecoveryService(
        current, open_new_window=open_new_window, recovery_stores=recovery_stores
    )
    original_save = current.save_documents
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    try:
        recovery.start(qt_application)
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel
        )
        file_menu = next(
            action.menu()
            for action in window.menuBar().actions()
            if action.text() == "File"
        )
        action = next(
            action
            for action in file_menu.actions()
            if action.text() == "Recover Unsaved Work..."
        )
        action.trigger()
        assert previous.session_dir.exists()
        assert not active_canvas_for_window(window).runtime_state.note_items()
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes
        )
        monkeypatch.setattr(
            current, "save_documents", mock.Mock(side_effect=OSError("disk full"))
        )
        action.trigger()
        canvas = active_canvas_for_window(window)
        assert canvas.runtime_state.document_metadata_state.file_path is None
        assert window.services.canvas_document_service.is_dirty(canvas)
        assert (
            canvas.services.canvas_document_session_service.snapshot_state()["notes"][
                0
            ]["text"]
            == "Recovered"
        )
        assert previous.session_dir.exists()
        count = len(open_windows())
        assert count == len(previous_stores)
        assert all(
            active_canvas_for_window(
                opened
            ).runtime_state.document_metadata_state.file_path
            is None
            for opened in open_windows()
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *a: None)
        action.trigger()
        assert len(open_windows()) == count
        monkeypatch.setattr(current, "save_documents", original_save)
        if retry_via_menu:
            # A handoff retry must not ask to open or create more copies.
            monkeypatch.setattr(
                QMessageBox,
                "question",
                lambda *a: pytest.fail("handoff retry asked to open copies"),
            )
            action.trigger()
        else:
            assert recovery.snapshot_now()
        assert len(open_windows()) == count
        assert all(not store.session_dir.exists() for store in previous_stores)
        manifest = json.loads((current.session_dir / "session.json").read_bytes())
        assert len(manifest["docs"]) == len(previous_stores)
        assert all(
            (current.session_dir / entry["snapshot"]).is_file()
            for entry in manifest["docs"]
        )
        # Recovery notices and Quit errors survive unrelated autosave success.
        status = window.services.status_service
        status.set_recovery_notice(window, "Recovery warning")
        status.set_quit_notice(window, "Quit paused")
        recovery.snapshot_now()
        assert "Recovery warning" in status.autosave_error_label.text()
        assert "Quit paused" in status.autosave_error_label.text()
    finally:
        if recovery._timer is not None:
            recovery._timer.stop()
        qt_application.setProperty("chemvasSessionRecovery", None)
        for opened in tuple(open_windows()):
            opened.services.canvas_document_service.mark_clean(
                active_canvas_for_window(opened)
            )
            forget_window(opened)
            opened.close()
        qt_application.processEvents()


def _crashed_session(root, *docs):
    previous = SessionSnapshotStore(root, session_id="crashed", pid=4242)
    previous.begin()
    previous.save_documents(
        [DocDescriptor(_valid_state(name), None, name, True) for name in docs]
    )
    return previous


def test_failed_copy_leaves_no_blank_window_for_the_retry(
    qt_application, tmp_path, monkeypatch
):
    _crashed_session(tmp_path, "Draft A", "Draft B")
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    open_state = MainWindowCanvasDocumentService.open_state
    calls = 0

    def open_once_failing(service, window, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("transient open failure")
        return open_state(service, window, **kwargs)

    monkeypatch.setattr(
        MainWindowCanvasDocumentService, "open_state", open_once_failing
    )
    window = open_new_window()
    recovery = SessionRecoveryService(
        SessionSnapshotStore(tmp_path, session_id="current", pid=4243),
        open_new_window=open_new_window,
    )
    try:
        recovery.start(SimpleNamespace())
        with pytest.raises(RuntimeError, match="transient open failure"):
            recovery.restore_previous(window)
        qt_application.processEvents()
        assert open_windows() == (window,)

        assert recovery.restore_previous(window) == 1

        assert [
            active_canvas_for_window(
                opened
            ).runtime_state.document_metadata_state.display_name
            for opened in open_windows()
        ] == ["Draft A", "Draft B"]
    finally:
        _close_windows(qt_application, recovery)


def _close_windows(qt_application, recovery):
    if recovery._timer is not None:
        recovery._timer.stop()
    for opened in tuple(open_windows()):
        opened.services.canvas_document_service.mark_clean(
            active_canvas_for_window(opened)
        )
        forget_window(opened)
        opened.close()
    qt_application.processEvents()


def test_recovered_untitled_copy_never_shares_an_open_document_name(
    qt_application, tmp_path, monkeypatch
):
    _crashed_session(tmp_path, "Canvas 1")
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    window = open_new_window()
    recovery = SessionRecoveryService(
        SessionSnapshotStore(tmp_path, session_id="current", pid=4243),
        open_new_window=open_new_window,
    )
    try:
        live = active_canvas_for_window(window)
        live.services.canvas_document_session_service.apply_state(
            _valid_state("live work")
        )
        window.services.canvas_document_service.mark_dirty(live)
        recovery.start(SimpleNamespace())

        assert recovery.restore_previous(window) == 1

        names = [
            active_canvas_for_window(
                opened
            ).runtime_state.document_metadata_state.display_name
            for opened in open_windows()
        ]
        assert len(open_windows()) == 2
        assert len(set(names)) == 2, names
        assert len({opened.windowTitle() for opened in open_windows()}) == 2
    finally:
        _close_windows(qt_application, recovery)


def test_copy_that_replaces_the_blank_canvas_keeps_its_name(
    qt_application, tmp_path, monkeypatch
):
    _crashed_session(tmp_path, "Canvas 1")
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    window = open_new_window()
    recovery = SessionRecoveryService(
        SessionSnapshotStore(tmp_path, session_id="current", pid=4243),
        open_new_window=open_new_window,
    )
    try:
        recovery.start(SimpleNamespace())
        blank = active_canvas_for_window(window)
        assert blank.runtime_state.document_metadata_state.display_name == "Canvas 1"

        assert recovery.restore_previous(window) == 1

        assert open_windows() == (window,)
        copy = active_canvas_for_window(window)
        assert copy.runtime_state.document_metadata_state.display_name == "Canvas 1"
    finally:
        _close_windows(qt_application, recovery)


def test_copy_whose_window_fails_to_open_keeps_its_name_for_the_retry():
    docs = [
        RestoredDoc(_valid_state(str(i)), None, f"Copy {i}", True, f"old/{i}")
        for i in range(2)
    ]
    store = _FakeStore(RestoreResult(docs=docs, release={"old": ("0", "1")}))
    first, second = _FakeWindow("1"), _FakeWindow("2")
    service, owner = _service(store)
    service._open_new_window = mock.Mock(
        side_effect=[RuntimeError("no window"), second]
    )
    with pytest.raises(RuntimeError, match="no window"):
        service.restore_previous(first)
    owner.reusable = False

    assert service.restore_previous(first) == 1

    assert [doc.display_name for doc in owner.opened] == ["Copy 0", "Copy 1"]
    assert [doc.window for doc in owner.opened] == [first, second]


def _handoff_service(current, first, withheld=()):
    """A started-state service whose snapshots persist the copies it opened."""
    status = mock.Mock()
    owner = None
    service, owner = _service(
        current,
        open_windows=lambda: (first,),
        status_service=status,
        current_documents=lambda: [
            *withheld,
            *(
                DocDescriptor(copy.state, None, copy.display_name, True)
                for copy in owner.opened
            ),
        ],
    )
    current.begin()
    return service, owner, status


def test_recovered_copy_is_not_offered_again_beside_an_unreadable_one(
    tmp_path, monkeypatch
):
    previous = _crashed_session(tmp_path, "Good", "Bad")
    manifest = json.loads((previous.session_dir / "session.json").read_bytes())
    unreadable = previous.session_dir / manifest["docs"][1]["snapshot"]
    unreadable.write_text("{corrupt")
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    first = _FakeWindow("first")
    current = SessionSnapshotStore(tmp_path, session_id="current", pid=4243)
    service, owner, status = _handoff_service(current, first)

    assert service.restore_previous(first) == 1

    assert [copy.display_name for copy in owner.opened] == ["Good"]
    # The user saves or discards the copy and quits; a later launch recovers.
    current.mark_clean_exit()
    later = SessionSnapshotStore(tmp_path, session_id="later", pid=4244)
    result = later.consume_previous_sessions()
    assert result.docs == []
    assert "Bad" in " ".join(result.warnings)
    assert unreadable.read_text() == "{corrupt"
    assert later.unrestored_snapshot_directories() == [previous.session_dir]


def test_recovered_originals_stay_while_autosave_withholds_a_drawing(
    tmp_path, monkeypatch
):
    previous = _crashed_session(tmp_path, "Draft")
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    first = _FakeWindow("first")
    current = SessionSnapshotStore(tmp_path, session_id="current", pid=4243)
    withheld = [WithheldDoc(key="stale", display_name="Stale", reason="Plan is stale.")]
    service, owner, status = _handoff_service(current, first, withheld)

    assert service.restore_previous(first) == 1

    # A withheld drawing could be a recovered copy, so no original is released.
    assert previous.session_dir.exists()
    assert "Autosave skipped Stale" in status.set_autosave_error.call_args.args[1]
    withheld.clear()
    assert service.snapshot_now()
    assert not previous.session_dir.exists()
    status.set_autosave_error.assert_called_with(first, None)


def test_unrecognized_file_keeps_its_session_without_blocking_cleanup(
    tmp_path, monkeypatch
):
    previous = _crashed_session(tmp_path, "Draft")
    finder = previous.session_dir / ".DS_Store"
    finder.write_bytes(b"finder")
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    first = _FakeWindow("first")
    current = SessionSnapshotStore(tmp_path, session_id="current", pid=4243)
    service, owner, status = _handoff_service(current, first)

    assert service.restore_previous(first) == 1
    assert service.snapshot_now()

    status.set_autosave_error.assert_called_with(first, None)
    status.set_recovery_notice.assert_called_with(first, None)
    assert finder.read_bytes() == b"finder"
    assert not list(previous.session_dir.glob("doc-*.json"))
    current.mark_clean_exit()
    later = SessionSnapshotStore(tmp_path, session_id="later", pid=4244)
    assert later.consume_previous_sessions().docs == []
    assert later.unrestored_snapshot_directories() == []


def test_staging_file_of_a_killed_write_is_released_with_its_session(
    tmp_path, monkeypatch
):
    previous = _crashed_session(tmp_path, "Draft")
    # A process killed inside the atomic writer leaves its staging file.
    (previous.session_dir / ".chemvas-abc123.tmp").write_text("{partial")
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    first = _FakeWindow("first")
    current = SessionSnapshotStore(tmp_path, session_id="current", pid=4243)
    service, owner, status = _handoff_service(current, first)

    assert service.restore_previous(first) == 1

    status.set_recovery_notice.assert_called_with(first, None)
    assert not previous.session_dir.exists()


def test_interrupted_release_finishes_on_the_next_snapshot(tmp_path, monkeypatch):
    previous = _crashed_session(tmp_path, "Draft")
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    first = _FakeWindow("first")
    current = SessionSnapshotStore(tmp_path, session_id="current", pid=4243)
    service, owner, status = _handoff_service(current, first)
    rmdir = store_module.Path.rmdir
    calls = 0

    def busy_once(path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.ENOTEMPTY, "Directory not empty", str(path))
        return rmdir(path)

    monkeypatch.setattr(store_module.Path, "rmdir", busy_once)
    assert service.restore_previous(first) == 1
    assert "Recovery cleanup paused" in status.set_recovery_notice.call_args.args[1]

    assert service.snapshot_now()

    status.set_recovery_notice.assert_called_with(first, None)
    assert not previous.session_dir.exists()


def test_file_that_appears_during_release_does_not_pause_cleanup(tmp_path, monkeypatch):
    previous = _crashed_session(tmp_path, "Draft")
    finder = previous.session_dir / ".DS_Store"
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    first = _FakeWindow("first")
    current = SessionSnapshotStore(tmp_path, session_id="current", pid=4243)
    service, owner, status = _handoff_service(current, first)
    rmdir = store_module.Path.rmdir

    def finder_writes_first(path):
        # Finder writes into the folder after the removal emptied it.
        monkeypatch.setattr(store_module.Path, "rmdir", rmdir)
        finder.write_bytes(b"finder")
        return rmdir(path)

    monkeypatch.setattr(store_module.Path, "rmdir", finder_writes_first)
    assert service.restore_previous(first) == 1
    assert "Recovery cleanup paused" in status.set_recovery_notice.call_args.args[1]

    assert service.snapshot_now()

    status.set_recovery_notice.assert_called_with(first, None)
    assert list(previous.session_dir.iterdir()) == [finder]
    assert finder.read_bytes() == b"finder"
