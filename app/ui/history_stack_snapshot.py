from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import cast

from ui.history_recovery_note import add_history_rollback_error_note

_MISSING_ATTRIBUTE = object()


def _capture_optional_attribute(target: object, name: str) -> object:
    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
            is not _MISSING_ATTRIBUTE
        ):
            raise
        return _MISSING_ATTRIBUTE


@dataclass(frozen=True, slots=True)
class _CapturedStackPort:
    value: list
    items: tuple
    getter: Callable[[], object]
    setter: Callable[[object], object]
    replace_items: Callable[[slice, tuple], object]
    iterate: Callable[[], Iterator]

    def apply_once(self) -> None:
        # Restore the public root first, then make the captured built-in list
        # storage the final writer.  A list subclass may override both
        # ``__setitem__`` and ``__iter__`` with callbacks; transaction authority
        # must never execute those overrides.
        self.setter(self.value)
        self.replace_items(slice(None), self.items)

    def verify(self) -> None:
        if self.getter() is not self.value:
            raise RuntimeError("history stack setter did not restore list identity")
        actual_items = tuple(self.iterate())
        if len(actual_items) != len(self.items) or any(
            actual is not expected
            for actual, expected in zip(
                actual_items,
                self.items,
                strict=False,
            )
        ):
            raise RuntimeError("history stack contents did not match the savepoint")


@dataclass(frozen=True, slots=True)
class _CapturedServiceStatePort:
    value: object
    getter: Callable[[], object]
    setter: Callable[[object], object]

    def apply_once(self) -> None:
        if self.getter() is self.value:
            return
        self.setter(self.value)

    def verify(self) -> None:
        if self.getter() is not self.value:
            raise RuntimeError(
                "history service state setter did not restore state identity"
            )


def _capture_service_state_port(
    service: object,
    state: object,
) -> _CapturedServiceStatePort:
    getattribute = inspect.getattr_static(
        type(service),
        "__getattribute__",
        _MISSING_ATTRIBUTE,
    )
    setattribute = inspect.getattr_static(
        type(service),
        "__setattr__",
        _MISSING_ATTRIBUTE,
    )
    if not callable(getattribute) or not callable(setattribute):
        raise RuntimeError("history service has incomplete state restore ports")
    getattribute_port = cast(Callable[[object, str], object], getattribute)
    setattribute_port = cast(
        Callable[[object, str, object], object],
        setattribute,
    )

    def get_state(
        _getattribute=getattribute_port,
        _service=service,
    ) -> object:
        return _getattribute(_service, "state")

    def set_state(
        value: object,
        _setattribute=setattribute_port,
        _service=service,
    ) -> object:
        return _setattribute(_service, "state", value)

    return _CapturedServiceStatePort(
        value=state,
        getter=get_state,
        setter=set_state,
    )


def _capture_stack_port(
    state: object,
    name: str,
    stack: list,
) -> _CapturedStackPort:
    getattribute = inspect.getattr_static(
        type(state),
        "__getattribute__",
        _MISSING_ATTRIBUTE,
    )
    setattribute = inspect.getattr_static(
        type(state),
        "__setattr__",
        _MISSING_ATTRIBUTE,
    )
    if not all(
        callable(port)
        for port in (
            getattribute,
            setattribute,
        )
    ):
        raise RuntimeError(f"history state has incomplete {name} restore ports")
    getattribute_port = cast(Callable[[object, str], object], getattribute)
    setattribute_port = cast(
        Callable[[object, str, object], object],
        setattribute,
    )

    def replace_items_raw(key: slice, items: tuple, _stack=stack) -> object:
        return list.__setitem__(_stack, key, items)

    def iterate_raw(_stack=stack) -> Iterator:
        return list.__iter__(_stack)

    def get_stack(
        _getattribute=getattribute_port,
        _state=state,
        _name=name,
    ) -> object:
        return _getattribute(_state, _name)

    def set_stack(
        value: object,
        _setattribute=setattribute_port,
        _state=state,
        _name=name,
    ) -> object:
        return _setattribute(_state, _name, value)

    return _CapturedStackPort(
        value=stack,
        items=tuple(iterate_raw()),
        getter=get_stack,
        setter=set_stack,
        replace_items=replace_items_raw,
        iterate=iterate_raw,
    )


