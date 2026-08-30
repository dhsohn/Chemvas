from __future__ import annotations

import json
import os
import time

import pytest

from chemvas.core.document_io import write_document
from chemvas.domain.document import CANVAS_FILE_VERSION, serialize_settings
from chemvas.features.session import DocDescriptor
from chemvas.ui import session_snapshot_store
from chemvas.ui.session_snapshot_store import SessionSnapshotStore


def _valid_state(marker: str | None = None) -> dict:
    return {
        "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "shapes": [],
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


def _store(root, name, *, pid=4242, process_identity="test-owner"):
    return SessionSnapshotStore(
        root,
        session_id=name,
        pid=pid,
        process_identity=process_identity,
    )


def _dead_pids(monkeypatch):
    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda pid: False)


class _FakeFunction:
    def __init__(self, callback):
        self._callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self._callback(*args)


class _FakeKernel32:
    def __init__(self, *, handle=0, last_error=0, process_times_ok=True):
        self.closed = []
        self.OpenProcess = _FakeFunction(lambda *_args: handle)
        self.GetLastError = _FakeFunction(lambda: last_error)
        self.CloseHandle = _FakeFunction(self._close_handle)
        self.GetProcessTimes = _FakeFunction(
            lambda opened, creation, exited, kernel, user: self._get_process_times(
                opened,
                creation,
                exited,
                kernel,
                user,
                process_times_ok=process_times_ok,
            )
        )

    def _close_handle(self, handle):
        self.closed.append(handle)
        return 1

    def _get_process_times(
        self,
        _opened,
        creation,
        _exited,
        _kernel,
        _user,
        *,
        process_times_ok,
    ):
        if not process_times_ok:
            return 0
        creation._obj.dwHighDateTime = 0x01234567
        creation._obj.dwLowDateTime = 0x89ABCDEF
        return 1


class _FakeWindll:
    def __init__(self, kernel32):
        self.kernel32 = kernel32


class _FakeLibproc:
    def __init__(
        self,
        *,
        started_sec=1_725_000_000,
        started_usec=123_456,
        returned_size=None,
    ):
        self.started_sec = started_sec
        self.started_usec = started_usec
        self.returned_size = returned_size
        self.calls = []
        self.proc_pidinfo = _FakeFunction(self._proc_pidinfo)

    def _proc_pidinfo(self, pid, flavor, arg, buffer, buffer_size):
        self.calls.append((pid, flavor, arg, buffer_size))
        info = buffer._obj
        info.pbi_pid = pid
        info.pbi_start_tvsec = self.started_sec
        info.pbi_start_tvusec = self.started_usec
        return buffer_size if self.returned_size is None else self.returned_size


def _install_fake_kernel32(monkeypatch, kernel32):
    import ctypes

    monkeypatch.setattr(ctypes, "windll", _FakeWindll(kernel32), raising=False)


def test_crash_restore_round_trips_unsaved_work(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=111)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("scratch"),
                file_path=None,
                display_name="Canvas 1",
                dirty=True,
            )
        ]
    )

    _dead_pids(monkeypatch)  # the previous instance is gone → a crash
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 1
    assert len(result.docs) == 1
    restored = result.docs[0]
    assert restored.dirty is True
    assert restored.file_path is None
    assert restored.state is not None
    assert restored.state["last_smiles_input"] == "scratch"
    # Deferred prune: the source dir is only scheduled for deletion, not yet gone
    # (the caller prunes after re-snapshotting the recovered work).
    assert result.prune_ids == ["prev"]
    assert (root / "prev").exists()


