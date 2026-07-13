from __future__ import annotations

from ui import session_autosave_hook
from ui.session_autosave_hook import request_snapshot, set_snapshot_hook


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
