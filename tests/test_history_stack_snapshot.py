from __future__ import annotations

from types import SimpleNamespace

import pytest
from ui.history_stack_snapshot import HistoryStackSnapshot


@pytest.mark.parametrize(
    "notify_error",
    (
        SystemExit("notify lookup terminated"),
        KeyboardInterrupt("notify lookup interrupted"),
    ),
)
def test_capture_preflights_notify_descriptor_before_any_mutation(
    notify_error: BaseException,
) -> None:
    old_history_entry = object()
    old_redo_entry = object()
    history = [old_history_entry]
    redo_stack = [old_redo_entry]
    state = SimpleNamespace(history=history, redo_stack=redo_stack)

    class _HistoryService:
        @property
        def notify_change(self):
            raise notify_error

    service = _HistoryService()
    service.state = state

    with pytest.raises(type(notify_error)) as raised:
        HistoryStackSnapshot.capture(service)

    assert raised.value is notify_error
    assert state.history is history
    assert state.redo_stack is redo_stack
    assert history == [old_history_entry]
    assert redo_stack == [old_redo_entry]


def test_restore_recovers_replaced_service_state_identity() -> None:
    old_history_entry = object()
    old_redo_entry = object()
    history = [old_history_entry]
    redo_stack = [old_redo_entry]
    original_state = SimpleNamespace(history=history, redo_stack=redo_stack)
    replacement_state = SimpleNamespace(history=[object()], redo_stack=[])
    notifications = 0

    class Service:
        def notify_change(self) -> None:
            nonlocal notifications
            notifications += 1

    service = Service()
    service.state = original_state
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    history.clear()
    redo_stack.clear()
    service.state = replacement_state
    primary = RuntimeError("push replaced history state before failing")

    snapshot.restore(primary, phase="replaced service state")

    assert service.state is original_state
    assert original_state.history is history
    assert original_state.redo_stack is redo_stack
    assert history == [old_history_entry]
    assert redo_stack == [old_redo_entry]
    assert notifications == 1
    assert not getattr(primary, "__notes__", [])


@pytest.mark.parametrize(
    ("behavior", "restored", "expected_notes"),
    (
        ("fail_once", True, 1),
        ("no_op_once", True, 1),
        ("persistent_no_op", False, 2),
    ),
)
def test_service_state_restore_retries_and_verifies_identity(
    behavior: str,
    restored: bool,
    expected_notes: int,
) -> None:
    history_entry = object()
    redo_entry = object()
    history = [history_entry]
    redo_stack = [redo_entry]
    original_state = SimpleNamespace(history=history, redo_stack=redo_stack)
    replacement_state = SimpleNamespace(history=[object()], redo_stack=[])
    notifications = 0

    class Service:
        def __init__(self) -> None:
            self._state = original_state
            self.behavior = "normal"
            self.setter_calls = 0

        @property
        def state(self):
            return self._state

        @state.setter
        def state(self, value) -> None:
            self.setter_calls += 1
            if self.behavior == "persistent_no_op":
                return
            if self.behavior == "no_op_once" and self.setter_calls == 1:
                return
            self._state = value
            if self.behavior == "fail_once" and self.setter_calls == 1:
                raise KeyboardInterrupt("service state restore failed after mutation")

        def notify_change(self) -> None:
            nonlocal notifications
            notifications += 1

    service = Service()
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    history.clear()
    redo_stack.clear()
    service._state = replacement_state
    service.behavior = behavior
    primary = SystemExit("push failed with a replacement history state")

    snapshot.restore(primary, phase="service state identity")

    assert history == [history_entry]
    assert redo_stack == [redo_entry]
    assert (service.state is original_state) is restored
    assert notifications == int(restored)
    assert len(getattr(primary, "__notes__", [])) == expected_notes