def test_legacy_v1_dirty_snapshot_is_recovered_without_an_owner_sidecar(
    tmp_path, monkeypatch
):
    root = tmp_path / "sessions"
    previous = root / "legacy"
    previous.mkdir(parents=True)
    write_document(
        previous / "doc-legacy.json",
        _valid_state("legacy-dirty"),
        CANVAS_FILE_VERSION,
    )
    (previous / "session.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 111,
                "clean_exit": False,
                "docs": [
                    {
                        "file_path": None,
                        "display_name": "Legacy Canvas",
                        "dirty": True,
                        "snapshot": "doc-legacy.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 1
    assert result.prune_ids == ["legacy"]
    assert len(result.docs) == 1
    assert result.docs[0].display_name == "Legacy Canvas"
    assert result.docs[0].state is not None
    assert result.docs[0].state["last_smiles_input"] == "legacy-dirty"


def test_clean_exit_reopens_saved_files_from_disk(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    saved = tmp_path / "molecule.chemvas"
    write_document(saved, _valid_state("on-disk"), CANVAS_FILE_VERSION)

    prev = _store(root, "prev", pid=222)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("on-disk"),
                file_path=str(saved),
                display_name="molecule.chemvas",
                dirty=False,
            )
        ]
    )
    prev.mark_clean_exit()

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 0
    assert [d.file_path for d in result.docs] == [str(saved)]
    assert result.docs[0].dirty is False
    assert result.docs[0].state is not None


def test_clean_exit_skips_legacy_saved_file_path(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    saved = tmp_path / "molecule.json"
    write_document(saved, _valid_state("on-disk"), CANVAS_FILE_VERSION)

    prev = _store(root, "prev", pid=222)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("on-disk"),
                file_path=str(saved),
                display_name="molecule.json",
                dirty=False,
            )
        ]
    )
    prev.mark_clean_exit()

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 0
    assert result.docs == []


def test_crash_snapshot_with_legacy_path_recovers_unbound(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    legacy = tmp_path / "molecule.json"
    write_document(legacy, _valid_state("on-disk"), CANVAS_FILE_VERSION)

    prev = _store(root, "prev", pid=222)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("unsaved"),
                file_path=str(legacy),
                display_name="molecule.json",
                dirty=True,
            )
        ]
    )

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 1
    assert len(result.docs) == 1
    restored = result.docs[0]
    assert restored.file_path is None
    assert restored.dirty is True
    assert restored.state is not None
    assert restored.state["last_smiles_input"] == "unsaved"


def test_missing_crash_snapshot_does_not_fall_back_to_legacy_disk_path(
    tmp_path, monkeypatch
):
    root = tmp_path / "sessions"
    legacy = tmp_path / "molecule.json"
    write_document(legacy, _valid_state("on-disk"), CANVAS_FILE_VERSION)

    prev = _store(root, "prev", pid=222)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("unsaved"),
                file_path=str(legacy),
                display_name="molecule.json",
                dirty=True,
            )
        ]
    )
    manifest = json.loads((root / "prev" / "session.json").read_text())
    (root / "prev" / manifest["docs"][0]["snapshot"]).unlink()

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 0
    assert result.docs == []


def test_clean_exit_drops_unsaved_untitled_docs(tmp_path, monkeypatch):
    # An untitled dirty doc present at a clean exit was already resolved by the
    # close prompt (saved or discarded), so it must NOT come back.
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=333)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state(),
                file_path=None,
                display_name="Canvas 1",
                dirty=True,
            )
        ]
    )
    prev.mark_clean_exit()

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []


def test_crash_and_clean_session_are_both_restored(tmp_path, monkeypatch):
    # Every launch restores crashed unsaved work plus the newest clean
    # workspace; both consumed siblings are scheduled for deferred pruning.
    root = tmp_path / "sessions"
    saved = tmp_path / "kept.chemvas"
    write_document(saved, _valid_state("disk"), CANVAS_FILE_VERSION)

    clean = _store(root, "clean-session", pid=10)
    clean.begin()
    clean.save_documents(
        [
            DocDescriptor(
                state=_valid_state("disk"),
                file_path=str(saved),
                display_name="kept.chemvas",
                dirty=False,
            )
        ]
    )
    clean.mark_clean_exit()

    crash = _store(root, "crash-session", pid=11)
    crash.begin()
    crash.save_documents(
        [
            DocDescriptor(
                state=_valid_state("unsaved"),
                file_path=None,
                display_name="Canvas 1",
                dirty=True,
            )
        ]
    )

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 1
    assert sorted(doc.dirty for doc in result.docs) == [False, True]
    # Both siblings are scheduled for prune (deferred), not yet deleted.
    assert set(result.prune_ids) == {"clean-session", "crash-session"}
    assert (root / "clean-session").exists()
    assert (root / "crash-session").exists()


