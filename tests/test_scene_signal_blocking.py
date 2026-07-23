from __future__ import annotations

import pytest
from chemvas.ui.scene_signal_blocking import blocked_scene_signals


class _SignalScene:
    def __init__(self, *, blocked: bool = False) -> None:
        self.blocked = blocked
        self.calls: list[bool] = []

    def signalsBlocked(self) -> bool:
        return self.blocked

    def blockSignals(self, blocked: bool) -> bool:
        self.calls.append(blocked)
        previous = self.blocked
        self.blocked = blocked
        return previous


def test_signal_blocker_blocks_body_and_restores_unblocked_scene() -> None:
    scene = _SignalScene()

    with blocked_scene_signals(scene):
        assert scene.blocked is True

    assert scene.blocked is False
    assert scene.calls == [True, False]


def test_signal_blocker_preserves_an_already_blocked_scene() -> None:
    scene = _SignalScene(blocked=True)

    with blocked_scene_signals(scene):
        assert scene.blocked is True

    assert scene.blocked is True
    assert scene.calls == [True, True]


def test_signal_blocker_restores_prior_state_when_body_raises() -> None:
    scene = _SignalScene()

    with pytest.raises(ValueError, match="body failed"):
        with blocked_scene_signals(scene):
            raise ValueError("body failed")

    assert scene.blocked is False
    assert scene.calls == [True, False]


def test_signal_blocker_requires_a_callable_setter() -> None:
    with pytest.raises(RuntimeError, match="signal-blocking setter"):
        with blocked_scene_signals(object()):
            raise AssertionError("body must not run")


def test_signal_blocker_uses_injected_ports() -> None:
    scene = _SignalScene(blocked=True)

    with blocked_scene_signals(
        object(),
        block_signals=scene.blockSignals,
        signals_blocked=scene.signalsBlocked,
    ):
        assert scene.blocked is True

    assert scene.blocked is True
    assert scene.calls == [True, True]


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
