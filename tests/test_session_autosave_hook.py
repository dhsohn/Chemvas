from __future__ import annotations

from ui import session_autosave_hook
from ui.session_autosave_hook import (
    mark_quitting,
    request_snapshot,
    reset_quitting,
    set_snapshot_hook,
    snapshot_unless_quitting,
)


def test_request_is_a_no_op_when_no_hook_installed():
    set_snapshot_hook(None)
    request_snapshot()  # must not raise


def test_request_invokes_the_installed_hook():
    calls: list[int] = []
    set_snapshot_hook(lambda: calls.append(1))

    request_snapshot()
    request_snapshot()

    assert calls == [1, 1]


def test_a_failing_hook_never_propagates():
    def boom():
        raise RuntimeError("snapshot failed")

    set_snapshot_hook(boom)

    request_snapshot()  # save must never break because autosave hiccuped

    assert session_autosave_hook._snapshot_hook is boom


def test_snapshot_unless_quitting_fires_while_running():
    reset_quitting()
    calls: list[int] = []
    set_snapshot_hook(lambda: calls.append(1))

    snapshot_unless_quitting()

    assert calls == [1]


def test_snapshot_unless_quitting_is_a_noop_during_quit():
    reset_quitting()
    calls: list[int] = []
    set_snapshot_hook(lambda: calls.append(1))

    mark_quitting()  # app-wide quit in progress
    snapshot_unless_quitting()

    assert calls == []