def test_unreadable_snapshot_does_not_inflate_recovered_count(tmp_path, monkeypatch):
    # A dirty entry whose payload is missing/truncated must not be counted as a
    # recovered document nor claimed in the "Recovered N unsaved" message.
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=55)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("good"),
                file_path=None,
                display_name="Good",
                dirty=True,
            ),
            DocDescriptor(
                state=_valid_state("lost"),
                file_path=None,
                display_name="Lost",
                dirty=True,
            ),
        ]
    )
    manifest = json.loads((root / "prev" / "session.json").read_text(encoding="utf-8"))
    lost_snapshot = next(
        entry["snapshot"]
        for entry in manifest["docs"]
        if entry["display_name"] == "Lost"
    )
    (root / "prev" / lost_snapshot).unlink()  # simulate a truncated/missing payload

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 1
    assert [doc.display_name for doc in result.docs] == ["Good"]


def test_prune_sessions_deletes_the_given_dirs(tmp_path):
    root = tmp_path / "sessions"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)

    _store(root, "cur").prune_sessions(["a", "b"])

    assert not (root / "a").exists()
    assert not (root / "b").exists()


def test_consume_tolerates_a_sibling_vanishing_mid_scan(tmp_path, monkeypatch):
    import shutil

    # Another instance can delete a sibling between _read_manifest and stat().
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=77)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("x"), file_path=None, display_name="X", dirty=True
            )
        ]
    )

    cur = _store(root, "cur")
    original_read = cur._read_manifest

    def read_then_vanish(session_dir):
        manifest = original_read(session_dir)
        shutil.rmtree(
            session_dir, ignore_errors=True
        )  # concurrent prune after the read
        return manifest

    monkeypatch.setattr(cur, "_read_manifest", read_then_vanish)
    _dead_pids(monkeypatch)

    result = cur.consume_previous_sessions()  # must not raise FileNotFoundError

    assert result.docs == []


def test_live_instance_session_is_left_untouched(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=444)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("live"),
                file_path=None,
                display_name="Canvas 1",
                dirty=True,
            )
        ]
    )

    monkeypatch.setattr(
        session_snapshot_store, "_pid_alive", lambda pid: True
    )  # still running
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity",
        lambda pid: "test-owner",
    )
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert (root / "prev").exists()  # not pruned


def test_identityless_legacy_live_session_fails_closed_on_pid_reuse(
    tmp_path, monkeypatch
):
    root = tmp_path / "sessions"
    monkeypatch.setattr(session_snapshot_store, "_process_identity", lambda _pid: None)
    prev = _store(root, "prev", pid=444, process_identity=None)
    prev.begin()

    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity",
        lambda _pid: "replacement-process",
    )
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert result.prune_ids == []
    assert (root / "prev").exists()


def test_reused_pid_recovers_the_crashed_owner_session(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=444, process_identity="original-owner")
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("recovered"),
                file_path=None,
                display_name="Canvas 1",
                dirty=True,
            )
        ]
    )

    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity",
        lambda pid: "replacement-process",
    )
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 1
    assert [doc.display_name for doc in result.docs] == ["Canvas 1"]
    assert result.prune_ids == ["prev"]


def test_process_identity_probe_is_cached_per_pid_during_restore(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    for name in ("first", "second"):
        previous = _store(root, name, pid=444, process_identity="same-owner")
        previous.begin()

    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda _pid: True)
    calls = []

    def identity(pid):
        calls.append(pid)
        return "same-owner"

    monkeypatch.setattr(session_snapshot_store, "_process_identity", identity)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert result.prune_ids == []
    assert calls == [444]