@pytest.mark.parametrize(
    ("corrupting_port", "restored", "expected_notes"),
    (
        ("service", True, 0),
        ("history", True, 2),
        ("both", False, 2),
    ),
)
def test_alternating_restore_order_handles_service_state_cross_corruption(
    corrupting_port: str,
    restored: bool,
    expected_notes: int,
) -> None:
    history_entry = object()
    redo_entry = object()
    history = [history_entry]
    redo_stack = [redo_entry]
    replacement_state = SimpleNamespace(history=[object()], redo_stack=[])
    notifications = 0

    class Service:
        def __init__(self) -> None:
            self._state = None
            self.corrupting_port = "none"

        @property
        def state(self):
            return self._state

        @state.setter
        def state(self, value) -> None:
            self._state = value
            if value is original_state and self.corrupting_port in {"service", "both"}:
                history[:] = [object()]

        def notify_change(self) -> None:
            nonlocal notifications
            notifications += 1

    service = Service()

    class State:
        def __init__(self) -> None:
            self._history = history
            self._redo_stack = redo_stack

        @property
        def history(self):
            return self._history

        @history.setter
        def history(self, value) -> None:
            self._history = value
            if service.corrupting_port in {"history", "both"}:
                service._state = replacement_state

        @property
        def redo_stack(self):
            return self._redo_stack

        @redo_stack.setter
        def redo_stack(self, value) -> None:
            self._redo_stack = value

    original_state = State()
    service._state = original_state
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    history.clear()
    redo_stack.clear()
    service._state = replacement_state
    service.corrupting_port = corrupting_port
    primary = RuntimeError("history state and stack setters cross-corrupted")

    snapshot.restore(primary, phase="state/stack cross-corruption")

    if restored:
        assert service.state is original_state
        assert history == [history_entry]
        assert redo_stack == [redo_entry]
        assert notifications == 1
    else:
        assert (
            service.state is not original_state
            or history != [history_entry]
            or redo_stack != [redo_entry]
        )
        assert notifications == 0
    assert len(getattr(primary, "__notes__", [])) == expected_notes


@pytest.mark.parametrize(
    ("list_behavior", "state_behavior"),
    (
        ("fail_once", "normal"),
        ("no_op_once", "normal"),
        ("normal", "fail_once"),
        ("normal", "no_op_once"),
    ),
)
def test_restore_retries_and_verifies_stack_contents_and_identity(
    list_behavior: str,
    state_behavior: str,
) -> None:
    class FlakyList(list):
        def __init__(self, values) -> None:
            super().__init__(values)
            self.behavior = "normal"
            self.restore_calls = 0

        def __setitem__(self, key, value) -> None:
            if isinstance(key, slice) and self.behavior != "normal":
                self.restore_calls += 1
                if self.behavior == "no_op_once" and self.restore_calls == 1:
                    return
                if self.behavior == "fail_once" and self.restore_calls == 1:
                    super().__setitem__(key, value)
                    self.append(object())
                    raise KeyboardInterrupt("history contents failed after mutation")
            super().__setitem__(key, value)

    class FlakyState:
        def __init__(self, history, redo_stack) -> None:
            self._history = history
            self._redo_stack = redo_stack
            self.behavior = "normal"
            self.setter_calls = 0

        @property
        def history(self):
            return self._history

        @history.setter
        def history(self, value) -> None:
            self.setter_calls += 1
            if self.behavior == "no_op_once" and self.setter_calls == 1:
                return
            self._history = value
            if self.behavior == "fail_once" and self.setter_calls == 1:
                raise SystemExit("history identity failed after mutation")

        @property
        def redo_stack(self):
            return self._redo_stack

        @redo_stack.setter
        def redo_stack(self, value) -> None:
            self._redo_stack = value

    old_history_entry = object()
    old_redo_entry = object()
    history = FlakyList([old_history_entry])
    redo_stack = FlakyList([old_redo_entry])
    state = FlakyState(history, redo_stack)
    notifications = 0

    class Service:
        def notify_change(self) -> None:
            nonlocal notifications
            notifications += 1

    service = Service()
    service.state = state
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    history[:] = [object(), object()]
    redo_stack.clear()
    state._history = [object()]
    state._redo_stack = [object()]
    history.behavior = list_behavior
    state.behavior = state_behavior
    primary = RuntimeError("push failed after partial mutation")

    snapshot.restore(primary, phase="adversarial")

    assert state.history is history
    assert state.redo_stack is redo_stack
    assert history == [old_history_entry]
    assert redo_stack == [old_redo_entry]
    assert notifications == 1
    if state_behavior == "normal":
        # Built-in list storage is the callback-free final authority; subclass
        # slice overrides are deliberately never invoked.
        assert getattr(primary, "__notes__", []) == []
        assert history.restore_calls == 0
    else:
        assert getattr(primary, "__notes__", [])


