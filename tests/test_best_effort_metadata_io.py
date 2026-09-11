from __future__ import annotations

import hashlib
import json
import os
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.window_registry import open_new_window, open_windows
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state
from chemvas.features.session import DocDescriptor
from chemvas.ui import recent_documents_store
from chemvas.ui.canvas_document_metadata_state import (
    document_file_path_for,
    document_source_sha256_for,
)
from chemvas.ui.canvas_window_access import (
    history_service_for_canvas,
    snapshot_canvas_state_for,
)
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.session_snapshot_store import OWNER_NAME, SessionSnapshotStore
from chemvas.ui.structure_mutation_access import add_bond_between_points_for

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX hard-link identity")


@pytest.fixture(scope="module")
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _state():
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [{"id": 0, "element": "O", "x": 0, "y": 0}],
            "bonds": [],
        }
    )


@pytest.mark.parametrize(
    "operation", ["save_as", "save_existing", "already_open", "save_user_hardlink"]
)
def test_hardlinked_recents_cannot_break_document_operations(
    tmp_path, monkeypatch, application, operation
):
    source = tmp_path / "source.chemvas"
    write_document(source, _state(), CANVAS_FILE_VERSION)
    original_bytes = source.read_bytes()
    recent = tmp_path / "recent.json"
    monkeypatch.setattr(recent_documents_store, "recent_documents_file", lambda: recent)
    window = open_new_window()
    services = services_for_window(window)
    actions = services.document_action_service
    try:
        assert actions.load_canvas_from_path(window, str(source))
        canvas = active_canvas_for_window(window)
        history = history_service_for_canvas(canvas)
        # Keep both undo and redo history live; opening an already-open path
        # must activate, never reload, even though its recent-list write fails.
        add_bond_between_points_for(canvas, QPointF(100, 0), QPointF(140, 0))
        add_bond_between_points_for(canvas, QPointF(100, 80), QPointF(140, 80))
        history.undo()
        stack = history.capture_stack_snapshot()
        assert stack.history and stack.redo_stack
        state = snapshot_canvas_state_for(canvas)
        assert services.canvas_document_service.is_dirty(canvas)
        source_digest = document_source_sha256_for(canvas)
        backup = tmp_path / "recent-backup.json"
        os.link(recent, backup)
        recent_bytes = recent.read_bytes()
        if operation == "save_user_hardlink":
            os.link(source, tmp_path / "source-backup.chemvas")
        warning = Mock()
        error = None
        result = None
        destination = (
            tmp_path / "saved-as.chemvas" if operation == "save_as" else source
        )
        try:
            if operation == "already_open":
                result = actions.load_canvas_from_path(
                    window, str(source), message_box=warning
                )
            else:
                result = actions.save_canvas_to_path(
                    window, str(destination), message_box=warning
                )
        except Exception as exc:
            error = exc

        assert recent.read_bytes() == backup.read_bytes() == recent_bytes
        assert os.path.samefile(recent, backup)
        assert snapshot_canvas_state_for(canvas) == state
        history.verify_stack_snapshot(stack)
        assert open_windows() == (window,)
        assert active_canvas_for_window(window) is canvas
        assert document_file_path_for(canvas) == str(destination)
        if operation == "save_user_hardlink":
            warning.warning.assert_called_once()
            assert "hard-link" in warning.warning.call_args.args[2]
            assert os.path.samefile(source, tmp_path / "source-backup.chemvas")
        else:
            warning.warning.assert_not_called()
        if operation in {"already_open", "save_user_hardlink"}:
            assert source.read_bytes() == original_bytes
            assert document_source_sha256_for(canvas) == source_digest
            assert services.canvas_document_service.is_dirty(canvas)
        else:
            assert read_document(destination).state == json.loads(json.dumps(state))
            assert (
                document_source_sha256_for(canvas)
                == hashlib.sha256(destination.read_bytes()).hexdigest()
            )
            assert not services.canvas_document_service.is_dirty(canvas)
            if operation == "save_as":
                assert source.read_bytes() == original_bytes
        # The old ValueError occurs after real Save already writes/marks clean.
        assert error is None, f"operation partially completed then raised: {error!r}"
        assert result is (operation != "save_user_hardlink")
        if operation not in {"already_open", "save_user_hardlink"}:
            assert window.statusBar().currentMessage() == f"Saved: {destination}"
    finally:
        for canvas in window.tab_references.all_canvases():
            services.canvas_document_service.mark_clean(canvas)
        window.close()
        application.processEvents()
        QTest.qWait(10)


@pytest.mark.parametrize("operation", ["save", "record", "clear"])
def test_recent_store_preserves_hardlinked_metadata_as_best_effort(tmp_path, operation):
    source = tmp_path / "source.chemvas"
    source.write_bytes(b"synthetic")
    recent = tmp_path / "recent.json"
    recent.write_text('{"version":1,"paths":[]}', encoding="utf-8")
    backup = tmp_path / "backup.json"
    os.link(recent, backup)
    before = recent.read_bytes()
    if operation == "save":
        recent_documents_store.save_recent([str(source)], path=recent)
    elif operation == "record":
        assert recent_documents_store.record_recent(str(source), path=recent) == [
            str(source)
        ]
    else:
        recent_documents_store.clear_recent(path=recent)
    assert recent.read_bytes() == backup.read_bytes() == before
    assert os.path.samefile(recent, backup)
    assert set(tmp_path.iterdir()) == {source, recent, backup}


def test_hardlinked_owner_sidecar_does_not_fail_committed_session_snapshot(tmp_path):
    store = SessionSnapshotStore(
        tmp_path,
        session_id="synthetic-session",
        pid=4242,
        process_identity="synthetic-owner",
    )
    store.begin()
    owner = store.session_dir / OWNER_NAME
    backup = tmp_path / "owner-backup.json"
    os.link(owner, backup)
    before = owner.read_bytes()
    store.save_documents([DocDescriptor(_state(), None, "Synthetic unsaved", True)])
    assert owner.read_bytes() == backup.read_bytes() == before
    assert os.path.samefile(owner, backup)
    manifest = json.loads((store.session_dir / "session.json").read_text())
    assert len(manifest["docs"]) == 1
    entry = manifest["docs"][0]
    assert entry["dirty"] is True
    assert read_document(store.session_dir / entry["snapshot"]).state == json.loads(
        json.dumps(_state())
    )
    assert not list(store.session_dir.glob(".chemvas-*"))