def test_malformed_owner_sidecar_discards_identity_and_fails_closed(
    tmp_path, monkeypatch
):
    root = tmp_path / "sessions"
    previous = _store(root, "prev", pid=444, process_identity="original-owner")
    previous.begin()
    owner_path = previous.session_dir / session_snapshot_store.OWNER_NAME
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    owner["unexpected"] = True
    owner_path.write_text(json.dumps(owner), encoding="utf-8")

    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity",
        lambda _pid: "replacement-process",
    )
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert result.prune_ids == []
    assert previous.session_dir.exists()


def test_whitespace_owner_identity_is_rejected_at_store_and_reader_boundaries(tmp_path):
    root = tmp_path / "sessions"
    for index, malformed_identity in enumerate(("   ", " owner", "owner ")):
        whitespace = _store(
            root,
            f"whitespace-{index}",
            process_identity=malformed_identity,
        )
        whitespace.begin()

        owner_path = whitespace.session_dir / session_snapshot_store.OWNER_NAME
        assert not owner_path.exists()

    valid = _store(root, "valid", process_identity="original-owner")
    valid.begin()
    owner_path = valid.session_dir / session_snapshot_store.OWNER_NAME
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    owner["process_identity"] = " original-owner "
    owner_path.write_text(json.dumps(owner), encoding="utf-8")

    parsed = _store(root, "cur")._read_manifest(valid.session_dir)
    assert parsed is not None
    assert parsed.process_identity is None


def test_bounded_json_reads_tolerate_deep_and_oversized_session_metadata(
    tmp_path, monkeypatch
):
    root = tmp_path / "sessions"
    previous = _store(root, "previous", pid=444, process_identity="original-owner")
    previous.begin()
    current = _store(root, "current")

    owner_path = previous.session_dir / session_snapshot_store.OWNER_NAME
    monkeypatch.setattr(session_snapshot_store, "_MAX_OWNER_BYTES", 30_000)
    owner_path.write_text("[" * 10_000 + "0" + "]" * 10_000, encoding="utf-8")
    parsed = current._read_manifest(previous.session_dir)
    assert parsed is not None
    assert parsed.process_identity is None

    monkeypatch.setattr(session_snapshot_store, "_MAX_MANIFEST_BYTES", 32)
    manifest_path = previous.session_dir / session_snapshot_store.MANIFEST_NAME
    manifest_path.write_text(" " * 33, encoding="utf-8")
    assert current._read_manifest(previous.session_dir) is None


def test_duplicate_keys_in_session_metadata_fail_closed(tmp_path):
    root = tmp_path / "sessions"
    previous = _store(root, "previous", pid=444, process_identity="original-owner")
    previous.begin()
    current = _store(root, "current")

    owner_path = previous.session_dir / session_snapshot_store.OWNER_NAME
    owner_path.write_text(
        '{"version":1,"version":1,"pid":444,"process_identity":"original-owner"}',
        encoding="utf-8",
    )
    parsed = current._read_manifest(previous.session_dir)
    assert parsed is not None
    assert parsed.process_identity is None

    manifest_path = previous.session_dir / session_snapshot_store.MANIFEST_NAME
    manifest_path.write_text(
        '{"version":1,"version":1,"pid":444,"clean_exit":false,"docs":[]}',
        encoding="utf-8",
    )
    assert current._read_manifest(previous.session_dir) is None


def test_manifest_writer_never_publishes_more_than_its_read_limit(
    tmp_path, monkeypatch
):
    root = tmp_path / "sessions"
    store = _store(root, "current")
    store.begin()
    manifest_path = store.session_dir / session_snapshot_store.MANIFEST_NAME
    before = manifest_path.read_bytes()
    monkeypatch.setattr(
        session_snapshot_store,
        "_MAX_MANIFEST_BYTES",
        len(before) + 8,
    )

    with pytest.raises(ValueError, match="JSON payload exceeds"):
        store.save_documents(
            [
                DocDescriptor(
                    state=_valid_state(),
                    file_path="/tmp/saved.chemvas",
                    display_name="x" * 100,
                    dirty=False,
                )
            ]
        )

    assert manifest_path.read_bytes() == before
    assert store._read_manifest(store.session_dir) is not None