@pytest.mark.parametrize("failure_source", ("contents", "identity"))
def test_persistent_stack_restore_failure_skips_notification(
    failure_source: str,
) -> None:
    class NoOpList(list):
        no_op = False

        def __setitem__(self, key, value) -> None:
            if self.no_op and isinstance(key, slice):
                return
            super().__setitem__(key, value)

    class NoOpState:
        def __init__(self, history, redo_stack) -> None:
            self._history = history
            self._redo_stack = redo_stack
            self.no_op = False

        @property
        def history(self):
            return self._history

        @history.setter
        def history(self, value) -> None:
            if not self.no_op:
                self._history = value

        @property
        def redo_stack(self):
            return self._redo_stack

        @redo_stack.setter
        def redo_stack(self, value) -> None:
            self._redo_stack = value

    old_history_entry = object()
    history = NoOpList([old_history_entry])
    redo_stack = NoOpList([])
    state = NoOpState(history, redo_stack)
    notifications = 0

    class Service:
        def notify_change(self) -> None:
            nonlocal notifications
            notifications += 1

    service = Service()
    service.state = state
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    history[:] = [object()]
    state._history = [object()]
    if failure_source == "contents":
        history.no_op = True
    else:
        state.no_op = True
    primary = SystemExit("primary mutation terminated")

    authoritative = snapshot.restore(primary, phase="persistent")

    if failure_source == "contents":
        assert authoritative is True
        assert notifications == 1
        assert history == [old_history_entry]
        assert getattr(primary, "__notes__", []) == []
    else:
        assert authoritative is False
        assert notifications == 0
        assert len(getattr(primary, "__notes__", [])) == 2
        assert state.history is not history


@pytest.mark.parametrize(
    ("corrupting_setter", "restored", "expected_notes"),
    (
        ("history", True, 0),
        ("redo", True, 2),
        ("both", False, 2),
    ),
)
def test_alternating_restore_order_handles_cross_stack_corruption(
    corrupting_setter: str,
    restored: bool,
    expected_notes: int,
) -> None:
    old_history_entry = object()
    old_redo_entry = object()
    history = [old_history_entry]
    redo_stack = [old_redo_entry]

    class CrossCorruptingState:
        def __init__(self) -> None:
            self._history = history
            self._redo_stack = redo_stack
            self.corrupting_setter = "none"

        @property
        def history(self):
            return self._history

        @history.setter
        def history(self, value) -> None:
            self._history = value
            if self.corrupting_setter in {"history", "both"}:
                redo_stack[:] = [object()]

        @property
        def redo_stack(self):
            return self._redo_stack

        @redo_stack.setter
        def redo_stack(self, value) -> None:
            self._redo_stack = value
            if self.corrupting_setter in {"redo", "both"}:
                history[:] = [object()]

    notifications = 0

    class Service:
        def notify_change(self) -> None:
            nonlocal notifications
            notifications += 1

    state = CrossCorruptingState()
    service = Service()
    service.state = state
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    history.clear()
    redo_stack.clear()
    state.corrupting_setter = corrupting_setter
    primary = RuntimeError("history push interrupted")

    authoritative = snapshot.restore(primary, phase="cross-corruption")

    assert authoritative is restored
    assert state.history is history
    assert state.redo_stack is redo_stack
    if restored:
        assert history == [old_history_entry]
        assert redo_stack == [old_redo_entry]
        assert notifications == 1
    else:
        assert history != [old_history_entry] or redo_stack != [old_redo_entry]
        assert notifications == 0
    assert len(getattr(primary, "__notes__", [])) == expected_notes


@pytest.mark.parametrize("mutation", ("state", "history", "redo"))
def test_notification_mutation_is_silently_reasserted_once(mutation: str) -> None:
    history_entry = object()
    redo_entry = object()
    history = [history_entry]
    redo_stack = [redo_entry]
    original_state = SimpleNamespace(history=history, redo_stack=redo_stack)
    replacement_state = SimpleNamespace(history=[object()], redo_stack=[object()])
    notifications = 0

    class Service:
        state = original_state

        def notify_change(self) -> None:
            nonlocal notifications
            notifications += 1
            if mutation == "state":
                self.state = replacement_state
            elif mutation == "history":
                history[:] = [object()]
            else:
                redo_stack[:] = [object()]

    service = Service()
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    history.clear()
    redo_stack.clear()
    primary = RuntimeError("history mutation failed")

    assert snapshot.restore(primary, phase="notification mutation")

    assert notifications == 1
    assert service.state is original_state
    assert original_state.history is history
    assert original_state.redo_stack is redo_stack
    assert history == [history_entry]
    assert redo_stack == [redo_entry]
    assert not getattr(primary, "__notes__", [])


def test_raising_notification_is_not_retried_and_mutation_is_reasserted() -> None:
    history_entry = object()
    history = [history_entry]
    redo_stack: list[object] = []
    state = SimpleNamespace(history=history, redo_stack=redo_stack)
    notification_error = SystemExit("observer terminated after mutation")
    notifications = 0

    class Service:
        def notify_change(self) -> None:
            nonlocal notifications
            notifications += 1
            history.clear()
            redo_stack.append(object())
            raise notification_error

    service = Service()
    service.state = state
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    history.clear()
    primary = KeyboardInterrupt("history command interrupted")

    assert snapshot.restore(primary, phase="raising notification")

    assert notifications == 1
    assert history == [history_entry]
    assert redo_stack == []
    assert len(getattr(primary, "__notes__", [])) == 1
    assert "observer terminated after mutation" in primary.__notes__[0]


