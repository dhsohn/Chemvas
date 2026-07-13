from __future__ import annotations

import json

from core.document_io import write_document
from core.document_state import CANVAS_FILE_VERSION, serialize_settings
from ui import session_snapshot_store
from ui.session_snapshot_logic import DocDescriptor
from ui.session_snapshot_store import SessionSnapshotStore


def _valid_state(marker: str | None = None) -> dict:
    return {
        "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=18.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=600,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": marker,
    }


def _store(root, name, *, pid=4242):
    return SessionSnapshotStore(root, session_id=name, pid=pid)


def _dead_pids(monkeypatch):
    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda pid: False)


def test_crash_restore_round_trips_unsaved_work(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=111)
    prev.begin()
    prev.save_documents([DocDescriptor(state=_valid_state("scratch"), file_path=None, display_name="Canvas 1", dirty=True)])

    _dead_pids(monkeypatch)  # the previous instance is gone → a crash
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 1
    assert len(result.docs) == 1
    restored = result.docs[0]
    assert restored.dirty is True
    assert restored.file_path is None
    assert restored.state is not None
    assert restored.state["last_smiles_input"] == "scratch"
    assert not (root / "prev").exists()  # consumed


def test_clean_exit_reopens_saved_files_from_disk(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    saved = tmp_path / "molecule.chemvas"
    write_document(saved, _valid_state("on-disk"), CANVAS_FILE_VERSION)

    prev = _store(root, "prev", pid=222)
    prev.begin()
    prev.save_documents([DocDescriptor(state=_valid_state("on-disk"), file_path=str(saved), display_name="molecule.chemvas", dirty=False)])
    prev.mark_clean_exit()

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 0
    assert [d.file_path for d in result.docs] == [str(saved)]
    assert result.docs[0].dirty is False
    assert result.docs[0].state is not None


def test_clean_exit_drops_unsaved_untitled_docs(tmp_path, monkeypatch):
    # An untitled dirty doc present at a clean exit was already resolved by the
    # close prompt (saved or discarded), so it must NOT come back.
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=333)
    prev.begin()
    prev.save_documents([DocDescriptor(state=_valid_state(), file_path=None, display_name="Canvas 1", dirty=True)])
    prev.mark_clean_exit()

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []


def test_live_instance_session_is_left_untouched(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=444)
    prev.begin()
    prev.save_documents([DocDescriptor(state=_valid_state("live"), file_path=None, display_name="Canvas 1", dirty=True)])

    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda pid: True)  # still running
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert (root / "prev").exists()  # not pruned


def test_clean_saved_doc_is_recorded_without_a_snapshot(tmp_path):
    root = tmp_path / "sessions"
    saved = tmp_path / "x.chemvas"
    write_document(saved, _valid_state(), CANVAS_FILE_VERSION)
    store = _store(root, "cur")
    store.begin()

    store.save_documents([DocDescriptor(state=_valid_state(), file_path=str(saved), display_name="x.chemvas", dirty=False)])

    assert list((root / "cur").glob("doc-*.json")) == []
    manifest = json.loads((root / "cur" / "session.json").read_text())
    assert manifest["docs"][0]["snapshot"] is None
    assert manifest["docs"][0]["file_path"] == str(saved)


def test_pristine_untitled_canvas_is_not_persisted(tmp_path):
    root = tmp_path / "sessions"
    store = _store(root, "cur")
    store.begin()

    store.save_documents([DocDescriptor(state=_valid_state(), file_path=None, display_name="Canvas 1", dirty=False)])

    manifest = json.loads((root / "cur" / "session.json").read_text())
    assert manifest["docs"] == []


def test_unchanged_tick_is_a_no_op(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    store = _store(root, "cur")
    store.begin()
    docs = [DocDescriptor(state=_valid_state("same"), file_path=None, display_name="Canvas 1", dirty=True)]
    store.save_documents(docs)

    writes: list[str] = []
    original = store._write_manifest
    monkeypatch.setattr(store, "_write_manifest", lambda manifest: (writes.append("w"), original(manifest))[1])

    store.save_documents([DocDescriptor(state=_valid_state("same"), file_path=None, display_name="Canvas 1", dirty=True)])

    assert writes == []  # identical open set → nothing rewritten


def test_corrupt_sibling_dir_is_pruned(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    root.mkdir()
    junk = root / "garbage"
    junk.mkdir()
    (junk / "session.json").write_text("{ not json")

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert not junk.exists()