def test_owner_sidecar_pid_must_match_its_manifest(tmp_path):
    root = tmp_path / "sessions"
    previous = _store(root, "prev", pid=444, process_identity="original-owner")
    previous.begin()
    owner_path = previous.session_dir / session_snapshot_store.OWNER_NAME
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    owner["pid"] = 445
    owner_path.write_text(json.dumps(owner), encoding="utf-8")

    parsed = _store(root, "cur")._read_manifest(previous.session_dir)

    assert parsed is not None
    assert parsed.process_identity is None


def test_store_reads_development_v2_identity_when_no_sidecar_exists(tmp_path):
    root = tmp_path / "sessions"
    previous = root / "development-v2"
    previous.mkdir(parents=True)
    (previous / "session.json").write_text(
        json.dumps(
            {
                "version": 2,
                "pid": 444,
                "process_identity": "embedded-owner",
                "clean_exit": False,
                "docs": [],
            }
        ),
        encoding="utf-8",
    )

    parsed = _store(root, "cur")._read_manifest(previous)

    assert parsed is not None
    assert parsed.process_identity == "embedded-owner"


def test_clean_saved_doc_is_recorded_without_a_snapshot(tmp_path):
    root = tmp_path / "sessions"
    saved = tmp_path / "x.chemvas"
    write_document(saved, _valid_state(), CANVAS_FILE_VERSION)
    store = _store(root, "cur")
    store.begin()

    store.save_documents(
        [
            DocDescriptor(
                state=_valid_state(),
                file_path=str(saved),
                display_name="x.chemvas",
                dirty=False,
            )
        ]
    )

    assert list((root / "cur").glob("doc-*.json")) == []
    manifest = json.loads((root / "cur" / "session.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"version", "pid", "clean_exit", "docs"}
    assert manifest["version"] == 1
    assert manifest["docs"][0]["snapshot"] is None
    assert manifest["docs"][0]["file_path"] == str(saved)
    owner = json.loads(
        (root / "cur" / session_snapshot_store.OWNER_NAME).read_text(encoding="utf-8")
    )
    assert owner == {
        "version": 1,
        "pid": 4242,
        "process_identity": "test-owner",
    }


def test_pristine_untitled_canvas_is_not_persisted(tmp_path):
    root = tmp_path / "sessions"
    store = _store(root, "cur")
    store.begin()

    store.save_documents(
        [
            DocDescriptor(
                state=_valid_state(),
                file_path=None,
                display_name="Canvas 1",
                dirty=False,
            )
        ]
    )

    manifest = json.loads((root / "cur" / "session.json").read_text(encoding="utf-8"))
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
            DocDescriptor(
                state=_valid_state("A"), file_path=None, display_name="A", dirty=True
            ),
            DocDescriptor(
                state=_valid_state("B"), file_path=None, display_name="B", dirty=True
            ),
        ]
    )
    assert sorted(p.name for p in session.glob("doc-*.json")) == [
        "doc-1-0.json",
        "doc-1-1.json",
    ]

    # Close the first doc: only B persists now, under a fresh generation name.
    store.save_documents(
        [
            DocDescriptor(
                state=_valid_state("B"), file_path=None, display_name="B", dirty=True
            )
        ]
    )

    assert sorted(p.name for p in session.glob("doc-*.json")) == [
        "doc-2-0.json"
    ]  # gen 1 pruned
    manifest = json.loads((session / "session.json").read_text(encoding="utf-8"))
    assert [entry["snapshot"] for entry in manifest["docs"]] == ["doc-2-0.json"]


