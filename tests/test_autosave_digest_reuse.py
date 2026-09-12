"""Reuse one freshly collected snapshot digest, never a history revision."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.ui import canvas_document_metadata_state as metadata
from chemvas.ui import session_recovery_service as recovery
from chemvas.ui import session_snapshot_store as snapshots
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def drawing(app, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    canvas = build_canvas_view()
    window = SimpleNamespace(
        tab_references=SimpleNamespace(all_canvases=lambda: [canvas])
    )
    monkeypatch.setattr(recovery, "default_open_windows", lambda: [window])
    metadata.set_document_file_path_for(canvas, str(tmp_path / "source.chemvas"))
    metadata.mark_document_clean_for(canvas, snapshot_canvas_state_for(canvas))
    metadata.set_document_source_sha256_for(canvas, "source-file-byte-hash")
    store = snapshots.SessionSnapshotStore(
        tmp_path / "sessions", session_id="current", pid=123, process_identity="test"
    )
    store.begin()
    yield canvas, store
    canvas.services.document.canvas_scene_reset_service.clear_scene()
    canvas.close()


def _digests(monkeypatch):
    digest = Mock(wraps=metadata.canonical_document_digest)
    monkeypatch.setattr(metadata, "canonical_document_digest", digest)
    monkeypatch.setattr(snapshots, "canonical_document_digest", digest)
    return digest


def _files(store):
    return {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in store.session_dir.iterdir()
    }


def _persisted_state(store):
    manifest = json.loads((store.session_dir / "session.json").read_bytes())
    return json.loads(
        (store.session_dir / manifest["docs"][0]["snapshot"]).read_bytes()
    )["state"]


@pytest.mark.parametrize("status", ["clean", "dirty", "recovered"])
def test_fresh_collection_hashes_at_most_once_and_idle_files_are_unchanged(
    drawing, monkeypatch, status
):
    canvas, store = drawing
    if status == "dirty":
        canvas.runtime_state.tool_settings_state.arrow_line_width = 2.5
    elif status == "recovered":
        metadata.mark_document_dirty_for(canvas)
    digest = _digests(monkeypatch)
    for _ in range(3):
        digest.reset_mock()
        docs = recovery.collect_open_documents()
        expected = deepcopy(docs[0].state)
        store.save_documents(docs)
        assert digest.call_count == 1
        assert docs[0].state == expected
        assert docs[0].dirty is (status != "clean")
        if status != "clean":
            assert _persisted_state(store) == expected
        if _ == 0:
            before = _files(store)
        else:
            assert _files(store) == before
    assert metadata.document_source_sha256_for(canvas) == "source-file-byte-hash"


@pytest.mark.parametrize("phase", ["snapshot", "manifest", "prune"])
def test_same_snapshot_digest_keeps_failed_write_retry_and_later_edits(
    drawing, monkeypatch, phase
):
    canvas, store = drawing
    store.save_documents(recovery.collect_open_documents())
    previous = (store.session_dir / "session.json").read_bytes()
    canvas.runtime_state.tool_settings_state.arrow_line_width = 3.25
    expected = snapshot_canvas_state_for(canvas)
    method = {
        "snapshot": "_write_snapshot",
        "manifest": "_write_manifest",
        "prune": "_prune_snapshots",
    }[phase]
    digest = _digests(monkeypatch)
    docs = recovery.collect_open_documents()
    with monkeypatch.context() as failure:
        failure.setattr(
            store, method, Mock(side_effect=OSError("synthetic write failure"))
        )
        with pytest.raises(OSError, match="synthetic write failure"):
            store.save_documents(docs)
    assert digest.call_count == 1
    if phase != "prune":
        assert (store.session_dir / "session.json").read_bytes() == previous
    digest.reset_mock()
    store.save_documents(docs)
    assert digest.call_count == 0
    assert _persisted_state(store) == expected

    canvas.runtime_state.tool_settings_state.arrow_line_width = 4.25
    store.save_documents(recovery.collect_open_documents())
    assert _persisted_state(store)["settings"]["arrow_line_width"] == 4.25
    metadata.mark_document_clean_for(canvas, snapshot_canvas_state_for(canvas))
    clean = recovery.collect_open_documents()
    assert not clean[0].dirty
    store.save_documents(clean)
    assert not list(store.session_dir.glob("doc-*.json"))


def test_warning_snapshot_remains_rejected_before_digest_or_store(drawing, monkeypatch):
    _canvas, store = drawing
    before = _files(store)
    digest = _digests(monkeypatch)
    monkeypatch.setattr(
        recovery,
        "snapshot_canvas_state_with_warnings_for",
        lambda _canvas: ({}, ["incomplete snapshot"]),
    )
    with pytest.raises(recovery.AutosaveSnapshotError, match="incomplete snapshot"):
        store.save_documents(recovery.collect_open_documents())
    digest.assert_not_called()
    assert _files(store) == before


def test_pending_note_text_without_drawing_history_is_recollected(drawing, monkeypatch):
    canvas, store = drawing
    note = canvas.services.interaction.note_controller.create_text_note(
        QPointF(10, 20), "Saved text"
    )
    saved_html = note.toHtml()
    metadata.mark_document_clean_for(canvas, snapshot_canvas_state_for(canvas))
    history = canvas.services.history_service.capture_stack_snapshot()
    digest = _digests(monkeypatch)
    for text in ("Pending text", "Pending text changed again"):
        note.setPlainText(text)
        digest.reset_mock()
        docs = recovery.collect_open_documents()
        store.save_documents(docs)
        assert digest.call_count == 1
        assert docs[0].dirty
        assert _persisted_state(store)["notes"][0]["text"] == text
        canvas.services.history_service.verify_stack_snapshot(history)
    note.setHtml(saved_html)
    assert not recovery.collect_open_documents()[0].dirty


def test_graph_edit_undo_redo_and_save_keep_content_based_dirty_state(
    drawing, monkeypatch
):
    canvas, store = drawing
    before = snapshot_canvas_state_for(canvas)
    canvas.services.structure.structure_build_service.add_benzene_ring(
        QPointF(200, 150)
    )
    after = snapshot_canvas_state_for(canvas)
    assert after != before
    digest = _digests(monkeypatch)
    for _ in range(2):
        digest.reset_mock()
        store.save_documents(recovery.collect_open_documents())
        assert digest.call_count == 1
        assert _persisted_state(store) == json.loads(json.dumps(after))
        canvas.services.history_service.undo()
        assert snapshot_canvas_state_for(canvas) == before
        docs = recovery.collect_open_documents()
        assert not docs[0].dirty
        store.save_documents(docs)
        assert not list(store.session_dir.glob("doc-*.json"))
        canvas.services.history_service.redo()
        assert snapshot_canvas_state_for(canvas) == after
    metadata.mark_document_clean_for(canvas, after)
    docs = recovery.collect_open_documents()
    assert not docs[0].dirty
    store.save_documents(docs)
    canvas.services.history_service.undo()
    assert recovery.collect_open_documents()[0].dirty
    canvas.services.history_service.redo()
    assert not recovery.collect_open_documents()[0].dirty
    assert metadata.document_source_sha256_for(canvas) == "source-file-byte-hash"


def test_uninitialized_blank_document_still_never_hashes(drawing, monkeypatch):
    canvas, store = drawing
    metadata.document_metadata_state_for(canvas).clean_digest = None
    metadata.set_document_file_path_for(canvas, None)
    digest = _digests(monkeypatch)
    docs = recovery.collect_open_documents()
    store.save_documents(docs)
    digest.assert_not_called()
    assert not docs[0].dirty
    assert json.loads((store.session_dir / "session.json").read_bytes())["docs"] == []


def test_reused_digest_does_not_bypass_strict_snapshot_write(drawing, monkeypatch):
    canvas, store = drawing
    before = _files(store)
    invalid = snapshot_canvas_state_for(canvas)
    invalid["settings"]["arrow_line_width"] = -1
    digest = _digests(monkeypatch)
    with monkeypatch.context() as invalid_snapshot:
        invalid_snapshot.setattr(
            recovery,
            "snapshot_canvas_state_with_warnings_for",
            lambda _canvas: (invalid, []),
        )
        docs = recovery.collect_open_documents()
        assert docs[0].dirty
        with pytest.raises(ValueError):
            store.save_documents(docs)
    assert digest.call_count == 1
    assert _files(store) == before
    store.save_documents(recovery.collect_open_documents())


def test_collected_snapshot_digest_is_not_a_live_canvas_cache(drawing, monkeypatch):
    canvas, store = drawing
    note = canvas.services.interaction.note_controller.create_text_note(
        QPointF(10, 20), "Collected text"
    )
    digest = _digests(monkeypatch)
    docs = recovery.collect_open_documents()
    collected = deepcopy(docs[0].state)
    note.setPlainText("Later live text")
    assert docs[0].state == collected
    digest.reset_mock()
    store.save_documents(docs)
    assert digest.call_count == 0
    assert _persisted_state(store)["notes"][0]["text"] == "Collected text"
    store.save_documents(recovery.collect_open_documents())
    assert digest.call_count == 1
    assert _persisted_state(store)["notes"][0]["text"] == "Later live text"
