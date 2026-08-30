from __future__ import annotations

from chemvas.features.session import (
    DocEntry,
    SessionManifest,
    entries_to_restore,
    is_consumable,
    is_valid_process_identity,
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


def test_is_consumable_uses_pid_and_process_identity():
    def dead(_pid):
        return False

    def alive(_pid):
        return True

    crashed = SessionManifest(
        pid=42, clean_exit=False, process_identity="owner-at-snapshot"
    )
    clean = SessionManifest(
        pid=42, clean_exit=True, process_identity="owner-at-snapshot"
    )

    assert (
        is_consumable(
            clean,
            is_alive=alive,
            process_identity_for=lambda _pid: "owner-at-snapshot",
        )
        is True
    )  # clean exit, regardless of pid
    assert (
        is_consumable(
            crashed,
            is_alive=dead,
            process_identity_for=lambda _pid: "owner-at-snapshot",
        )
        is True
    )  # crash — pid gone
    assert (
        is_consumable(
            crashed,
            is_alive=alive,
            process_identity_for=lambda _pid: "owner-at-snapshot",
        )
        is False
    )  # the original owner is still running
    assert (
        is_consumable(
            crashed,
            is_alive=alive,
            process_identity_for=lambda _pid: "new-process-at-reused-pid",
        )
        is True
    )  # a different process reused the pid


def test_is_consumable_fails_closed_when_live_owner_identity_is_unknown():
    legacy = SessionManifest(pid=42, clean_exit=False, process_identity=None)
    identified = SessionManifest(
        pid=42, clean_exit=False, process_identity="owner-at-snapshot"
    )

    assert (
        is_consumable(
            legacy,
            is_alive=lambda _pid: True,
            process_identity_for=lambda _pid: "new-process-at-reused-pid",
        )
        is False
    )
    assert (
        is_consumable(
            identified,
            is_alive=lambda _pid: True,
            process_identity_for=lambda _pid: None,
        )
        is False
    )


def test_process_identity_validation_and_policy_reject_whitespace():
    assert is_valid_process_identity("owner") is True
    for malformed in (
        None,
        "",
        "   ",
        "\n",
        "owner\nfragment",
        " owner",
        "owner ",
        42,
    ):
        assert is_valid_process_identity(malformed) is False

    for malformed_owner in ("   ", " original-process "):
        manifest = SessionManifest(
            pid=42,
            clean_exit=False,
            process_identity=malformed_owner,
        )
        assert (
            is_consumable(
                manifest,
                is_alive=lambda _pid: True,
                process_identity_for=lambda _pid: "original-process",
            )
            is False
        )

    identified = SessionManifest(
        pid=42,
        clean_exit=False,
        process_identity="original-process",
    )
    assert (
        is_consumable(
            identified,
            is_alive=lambda _pid: True,
            process_identity_for=lambda _pid: "\n",
        )
        is False
    )


def test_identity_extension_preserves_the_original_public_call_shapes():
    entry = _entry(file_path="/a/x.chemvas", dirty=False, snapshot=None)
    manifest = SessionManifest(42, False, [entry])

    assert manifest.docs == [entry]
    assert manifest.process_identity is None
    assert is_consumable(manifest, is_alive=lambda _pid: True) is False
    plan = plan_restore([("legacy-live", manifest, 1.0)], is_alive=lambda _pid: True)
    assert plan.restore == []
    assert plan.prune == []


def test_plan_restore_reopens_only_the_newest_clean_session_and_prunes_all():
    a = SessionManifest(pid=1, clean_exit=True)
    b = SessionManifest(pid=2, clean_exit=True)
    candidates = [("old", a, 100.0), ("new", b, 200.0)]

    plan = plan_restore(
        candidates,
        is_alive=lambda pid: False,
        process_identity_for=lambda _pid: None,
    )

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

    plan = plan_restore(
        candidates,
        is_alive=lambda pid: False,
        process_identity_for=lambda _pid: None,
    )

    # Every crash is restored (unsaved work is never dropped) + newest clean,
    # ordered newest-first so the most recent session reuses the blank window.
    assert plan.restore == ["c_new", "clean", "c_old"]
    assert set(plan.prune) == {"c_old", "c_new", "clean"}


def test_plan_restore_ignores_live_sessions():
    live = SessionManifest(pid=7, clean_exit=False, process_identity="same-owner")

    plan = plan_restore(
        [("live", live, 100.0)],
        is_alive=lambda pid: True,
        process_identity_for=lambda _pid: "same-owner",
    )

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


def test_manifest_writer_stays_strict_v1_and_round_trips_documents():
    manifest = SessionManifest(
        pid=99,
        clean_exit=False,
        process_identity="linux:boot-id:12345",
        docs=[
            _entry(
                file_path="/a/x.chemvas",
                dirty=True,
                snapshot="doc-0.json",
                name="x.chemvas",
            )
        ],
    )
    encoded = manifest_to_json(manifest)

    assert encoded == {
        "version": 1,
        "pid": 99,
        "clean_exit": False,
        "docs": [
            {
                "file_path": "/a/x.chemvas",
                "display_name": "x.chemvas",
                "dirty": True,
                "snapshot": "doc-0.json",
            }
        ],
    }
    assert manifest_from_json(encoded) == SessionManifest(
        pid=99,
        clean_exit=False,
        docs=manifest.docs,
        process_identity=None,
    )


def test_manifest_parser_recovers_the_development_v2_format():
    development_v2 = {
        "version": 2,
        "pid": 99,
        "process_identity": "linux:boot-id:12345",
        "clean_exit": False,
        "docs": [
            {
                "file_path": None,
                "display_name": "Canvas 1",
                "dirty": True,
                "snapshot": "doc-0.json",
            }
        ],
    }

    assert manifest_from_json(development_v2) == SessionManifest(
        pid=99,
        clean_exit=False,
        docs=[
            _entry(
                file_path=None,
                dirty=True,
                snapshot="doc-0.json",
                name="Canvas 1",
            )
        ],
        process_identity="linux:boot-id:12345",
    )


def test_manifest_from_json_rejects_garbage():
    assert manifest_from_json(None) is None
    assert manifest_from_json({"clean_exit": True}) is None  # no pid
    base = {
        "version": 2,
        "pid": 1,
        "process_identity": "owner",
        "clean_exit": False,
        "docs": [],
    }
    for version in (3, 2.0, True):
        assert manifest_from_json({**base, "version": version}) is None
    assert manifest_from_json({**base, "clean_exit": 0}) is None
    assert manifest_from_json({**base, "docs": [{"file_path": "/a"}]}) is None
    assert manifest_from_json({**base, "process_identity": ""}) is None
    assert manifest_from_json({**base, "process_identity": "   "}) is None
    assert manifest_from_json({**base, "process_identity": " owner"}) is None
    assert manifest_from_json({**base, "process_identity": "owner "}) is None
    assert manifest_from_json({**base, "process_identity": 42}) is None


def test_manifest_from_json_accepts_v1_as_identityless_legacy():
    legacy = {
        "version": 1,
        "pid": 42,
        "clean_exit": False,
        "docs": [],
    }

    assert manifest_from_json(legacy) == SessionManifest(
        pid=42,
        clean_exit=False,
        process_identity=None,
    )


def test_manifest_from_json_enforces_the_cross_platform_pid_range():
    v1 = {"version": 1, "pid": 1, "clean_exit": False, "docs": []}
    v2 = {
        "version": 2,
        "pid": 1,
        "process_identity": "owner",
        "clean_exit": False,
        "docs": [],
    }

    for base in (v1, v2):
        assert manifest_from_json({**base, "pid": 4_294_967_295}) is not None
        for invalid_pid in (0, -1, 4_294_967_296, 10**100, True):
            assert manifest_from_json({**base, "pid": invalid_pid}) is None