def test_unchanged_tick_is_a_no_op(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    store = _store(root, "cur")
    store.begin()
    docs = [
        DocDescriptor(
            state=_valid_state("same"),
            file_path=None,
            display_name="Canvas 1",
            dirty=True,
        )
    ]
    store.save_documents(docs)

    writes: list[str] = []
    original = store._write_manifest
    monkeypatch.setattr(
        store,
        "_write_manifest",
        lambda manifest: (writes.append("w"), original(manifest))[1],
    )

    store.save_documents(
        [
            DocDescriptor(
                state=_valid_state("same"),
                file_path=None,
                display_name="Canvas 1",
                dirty=True,
            )
        ]
    )

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


def test_current_process_identity_is_nonempty_and_stable():
    first = session_snapshot_store._process_identity(os.getpid())
    second = session_snapshot_store._process_identity(os.getpid())

    assert first
    assert second == first


def test_process_identity_rejects_nonpositive_pids():
    assert session_snapshot_store._process_identity(0) is None
    assert session_snapshot_store._process_identity(-1) is None


def test_huge_pid_probes_are_exception_free_and_fail_closed():
    huge_pid = 10**100

    assert session_snapshot_store._pid_alive(huge_pid) is True
    assert session_snapshot_store._pid_alive_posix(huge_pid) is True
    assert session_snapshot_store._pid_alive_windows(huge_pid) is True
    assert session_snapshot_store._process_identity(huge_pid) is None
    assert session_snapshot_store._process_identity_linux(huge_pid) is None
    assert session_snapshot_store._process_identity_posix(huge_pid) is None
    assert session_snapshot_store._process_identity_windows(huge_pid) is None


def test_windows_dword_pid_range_is_persisted_while_posix_overflow_fails_closed(
    tmp_path, monkeypatch
):
    high_pid = 4_294_967_295
    root = tmp_path / "sessions"
    store = _store(
        root,
        "high-pid",
        pid=high_pid,
        process_identity="windows:123456",
    )
    store.begin()

    parsed = _store(root, "current")._read_manifest(store.session_dir)
    assert parsed is not None
    assert parsed.pid == high_pid
    assert parsed.process_identity == "windows:123456"

    monkeypatch.setattr(
        session_snapshot_store.os,
        "kill",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("out-of-range POSIX pid must not reach os.kill")
        ),
    )
    assert session_snapshot_store._pid_alive_posix(high_pid) is True
    assert session_snapshot_store._process_identity_posix(high_pid) is None


def test_linux_start_ticks_handles_spaces_and_close_parens_in_comm():
    fields_3_through_22 = ["S", *(str(value) for value in range(4, 23))]
    stat = f"123 (worker ) name with spaces) {' '.join(fields_3_through_22)}"

    assert session_snapshot_store._linux_start_ticks(stat) == "22"
    assert session_snapshot_store._linux_start_ticks("123 malformed") is None


def test_posix_process_identity_is_independent_of_caller_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Seoul")
    first = session_snapshot_store._process_identity_posix(os.getpid())
    monkeypatch.setenv("TZ", "America/New_York")
    second = session_snapshot_store._process_identity_posix(os.getpid())

    assert first
    assert second == first


def test_process_identity_dispatches_to_windows_creation_time(monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity_windows",
        lambda pid: (seen.append(pid), "windows:1234")[1],
    )

    assert session_snapshot_store._process_identity(4321) == "windows:1234"
    assert seen == [4321]


def test_process_identity_dispatches_to_portable_posix_fallback(monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr("sys.platform", "freebsd14")
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity_posix",
        lambda pid: (seen.append(pid), "posix:start-time")[1],
    )

    assert session_snapshot_store._process_identity(4321) == "posix:start-time"
    assert seen == [4321]


def test_darwin_libproc_failure_is_unknown_without_ps_scheme_fallback(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity_darwin",
        lambda _pid: None,
    )
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity_posix",
        lambda _pid: (_ for _ in ()).throw(
            AssertionError("Darwin must not switch to a second-resolution ps token")
        ),
    )

    assert session_snapshot_store._process_identity(4321) is None


