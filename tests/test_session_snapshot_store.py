from __future__ import annotations

import json
import os

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


def test_crash_is_recovered_even_when_clean_session_is_suppressed(tmp_path, monkeypatch):
    # The startup-file case (include_clean_session=False): the clean workspace is
    # not reopened, but a crashed session's unsaved work must still be recovered
    # rather than silently pruned.
    root = tmp_path / "sessions"
    saved = tmp_path / "kept.chemvas"
    write_document(saved, _valid_state("disk"), CANVAS_FILE_VERSION)

    clean = _store(root, "clean-session", pid=10)
    clean.begin()
    clean.save_documents([DocDescriptor(state=_valid_state("disk"), file_path=str(saved), display_name="kept.chemvas", dirty=False)])
    clean.mark_clean_exit()

    crash = _store(root, "crash-session", pid=11)
    crash.begin()
    crash.save_documents([DocDescriptor(state=_valid_state("unsaved"), file_path=None, display_name="Canvas 1", dirty=True)])

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions(include_clean_session=False)

    assert result.recovered_unsaved == 1
    assert [doc.dirty for doc in result.docs] == [True]
    assert result.docs[0].state["last_smiles_input"] == "unsaved"
    # Both siblings are pruned (the clean one's file is safe on disk).
    assert not (root / "clean-session").exists()
    assert not (root / "crash-session").exists()


def test_unreadable_snapshot_does_not_inflate_recovered_count(tmp_path, monkeypatch):
    # A dirty entry whose payload is missing/truncated must not be counted as a
    # recovered document nor claimed in the "Recovered N unsaved" message.
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=55)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(state=_valid_state("good"), file_path=None, display_name="Good", dirty=True),
            DocDescriptor(state=_valid_state("lost"), file_path=None, display_name="Lost", dirty=True),
        ]
    )
    manifest = json.loads((root / "prev" / "session.json").read_text())
    lost_snapshot = next(entry["snapshot"] for entry in manifest["docs"] if entry["display_name"] == "Lost")
    (root / "prev" / lost_snapshot).unlink()  # simulate a truncated/missing payload

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 1
    assert [doc.display_name for doc in result.docs] == ["Good"]


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


def test_snapshot_names_are_generation_unique_and_pruned_after_commit(tmp_path):
    # A new generation must never overwrite the previous generation's payloads
    # (a crash mid-save would otherwise leave the old manifest pointing at
    # foreign content). Old files are pruned only after the new manifest lands.
    root = tmp_path / "sessions"
    store = _store(root, "cur")
    store.begin()
    session = store.session_dir

    store.save_documents(
        [
            DocDescriptor(state=_valid_state("A"), file_path=None, display_name="A", dirty=True),
            DocDescriptor(state=_valid_state("B"), file_path=None, display_name="B", dirty=True),
        ]
    )
    assert sorted(p.name for p in session.glob("doc-*.json")) == ["doc-1-0.json", "doc-1-1.json"]

    # Close the first doc: only B persists now, under a fresh generation name.
    store.save_documents([DocDescriptor(state=_valid_state("B"), file_path=None, display_name="B", dirty=True)])

    assert sorted(p.name for p in session.glob("doc-*.json")) == ["doc-2-0.json"]  # gen 1 pruned
    manifest = json.loads((session / "session.json").read_text())
    assert [entry["snapshot"] for entry in manifest["docs"]] == ["doc-2-0.json"]


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


def test_consume_tolerates_a_non_directory_sessions_root(tmp_path, monkeypatch):
    # A broken profile can leave <app-data>/sessions as a regular file; consuming
    # must not raise NotADirectoryError before the editor opens.
    root = tmp_path / "sessions"
    root.write_text("not a directory")

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []


def test_pid_liveness_rejects_nonpositive_pids():
    assert session_snapshot_store._pid_alive(0) is False
    assert session_snapshot_store._pid_alive(-1) is False


def test_pid_liveness_reports_the_current_process_alive():
    assert session_snapshot_store._pid_alive(os.getpid()) is True


def test_pid_liveness_uses_a_safe_probe_on_windows_never_os_kill(monkeypatch):
    seen: dict = {}

    def _fake_windows(pid):
        seen["pid"] = pid
        return True

    def _forbidden_kill(*_args, **_kwargs):
        raise AssertionError("os.kill must never be used on Windows (it terminates the target)")

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(session_snapshot_store, "_pid_alive_windows", _fake_windows)
    monkeypatch.setattr(session_snapshot_store.os, "kill", _forbidden_kill)

    assert session_snapshot_store._pid_alive(4321) is True
    assert seen["pid"] == 4321


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
