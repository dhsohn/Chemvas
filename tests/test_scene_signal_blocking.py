from __future__ import annotations

import pytest
from chemvas.ui.scene_signal_blocking import blocked_scene_signals


class _SignalScene:
    def __init__(self, *, blocked: bool = False) -> None:
        self.blocked = blocked
        self.calls: list[bool] = []
        self.ignore_next = False
        self.ignore_restore = False
        self.raise_next: BaseException | None = None

    def signalsBlocked(self) -> bool:
        return self.blocked

    def blockSignals(self, blocked: bool) -> bool:
        self.calls.append(blocked)
        previous = self.blocked
        if self.raise_next is not None:
            error = self.raise_next
            self.raise_next = None
            raise error
        if self.ignore_next:
            self.ignore_next = False
            return previous
        if not (self.ignore_restore and blocked is False):
            self.blocked = blocked
        return previous


def test_signal_block_entry_persistent_no_op_does_not_run_body() -> None:
    scene = _SignalScene()
    body_calls = 0

    def ignore_all_changes(blocked: bool) -> bool:
        scene.calls.append(blocked)
        return scene.blocked

    scene.blockSignals = ignore_all_changes  # type: ignore[method-assign]

    with pytest.raises(
        RuntimeError,
        match="setter did not apply the requested state",
    ):
        with blocked_scene_signals(scene):
            body_calls += 1

    assert body_calls == 0
    assert scene.blocked is False
    assert scene.calls == [True, True, False]


def test_signal_block_entry_recovers_from_one_no_op_before_body() -> None:
    scene = _SignalScene()
    scene.ignore_next = True

    with blocked_scene_signals(scene):
        assert scene.blocked is True

    assert scene.blocked is False
    assert scene.calls == [True, True, False]


def test_signal_block_exit_recovers_from_one_setter_failure() -> None:
    scene = _SignalScene()

    with blocked_scene_signals(scene):
        scene.raise_next = SystemExit("restore interrupted")

    assert scene.blocked is False
    assert scene.calls == [True, False, False]


def test_signal_block_exit_persistent_no_op_raises_after_normal_body() -> None:
    scene = _SignalScene()

    with pytest.raises(
        RuntimeError,
        match="setter did not apply the requested state",
    ):
        with blocked_scene_signals(scene):
            scene.ignore_restore = True

    assert scene.blocked is True
    assert scene.calls == [True, False, False]


def test_signal_block_exit_failure_preserves_body_base_exception_identity() -> None:
    scene = _SignalScene()
    primary = KeyboardInterrupt("body interrupted")

    with pytest.raises(KeyboardInterrupt) as caught:
        with blocked_scene_signals(scene):
            scene.ignore_restore = True
            raise primary

    assert caught.value is primary
    assert scene.blocked is True
    assert len(primary.__notes__) == 2
    assert all("signal recovery also failed" in note for note in primary.__notes__)


def test_signal_ports_are_captured_once_for_the_full_context() -> None:
    class DescriptorScene:
        def __init__(self) -> None:
            self.blocked = False
            self.lookup_counts = {"blockSignals": 0, "signalsBlocked": 0}
            self.fail_lookup = False

        @property
        def blockSignals(self):
            self.lookup_counts["blockSignals"] += 1
            if self.fail_lookup:
                raise AssertionError("blockSignals port was looked up again")
            return self._block_signals

        @property
        def signalsBlocked(self):
            self.lookup_counts["signalsBlocked"] += 1
            if self.fail_lookup:
                raise AssertionError("signalsBlocked port was looked up again")
            return self._signals_blocked

        def _block_signals(self, blocked: bool) -> bool:
            previous = self.blocked
            self.blocked = blocked
            return previous

        def _signals_blocked(self) -> bool:
            return self.blocked

    scene = DescriptorScene()
    with blocked_scene_signals(scene):
        scene.fail_lookup = True
        assert scene.blocked is True

    assert scene.blocked is False
    assert scene.lookup_counts == {"blockSignals": 1, "signalsBlocked": 1}


def test_signal_blocker_without_state_getter_retains_return_value_fallback() -> None:
    class SetterOnlyScene:
        def __init__(self) -> None:
            self.blocked = True

        def blockSignals(self, blocked: bool) -> bool:
            previous = self.blocked
            self.blocked = blocked
            return previous

    scene = SetterOnlyScene()
    with blocked_scene_signals(scene):
        assert scene.blocked is True

    assert scene.blocked is True