def test_process_identity_prefers_darwin_libproc_over_posix_fallback(monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity_darwin",
        lambda pid: (seen.append(pid), "darwin:1725000000:123456")[1],
    )
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity_posix",
        lambda _pid: (_ for _ in ()).throw(
            AssertionError("ps fallback must not run after a libproc success")
        ),
    )

    assert session_snapshot_store._process_identity(4321) == "darwin:1725000000:123456"
    assert seen == [4321]


def test_darwin_libproc_identity_uses_microsecond_start_token(monkeypatch):
    libproc = _FakeLibproc(started_sec=1_725_000_000, started_usec=123_456)
    monkeypatch.setattr(
        session_snapshot_store,
        "_load_darwin_libproc",
        lambda: libproc,
    )

    assert (
        session_snapshot_store.ctypes.sizeof(session_snapshot_store._DarwinProcBsdInfo)
        == 136
    )
    assert (
        session_snapshot_store._process_identity_darwin(4321)
        == "darwin:1725000000:123456"
    )
    assert libproc.calls == [
        (
            4321,
            session_snapshot_store._DARWIN_PROC_PIDTBSDINFO,
            0,
            session_snapshot_store.ctypes.sizeof(
                session_snapshot_store._DarwinProcBsdInfo
            ),
        )
    ]
    assert libproc.proc_pidinfo.argtypes is not None
    assert libproc.proc_pidinfo.restype is session_snapshot_store.ctypes.c_int

    libproc.started_usec = 123_457
    assert (
        session_snapshot_store._process_identity_darwin(4321)
        == "darwin:1725000000:123457"
    )


def test_darwin_libproc_partial_or_invalid_result_falls_back_to_unknown(monkeypatch):
    partial = _FakeLibproc(returned_size=1)
    monkeypatch.setattr(
        session_snapshot_store,
        "_load_darwin_libproc",
        lambda: partial,
    )
    assert session_snapshot_store._process_identity_darwin(4321) is None

    invalid_usec = _FakeLibproc(started_usec=1_000_000)
    monkeypatch.setattr(
        session_snapshot_store,
        "_load_darwin_libproc",
        lambda: invalid_usec,
    )
    assert session_snapshot_store._process_identity_darwin(4321) is None


def test_pid_liveness_uses_a_safe_probe_on_windows_never_os_kill(monkeypatch):
    seen: dict = {}

    def _fake_windows(pid):
        seen["pid"] = pid
        return True

    def _forbidden_kill(*_args, **_kwargs):
        raise AssertionError(
            "os.kill must never be used on Windows (it terminates the target)"
        )

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(session_snapshot_store, "_pid_alive_windows", _fake_windows)
    monkeypatch.setattr(session_snapshot_store.os, "kill", _forbidden_kill)

    assert session_snapshot_store._pid_alive(4321) is True
    assert seen["pid"] == 4321


def test_windows_liveness_distinguishes_access_denied_from_missing(monkeypatch):
    access_denied = _FakeKernel32(handle=0, last_error=5)
    _install_fake_kernel32(monkeypatch, access_denied)

    assert session_snapshot_store._pid_alive_windows(4321) is True
    assert access_denied.closed == []
    assert access_denied.OpenProcess.argtypes is not None
    assert access_denied.OpenProcess.restype is not None
    assert access_denied.CloseHandle.argtypes is not None
    assert access_denied.CloseHandle.restype is not None

    missing = _FakeKernel32(handle=0, last_error=87)
    _install_fake_kernel32(monkeypatch, missing)

    assert session_snapshot_store._pid_alive_windows(4321) is False
    assert missing.closed == []


def test_windows_process_identity_closes_handle_on_query_failure(monkeypatch):
    kernel32 = _FakeKernel32(handle=123, process_times_ok=False)
    _install_fake_kernel32(monkeypatch, kernel32)

    assert session_snapshot_store._process_identity_windows(4321) is None
    assert kernel32.closed == [123]
    assert kernel32.GetProcessTimes.argtypes is not None
    assert kernel32.GetProcessTimes.restype is not None


