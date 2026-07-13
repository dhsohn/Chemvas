from __future__ import annotations

from ui.session_snapshot_logic import (
    DocEntry,
    SessionManifest,
    count_recovered_unsaved,
    entries_to_restore,
    is_consumable,
    manifest_from_json,
    manifest_to_json,
    needs_snapshot,
    select_restorable,
    should_persist,
)


def _entry(*, file_path=None, dirty=False, snapshot=None, name="Doc"):
    return DocEntry(file_path=file_path, display_name=name, dirty=dirty, snapshot=snapshot)


def test_should_persist_skips_only_blank_untitled():
    assert should_persist(has_path=True, dirty=False) is True  # saved
    assert should_persist(has_path=False, dirty=True) is True  # unsaved scratch
    assert should_persist(has_path=True, dirty=True) is True
    assert should_persist(has_path=False, dirty=False) is False  # pristine new canvas


def test_only_dirty_docs_need_a_snapshot():
    assert needs_snapshot(dirty=True) is True
    assert needs_snapshot(dirty=False) is False


def test_is_consumable_leaves_live_instances_alone():
    def dead(_pid):
        return False

    def alive(_pid):
        return True

    crashed = SessionManifest(pid=42, clean_exit=False)
    clean = SessionManifest(pid=42, clean_exit=True)

    assert is_consumable(clean, is_alive=alive) is True  # clean exit, regardless of pid
    assert is_consumable(crashed, is_alive=dead) is True  # crash — pid gone
    assert is_consumable(crashed, is_alive=alive) is False  # still running elsewhere


def test_select_restorable_picks_newest_and_prunes_all_consumable():
    a = SessionManifest(pid=1, clean_exit=True)
    b = SessionManifest(pid=2, clean_exit=True)
    candidates = [("old", a, 100.0), ("new", b, 200.0)]

    chosen, prune = select_restorable(candidates, is_alive=lambda pid: False)

    assert chosen == ("new", b)
    assert set(prune) == {"old", "new"}


def test_select_restorable_ignores_live_sessions():
    live = SessionManifest(pid=7, clean_exit=False)
    candidates = [("live", live, 100.0)]

    chosen, prune = select_restorable(candidates, is_alive=lambda pid: True)

    assert chosen is None
    assert prune == []


def test_entries_to_restore_clean_exit_keeps_only_saved_paths():
    manifest = SessionManifest(
        pid=1,
        clean_exit=True,
        docs=[_entry(file_path="/a/x.chemvas"), _entry(file_path=None, dirty=True, snapshot="doc-0.json")],
    )
    restored = entries_to_restore(manifest)
    assert [e.file_path for e in restored] == ["/a/x.chemvas"]


def test_entries_to_restore_crash_keeps_everything():
    manifest = SessionManifest(
        pid=1,
        clean_exit=False,
        docs=[_entry(file_path="/a/x.chemvas"), _entry(file_path=None, dirty=True, snapshot="doc-0.json")],
    )
    assert len(entries_to_restore(manifest)) == 2


def test_count_recovered_unsaved_only_counts_on_crash():
    docs = [_entry(dirty=True, snapshot="doc-0.json"), _entry(file_path="/a/x.chemvas")]
    assert count_recovered_unsaved(SessionManifest(pid=1, clean_exit=False, docs=docs)) == 1
    assert count_recovered_unsaved(SessionManifest(pid=1, clean_exit=True, docs=docs)) == 0


def test_manifest_json_round_trips():
    manifest = SessionManifest(
        pid=99,
        clean_exit=False,
        docs=[_entry(file_path="/a/x.chemvas", dirty=True, snapshot="doc-0.json", name="x.chemvas")],
    )
    restored = manifest_from_json(manifest_to_json(manifest))
    assert restored == manifest


def test_manifest_from_json_rejects_garbage():
    assert manifest_from_json(None) is None
    assert manifest_from_json({"clean_exit": True}) is None  # no pid
    # A doc without a display_name is dropped, not fatal.
    parsed = manifest_from_json({"pid": 1, "docs": [{"file_path": "/a"}, {"display_name": "ok"}]})
    assert parsed is not None
    assert [e.display_name for e in parsed.docs] == ["ok"]