@dataclass(slots=True)
class HistoryStackSnapshot:
    """Exact savepoint for a CanvasHistoryService-compatible stack pair."""

    service: object
    state: object
    history: list
    redo_stack: list
    history_items: tuple
    redo_items: tuple
    state_port: _CapturedServiceStatePort
    history_port: _CapturedStackPort
    redo_port: _CapturedStackPort
    notify_change: Callable[[], object] | None

    @classmethod
    def capture(cls, service) -> HistoryStackSnapshot | None:
        state = _capture_optional_attribute(service, "state")
        if state is _MISSING_ATTRIBUTE:
            return None
        history = _capture_optional_attribute(state, "history")
        redo_stack = _capture_optional_attribute(state, "redo_stack")
        if history is _MISSING_ATTRIBUTE or redo_stack is _MISSING_ATTRIBUTE:
            raise RuntimeError("history state has incomplete stack roots")
        if not isinstance(history, list) or not isinstance(redo_stack, list):
            raise RuntimeError(
                "history operation requires exact mutable history stacks"
            )
        if history is redo_stack:
            raise RuntimeError("history and redo stacks must not alias")
        state_port = _capture_service_state_port(service, state)
        history_port = _capture_stack_port(state, "history", history)
        redo_port = _capture_stack_port(state, "redo_stack", redo_stack)
        notify_change_value = _capture_optional_attribute(service, "notify_change")
        return cls(
            service=service,
            state=state,
            history=history,
            redo_stack=redo_stack,
            history_items=history_port.items,
            redo_items=redo_port.items,
            state_port=state_port,
            history_port=history_port,
            redo_port=redo_port,
            notify_change=(
                notify_change_value if callable(notify_change_value) else None
            ),
        )

    def _restore_exact(self) -> tuple[bool, tuple[BaseException, ...]]:
        errors: list[BaseException] = []
        for attempt in range(2):
            try:
                restore_order = (
                    (self.state_port, self.history_port, self.redo_port)
                    if attempt == 0
                    else (self.redo_port, self.history_port, self.state_port)
                )
                for port in restore_order:
                    port.apply_once()
                self.verify_exact_items()
            except BaseException as restore_error:
                errors.append(restore_error)
                continue
            return True, tuple(errors)
        return False, tuple(errors)

    @staticmethod
    def _report_errors(
        original_error: BaseException,
        errors: tuple[BaseException, ...],
        *,
        phase: str,
    ) -> None:
        for recorded_error in errors:
            add_history_rollback_error_note(
                original_error,
                recorded_error,
                phase=phase,
            )

    def restore(self, original_error: BaseException, *, phase: str) -> bool:
        restored, restore_errors = self._restore_exact()
        self._report_errors(
            original_error,
            restore_errors,
            phase=f"restoring {phase} exact history stacks",
        )
        if not restored:
            return False

        if restore_errors:
            # Attaching diagnostics is an untrusted callback boundary. A
            # custom BaseException.add_note implementation can replace roots
            # after the successful retry that produced ``restored``. Close
            # once more without invoking diagnostics after that final pass.
            restored, closing_errors = self._restore_exact()
            if not restored:
                self._report_errors(
                    original_error,
                    closing_errors,
                    phase=(f"closing {phase} exact history stacks after diagnostics"),
                )
                return False

        notify_change = self.notify_change
        if notify_change is None:
            return True

        try:
            # Publication is deliberately one-shot. A callback may mutate the
            # stacks before returning or may mutate and then raise; either way,
            # the silent exact pass below is the final authority and must never
            # notify that same observer a second time.
            notify_change()
        except BaseException as notification_error:
            add_history_rollback_error_note(
                original_error,
                notification_error,
                phase=f"notifying observers after {phase} history rollback",
            )

        reasserted, reassert_errors = self._restore_exact()
        self._report_errors(
            original_error,
            reassert_errors,
            phase=(f"reasserting {phase} exact history stacks after notification"),
        )
        if not reasserted:
            return False
        if not reassert_errors:
            return True

        # As above, recovered retry diagnostics run after an exact pass. Make
        # a silent pass the final writer so note callbacks cannot win.
        closed, closing_errors = self._restore_exact()
        if not closed:
            self._report_errors(
                original_error,
                closing_errors,
                phase=(
                    f"closing {phase} exact history stacks after reassertion "
                    "diagnostics"
                ),
            )
        return closed

    def restore_silently(
        self,
        original_error: BaseException,
        *,
        phase: str,
    ) -> bool:
        restored, restore_errors = self._restore_exact()
        self._report_errors(
            original_error,
            restore_errors,
            phase=f"silently restoring {phase} exact history stacks",
        )
        if not restored or not restore_errors:
            return restored

        # Even this nominally silent helper retains recovered restore failures
        # as diagnostics.  ``BaseException.add_note`` is an untrusted callback
        # boundary and can replace a stack/state root after the successful
        # retry above.  Close once more without reporting anything after the
        # final exact pass; otherwise callers can receive ``True`` while the
        # public history root no longer points at the captured list.
        closed, closing_errors = self._restore_exact()
        if not closed:
            self._report_errors(
                original_error,
                closing_errors,
                phase=(
                    f"closing silent {phase} exact history stacks after diagnostics"
                ),
            )
        return closed

    def is_exact(self) -> bool:
        try:
            self.verify_exact_items()
        except BaseException:
            return False
        return True

    @staticmethod
    def _same_identity_items(
        actual: tuple[object, ...],
        expected: tuple[object, ...],
    ) -> bool:
        return len(actual) == len(expected) and all(
            item is expected_item
            for item, expected_item in zip(actual, expected, strict=False)
        )

    def verify_exact_items(
        self,
        *,
        history_items: tuple[object, ...] | None = None,
        redo_items: tuple[object, ...] | None = None,
    ) -> None:
        """Verify roots first and raw built-in list storage last."""

        expected_history = (
            self.history_items if history_items is None else history_items
        )
        expected_redo = self.redo_items if redo_items is None else redo_items

        def verify_history_root() -> None:
            if self.history_port.getter() is not self.history:
                raise RuntimeError("history stack setter did not restore list identity")

        def verify_redo_root() -> None:
            if self.redo_port.getter() is not self.redo_stack:
                raise RuntimeError("redo stack setter did not restore list identity")

        # Public state/stack readers are callback boundaries.  One reader can
        # return its expected value while replacing a root already checked in
        # the same sweep.  Verify the capture-bound roots in both directions
        # before closing on callback-free built-in list storage.
        root_verifiers = (
            self.state_port.verify,
            verify_history_root,
            verify_redo_root,
        )
        for _sweep in range(2):
            for verifier in root_verifiers:
                verifier()
            for verifier in reversed(root_verifiers):
                verifier()
        actual_history = tuple(self.history_port.iterate())
        actual_redo = tuple(self.redo_port.iterate())
        if not self._same_identity_items(actual_history, expected_history):
            raise RuntimeError("history stack contents did not match the savepoint")
        if not self._same_identity_items(actual_redo, expected_redo):
            raise RuntimeError("redo stack contents did not match the savepoint")


__all__ = ["HistoryStackSnapshot"]