def test_windows_process_identity_uses_creation_filetime_and_closes(monkeypatch):
    kernel32 = _FakeKernel32(handle=456, process_times_ok=True)
    _install_fake_kernel32(monkeypatch, kernel32)

    expected = (0x01234567 << 32) | 0x89ABCDEF
    assert (
        session_snapshot_store._process_identity_windows(4321) == f"windows:{expected}"
    )
    assert kernel32.closed == [456]


def test_old_corrupt_sibling_without_owner_proof_is_preserved(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    root.mkdir()
    junk = root / "garbage"
    junk.mkdir()
    (junk / "session.json").write_text("{ not json")
    old = time.time() - 3600
    os.utime(junk, (old, old))  # clearly old → a real orphan

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert junk.exists()


def test_old_corrupt_sibling_is_pruned_only_when_owner_is_proven_gone(
    tmp_path, monkeypatch
):
    root = tmp_path / "sessions"
    previous = _store(root, "gone", pid=111, process_identity="original-owner")
    previous.begin()
    (previous.session_dir / session_snapshot_store.MANIFEST_NAME).write_text(
        "{ not json",
        encoding="utf-8",
    )
    old = time.time() - 3600
    os.utime(previous.session_dir, (old, old))

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert not previous.session_dir.exists()


def test_old_corrupt_live_owner_and_malformed_owner_are_preserved(
    tmp_path, monkeypatch
):
    root = tmp_path / "sessions"
    live = _store(root, "live", pid=444, process_identity="same-owner")
    live.begin()
    malformed = _store(root, "malformed", pid=445, process_identity="owner")
    malformed.begin()

    for store in (live, malformed):
        (store.session_dir / session_snapshot_store.MANIFEST_NAME).write_text(
            "{ not json",
            encoding="utf-8",
        )
        old = time.time() - 3600
        os.utime(store.session_dir, (old, old))
    (malformed.session_dir / session_snapshot_store.OWNER_NAME).write_text(
        "{ malformed",
        encoding="utf-8",
    )

    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(
        session_snapshot_store,
        "_process_identity",
        lambda pid: "same-owner" if pid == 444 else None,
    )
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert live.session_dir.exists()
    assert malformed.session_dir.exists()


def test_recently_created_unreadable_sibling_is_left_alone(tmp_path, monkeypatch):
    # A sibling that just made its dir but has not written session.json yet
    # (another instance mid-begin) must not be reaped as if it were an orphan.
    root = tmp_path / "sessions"
    root.mkdir()
    starting = root / "starting-up"
    starting.mkdir()  # freshly created, no manifest

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.docs == []
    assert starting.exists()


def test_snapshot_with_an_uncomparable_number_is_skipped_not_fatal(
    tmp_path, monkeypatch
):
    # A number past the arithmetic context's limit constructs fine and only
    # fails when the range check takes its absolute value. Recovery runs before
    # the event loop starts, and a recorded session is not pruned until a
    # recovery finishes, so an arithmetic error escaping here aborts every
    # launch.
    root = tmp_path / "sessions"
    prev = _store(root, "prev", pid=55)
    prev.begin()
    prev.save_documents(
        [
            DocDescriptor(
                state=_valid_state("good"),
                file_path=None,
                display_name="Good",
                dirty=True,
            ),
            DocDescriptor(
                state=_valid_state("huge"),
                file_path=None,
                display_name="Huge",
                dirty=True,
            ),
        ]
    )
    manifest = json.loads((root / "prev" / "session.json").read_text(encoding="utf-8"))
    huge_snapshot = next(
        entry["snapshot"]
        for entry in manifest["docs"]
        if entry["display_name"] == "Huge"
    )
    snapshot_path = root / "prev" / huge_snapshot
    text = snapshot_path.read_text(encoding="utf-8")
    assert "18.0" in text
    snapshot_path.write_text(text.replace("18.0", "1e999999999", 1), encoding="utf-8")

    _dead_pids(monkeypatch)
    result = _store(root, "cur").consume_previous_sessions()

    assert result.recovered_unsaved == 1
    assert [doc.display_name for doc in result.docs] == ["Good"]
