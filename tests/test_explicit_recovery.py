"""Recovery publishes copies before retiring the last on-disk source."""

import json
from unittest import mock

import pytest
from PyQt6.QtWidgets import QMessageBox

from chemvas.bootstrap.window_registry import open_new_window
from chemvas.core.document_io import write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.session import DocDescriptor, RestoredDoc
from chemvas.shell.window_registry import forget_window, open_windows
from chemvas.ui.session import session_snapshot_store as store_module
from chemvas.ui.session.session_recovery_service import SessionRecoveryService
from chemvas.ui.session.session_snapshot_store import (
    RestoreResult,
    SessionSnapshotStore,
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
    store = _FakeStore(RestoreResult(docs=docs, prune_ids=["old"]))
    first, second = _FakeWindow("first"), _FakeWindow("second")
    service, owner = _service(store, extra_windows=[second, second])
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
    assert not store.pruned
    assert not store.saved
    owner.reusable = False
    assert service.restore_previous(first) == 1
    assert len(owner.opened) == 2
    assert len({doc.display_name for doc in owner.opened}) == 2
    assert [doc.state["notes"][0]["text"] for doc in owner.opened] == ["0", "1"]
    assert service.snapshot_now()
    assert store.pruned == [["old"]]


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
            prune_ids=["old"],
        )
    )
    service, owner = _service(store)
    first = _FakeWindow("first")
    assert service.restore_previous(first) == 1
    prune = store.prune_sessions
    with mock.patch.object(store, "prune_sessions", side_effect=OSError("locked")):
        assert not service.snapshot_now()
    assert store.saved and not store.pruned
    store.prune_sessions = prune
    assert service.restore_previous(first) == 0
    assert len(owner.opened) == 1
    assert store.pruned == [["old"]]


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
    assert not result.docs and not result.prune_ids
    assert result.warnings
    assert previous.session_dir.exists()
    assert outside.read_bytes() == outside_bytes


@pytest.mark.parametrize("alternate_root", [False, True])
def test_file_menu_recovers_copy_and_retries_failed_handoff(
    qt_application, tmp_path, monkeypatch, alternate_root
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
        assert recovery.snapshot_now()
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
