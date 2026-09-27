"""Exact history snapshots keep their original recovery callbacks."""

from types import SimpleNamespace

import pytest

from chemvas.core.history import history_command_transaction
from chemvas.domain.transactions import RestoreOutcome


def test_failed_command_uses_original_restore_after_hook_replacement():
    state = ["before"]
    restored = []
    wrong_snapshots = []
    original_error = RuntimeError("edit failed")

    def restore(snapshot):
        restored.append(snapshot)
        state[:] = snapshot
        return RestoreOutcome(authoritative=True)

    port = SimpleNamespace(
        capture_history_transaction_for_history=lambda: list(state),
        restore_history_transaction_for_history=restore,
    )
    with pytest.raises(RuntimeError) as caught:
        with history_command_transaction(port):
            state.append("partial edit")
            port.restore_history_transaction_for_history = wrong_snapshots.append
            raise original_error
    assert caught.value is original_error
    assert state == ["before"]
    assert restored == [["before"]]
    assert wrong_snapshots == []


def test_success_releases_original_snapshot_with_capture_time_hook():
    snapshot = object()
    released = []
    wrong_snapshots = []
    port = SimpleNamespace(
        capture_history_transaction_for_history=lambda: snapshot,
        restore_history_transaction_for_history=lambda _: RestoreOutcome(
            authoritative=True
        ),
        release_history_transaction_for_history=released.append,
    )
    with history_command_transaction(port):
        port.release_history_transaction_for_history = wrong_snapshots.append
    assert released == [snapshot]
    assert wrong_snapshots == []


def test_capture_cannot_rebind_its_own_snapshot_restore():
    snapshot = object()
    restored = []
    wrong_snapshots = []

    def capture():
        port.restore_history_transaction_for_history = wrong_snapshots.append
        return snapshot

    port = SimpleNamespace(
        capture_history_transaction_for_history=capture,
        restore_history_transaction_for_history=restored.append,
    )
    with pytest.raises(ValueError, match="failed"):
        with history_command_transaction(port):
            raise ValueError("failed")
    assert restored == [snapshot]
    assert wrong_snapshots == []


def test_resource_free_snapshot_does_not_require_release_hook():
    captured = []
    restored = []
    port = SimpleNamespace(
        capture_history_transaction_for_history=lambda: captured.append("snapshot"),
        restore_history_transaction_for_history=restored.append,
    )
    with history_command_transaction(port):
        pass
    assert captured == ["snapshot"]
    assert restored == []