def test_stack_getter_cannot_replace_service_state_after_earlier_root_check() -> None:
    history = [object()]
    redo_stack = [object()]
    replacement_state = SimpleNamespace(history=[object()], redo_stack=[object()])

    class Service:
        state: object

    service = Service()

    class CrossRootState:
        def __init__(self) -> None:
            self._history = history
            self._redo_stack = redo_stack
            self.poison_state = False

        @property
        def history(self) -> list[object]:
            return self._history

        @history.setter
        def history(self, value: list[object]) -> None:
            self._history = value

        @property
        def redo_stack(self) -> list[object]:
            if self.poison_state:
                service.state = replacement_state
            return self._redo_stack

        @redo_stack.setter
        def redo_stack(self, value: list[object]) -> None:
            self._redo_stack = value

    state = CrossRootState()
    service.state = state
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    state.poison_state = True

    restored = snapshot.restore_silently(
        RuntimeError("cross-root reader poisoned history authority"),
        phase="cross-root reader poisoning",
    )

    assert not restored
    assert service.state is replacement_state


def test_recovered_restore_closes_again_after_hostile_diagnostic_callback() -> None:
    history_entry = object()
    history = [history_entry]
    redo_stack: list[object] = []

    class State:
        pass

    state = State()
    state.history = history
    state.redo_stack = redo_stack

    class Service:
        def __init__(self) -> None:
            self._state = state
            self.fail_next_set = False

        @property
        def state(self):
            return self._state

        @state.setter
        def state(self, value) -> None:
            self._state = value
            if self.fail_next_set:
                self.fail_next_set = False
                raise KeyboardInterrupt("transient state restore failure")

    service = Service()
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    service._state = SimpleNamespace(history=[], redo_stack=[])
    service.fail_next_set = True
    replacement_history = [object()]

    class HostilePrimary(SystemExit):
        def add_note(self, _note: str) -> None:
            state.history = replacement_history

    restored = snapshot.restore(
        HostilePrimary("primary history failure"),
        phase="diagnostic callback",
    )

    assert restored
    assert service.state is state
    assert state.history is history
    assert state.redo_stack is redo_stack
    assert tuple(list.__iter__(history)) == (history_entry,)


def test_recovered_silent_restore_closes_after_hostile_diagnostic_callback() -> None:
    history_entry = object()
    history = [history_entry]
    redo_stack: list[object] = []

    class State:
        pass

    state = State()
    state.history = history
    state.redo_stack = redo_stack

    class Service:
        def __init__(self) -> None:
            self._state = state
            self.fail_next_set = False

        @property
        def state(self):
            return self._state

        @state.setter
        def state(self, value) -> None:
            self._state = value
            if self.fail_next_set:
                self.fail_next_set = False
                raise KeyboardInterrupt("transient silent state restore failure")

    service = Service()
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    service._state = SimpleNamespace(history=[], redo_stack=[])
    service.fail_next_set = True
    replacement_history = [object()]

    class HostilePrimary(SystemExit):
        def add_note(self, _note: str) -> None:
            state.history = replacement_history

    restored = snapshot.restore_silently(
        HostilePrimary("primary history failure"),
        phase="silent diagnostic callback",
    )

    assert restored
    assert service.state is state
    assert state.history is history
    assert state.redo_stack is redo_stack
    assert tuple(list.__iter__(history)) == (history_entry,)


def test_final_state_getter_pollution_is_caught_by_closing_root_sweep() -> None:
    history_entry = object()
    history = [history_entry]
    redo_stack: list[object] = []
    replacement_history = [object()]
    state = SimpleNamespace(history=history, redo_stack=redo_stack)

    class Service:
        def __init__(self) -> None:
            object.__setattr__(self, "state", state)
            object.__setattr__(self, "armed", False)
            object.__setattr__(self, "state_reads", 0)

        def __getattribute__(self, name: str):
            if name == "state":
                captured_state = object.__getattribute__(self, "state")
                if object.__getattribute__(self, "armed"):
                    reads = object.__getattribute__(self, "state_reads") + 1
                    object.__setattr__(self, "state_reads", reads)
                    if reads == 3:
                        captured_state.history = replacement_history
                return captured_state
            return object.__getattribute__(self, name)

    service = Service()
    snapshot = HistoryStackSnapshot.capture(service)
    assert snapshot is not None
    service.armed = True

    restored = snapshot.restore_silently(
        RuntimeError("last getter polluted an earlier root"),
        phase="closing root sweep",
    )

    assert restored
    assert object.__getattribute__(service, "state") is state
    assert state.history is history
    assert tuple(list.__iter__(history)) == (history_entry,)
