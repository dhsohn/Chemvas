from __future__ import annotations

from chemvas.features.session import (
    DocEntry,
    SessionManifest,
    entries_to_restore,
    is_consumable,
    manifest_from_json,
    manifest_to_json,
    needs_snapshot,
    plan_restore,
    should_persist,
)


def _entry(*, file_path=None, dirty=False, snapshot=None, name="Doc"):
    return DocEntry(
        file_path=file_path, display_name=name, dirty=dirty, snapshot=snapshot
    )


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


def test_plan_restore_reopens_only_the_newest_clean_session_and_prunes_all():
    a = SessionManifest(pid=1, clean_exit=True)
    b = SessionManifest(pid=2, clean_exit=True)
    candidates = [("old", a, 100.0), ("new", b, 200.0)]

    plan = plan_restore(candidates, is_alive=lambda pid: False)

    assert plan.restore == ["new"]  # older clean session is pruned, not reopened
    assert set(plan.prune) == {"old", "new"}


def test_plan_restore_recovers_every_crash_session_plus_newest_clean():
    crash_old = SessionManifest(pid=1, clean_exit=False)
    crash_new = SessionManifest(pid=2, clean_exit=False)
    clean = SessionManifest(pid=3, clean_exit=True)
    candidates = [
        ("c_old", crash_old, 100.0),
        ("c_new", crash_new, 300.0),
        ("clean", clean, 200.0),
    ]

    plan = plan_restore(candidates, is_alive=lambda pid: False)

    # Every crash is restored (unsaved work is never dropped) + newest clean,
    # ordered newest-first so the most recent session reuses the blank window.
    assert plan.restore == ["c_new", "clean", "c_old"]
    assert set(plan.prune) == {"c_old", "c_new", "clean"}


def test_plan_restore_suppresses_clean_session_but_still_recovers_crashes():
    # This is the startup-file case: a P1 regression would drop the crash here.
    crash = SessionManifest(pid=1, clean_exit=False)
    clean = SessionManifest(pid=2, clean_exit=True)
    candidates = [("crash", crash, 100.0), ("clean", clean, 200.0)]

    plan = plan_restore(
        candidates, is_alive=lambda pid: False, include_clean_session=False
    )

    assert plan.restore == ["crash"]  # crash recovered even though a file was opened
    assert set(plan.prune) == {
        "crash",
        "clean",
    }  # clean pruned (its files are safe on disk)


def test_plan_restore_ignores_live_sessions():
    live = SessionManifest(pid=7, clean_exit=False)

    plan = plan_restore([("live", live, 100.0)], is_alive=lambda pid: True)

    assert plan.restore == []
    assert plan.prune == []


def test_entries_to_restore_clean_exit_keeps_only_saved_paths():
    manifest = SessionManifest(
        pid=1,
        clean_exit=True,
        docs=[
            _entry(file_path="/a/x.chemvas"),
            _entry(file_path=None, dirty=True, snapshot="doc-0.json"),
        ],
    )
    restored = entries_to_restore(manifest)
    assert [e.file_path for e in restored] == ["/a/x.chemvas"]


def test_entries_to_restore_crash_keeps_everything():
    manifest = SessionManifest(
        pid=1,
        clean_exit=False,
        docs=[
            _entry(file_path="/a/x.chemvas"),
            _entry(file_path=None, dirty=True, snapshot="doc-0.json"),
        ],
    )
    assert len(entries_to_restore(manifest)) == 2


def test_manifest_json_round_trips():
    manifest = SessionManifest(
        pid=99,
        clean_exit=False,
        docs=[
            _entry(
                file_path="/a/x.chemvas",
                dirty=True,
                snapshot="doc-0.json",
                name="x.chemvas",
            )
        ],
    )
    restored = manifest_from_json(manifest_to_json(manifest))
    assert restored == manifest


def test_manifest_from_json_rejects_garbage():
    assert manifest_from_json(None) is None
    assert manifest_from_json({"clean_exit": True}) is None  # no pid
    # A doc without a display_name is dropped, not fatal.
    parsed = manifest_from_json(
        {"pid": 1, "docs": [{"file_path": "/a"}, {"display_name": "ok"}]}
    )
    assert parsed is not None
    assert [e.display_name for e in parsed.docs] == ["ok"]
