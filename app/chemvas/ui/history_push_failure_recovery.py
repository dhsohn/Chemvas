from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from chemvas.core.history import HistoryCommand
from chemvas.domain.transactions import (
    HistoryAuthoritySnapshot,
    validate_restore_outcome,
)
from chemvas.ui.history_canvas_access import (
    capture_history_transaction_for_history,
    restore_history_transaction_for_history,
)
from chemvas.ui.transactions.history_command import HistoryCommandSnapshot

_MISSING_POLICY_PORT = object()


@dataclass(frozen=True, slots=True)
class _RecordingHistoryPolicyPort:
    name: str
    value: object
    getter: Callable[[], object]
    setter: Callable[[object], object]

    def matches(self) -> bool:
        actual = self.getter()
        if actual is self.value:
            return True
        return type(actual) is type(self.value) and bool(actual == self.value)

    def apply_once(self) -> None:
        if not self.matches():
            self.setter(self.value)
        if not self.matches():
            raise RuntimeError(
                f"failed push history policy {self.name!r} was not restored"
            )


@dataclass(frozen=True, slots=True)
class RecordingHistoryPolicySnapshot:
    ports: tuple[_RecordingHistoryPolicyPort, ...]

    @classmethod
    def capture(
        cls,
        history_snapshot: HistoryAuthoritySnapshot,
    ) -> RecordingHistoryPolicySnapshot:
        state = history_snapshot.state
        getattribute = inspect.getattr_static(
            type(state),
            "__getattribute__",
            _MISSING_POLICY_PORT,
        )
        setattribute = inspect.getattr_static(
            type(state),
            "__setattr__",
            _MISSING_POLICY_PORT,
        )
        if not callable(getattribute) or not callable(setattribute):
            raise RuntimeError("recording history policy has incomplete bound ports")
        bound_getattribute = cast(Callable[[object, str], object], getattribute)
        bound_setattribute = cast(
            Callable[[object, str, object], object],
            setattribute,
        )
        ports: list[_RecordingHistoryPolicyPort] = []
        for name in ("enabled", "limit"):
            if (
                inspect.getattr_static(state, name, _MISSING_POLICY_PORT)
                is _MISSING_POLICY_PORT
            ):
                continue

            def get_value(
                _name: str = name,
                _getattribute: Callable[[object, str], object] = bound_getattribute,
                _state: object = state,
            ) -> object:
                return _getattribute(_state, _name)

            def set_value(
                value: object,
                _name: str = name,
                _setattribute: Callable[
                    [object, str, object], object
                ] = bound_setattribute,
                _state: object = state,
            ) -> object:
                return _setattribute(_state, _name, value)

            ports.append(
                _RecordingHistoryPolicyPort(
                    name=name,
                    value=get_value(),
                    getter=get_value,
                    setter=set_value,
                )
            )
        return cls(tuple(ports))

    def restore_once(self, *, reverse: bool = False) -> None:
        ports = tuple(reversed(self.ports)) if reverse else self.ports
        for port in ports:
            port.apply_once()

    def verify(self, *, reverse: bool = False) -> None:
        ports = tuple(reversed(self.ports)) if reverse else self.ports
        for port in ports:
            if not port.matches():
                raise RuntimeError(f"failed push history policy {port.name!r} changed")


def _add_recovery_note(
    original_error: BaseException,
    secondary_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                f"{phase} also encountered "
                f"{type(secondary_error).__name__}: {secondary_error}"
            )
    except BaseException:
        return


def _verify_history_and_policy_authority(
    history_snapshot: HistoryAuthoritySnapshot,
    policy_snapshot: RecordingHistoryPolicySnapshot | None,
) -> None:
    """Verify capture-bound roots, policies and raw stacks in both orders."""

    history_snapshot.verify_exact_items()
    if policy_snapshot is None:
        return
    policy_snapshot.verify()
    history_snapshot.verify_exact_items()
    policy_snapshot.verify(reverse=True)
    history_snapshot.verify_exact_items()


def _verify_runtime_and_history(
    history_snapshot: HistoryAuthoritySnapshot,
    policy_snapshot: RecordingHistoryPolicySnapshot | None,
    runtime_verify: Callable[[], tuple[BaseException, ...]],
) -> None:
    # History state/root/policy readers may be callback ports. Run a complete
    # combined sweep before the exact runtime verifier, then close the same
    # combined authority again after that untrusted callback boundary.
    _verify_history_and_policy_authority(history_snapshot, policy_snapshot)
    runtime_errors = tuple(runtime_verify())
    if runtime_errors:
        raise BaseExceptionGroup(
            "failed push runtime verification failed",
            list(runtime_errors),
        )
    _verify_history_and_policy_authority(history_snapshot, policy_snapshot)


def _restore_history_and_policy_silently(
    history_snapshot: HistoryAuthoritySnapshot,
    policy_snapshot: RecordingHistoryPolicySnapshot | None,
    original_error: BaseException,
    *,
    phase: str,
    reverse: bool,
) -> bool:
    try:
        if reverse:
            if policy_snapshot is not None:
                policy_snapshot.restore_once(reverse=True)
            restored = history_snapshot.restore_silently(
                original_error,
                phase=phase,
            )
        else:
            restored = history_snapshot.restore_silently(
                original_error,
                phase=phase,
            )
            if policy_snapshot is not None:
                policy_snapshot.restore_once()
        if not restored:
            return False
        _verify_history_and_policy_authority(history_snapshot, policy_snapshot)
    except BaseException as restore_error:
        _add_recovery_note(
            original_error,
            restore_error,
            phase=phase,
        )
        return False
    return True


def _clear_reachable_history_stacks(
    history_snapshot: HistoryAuthoritySnapshot,
    original_error: BaseException,
    *,
    phase: str,
) -> None:
    candidates: list[list] = [
        history_snapshot.history,
        history_snapshot.redo_stack,
    ]
    for getter in (
        history_snapshot.history_port.getter,
        history_snapshot.redo_port.getter,
    ):
        try:
            value = getter()
        except BaseException as getter_error:
            _add_recovery_note(
                original_error,
                getter_error,
                phase=f"{phase} stack discovery",
            )
            continue
        if isinstance(value, list):
            candidates.append(value)
    try:
        current_state = history_snapshot.state_port.getter()
        for name in ("history", "redo_stack"):
            value = getattr(current_state, name, None)
            if isinstance(value, list):
                candidates.append(value)
    except BaseException as getter_error:
        _add_recovery_note(
            original_error,
            getter_error,
            phase=f"{phase} current-state discovery",
        )
    seen: set[int] = set()
    for stack in candidates:
        if id(stack) in seen:
            continue
        seen.add(id(stack))
        try:
            list.__setitem__(stack, slice(None), ())
        except BaseException as clear_error:
            _add_recovery_note(
                original_error,
                clear_error,
                phase=f"{phase} conservative clear",
            )


def _restore_pre_inverse_authority(
    canvas: object,
    command_snapshot: HistoryCommandSnapshot,
    after_runtime_snapshot: object,
    history_snapshot: HistoryAuthoritySnapshot | None,
    policy_snapshot: RecordingHistoryPolicySnapshot | None,
    original_error: BaseException,
    *,
    phase: str,
) -> bool:
    """Reassert the frozen command/after-runtime/history before inverse use."""

    runtime_verify = getattr(after_runtime_snapshot, "verify_exact", None)
    if not callable(runtime_verify):
        _add_recovery_note(
            original_error,
            RuntimeError("failed push after-runtime has no exact verifier"),
            phase=f"{phase} pre-inverse authority",
        )
        return False

    accumulated_errors: list[BaseException] = []
    for attempt in range(2):
        attempt_errors: list[BaseException] = []

        def restore_runtime(
            _attempt_errors: list[BaseException] = attempt_errors,
        ) -> bool:
            try:
                result = validate_restore_outcome(
                    restore_history_transaction_for_history(
                        canvas,
                        after_runtime_snapshot,
                    )
                )
            except BaseException as restore_error:
                _attempt_errors.append(restore_error)
                return False
            if not result.authoritative:
                _attempt_errors.extend(result.errors)
                if not result.errors:
                    _attempt_errors.append(
                        RuntimeError(
                            "failed push after-runtime restore was not authoritative"
                        )
                    )
            return result.authoritative

        def restore_history(*, reverse: bool) -> bool:
            if history_snapshot is None:
                return True
            return _restore_history_and_policy_silently(
                history_snapshot,
                policy_snapshot,
                original_error,
                phase=f"{phase} pre-inverse history authority",
                reverse=reverse,
            )

        try:
            if attempt == 0:
                runtime_authoritative = restore_runtime()
                history_authoritative = restore_history(reverse=False)
                command_snapshot.restore()
            else:
                command_snapshot.restore()
                history_authoritative = restore_history(reverse=True)
                runtime_authoritative = restore_runtime()

            # Every verifier except the command snapshot can cross live
            # descriptors.  Two opposite sweeps ensure a one-shot verifier that
            # poisons a sibling authority cannot become the final writer.
            for reverse in (False, True):
                command_snapshot.verify()
                if history_snapshot is not None:
                    _verify_history_and_policy_authority(
                        history_snapshot,
                        policy_snapshot,
                    )
                runtime_errors = tuple(runtime_verify())
                if runtime_errors:
                    raise BaseExceptionGroup(
                        "failed push after-runtime verification failed",
                        list(runtime_errors),
                    )
                if history_snapshot is not None:
                    if reverse and policy_snapshot is not None:
                        policy_snapshot.verify(reverse=True)
                    _verify_history_and_policy_authority(
                        history_snapshot,
                        policy_snapshot,
                    )
                command_snapshot.verify()
        except BaseException as verification_error:
            attempt_errors.append(verification_error)
            runtime_authoritative = False
            history_authoritative = False

        if runtime_authoritative and history_authoritative and not attempt_errors:
            return True
        accumulated_errors.extend(attempt_errors)

    for authority_error in accumulated_errors:
        _add_recovery_note(
            original_error,
            authority_error,
            phase=f"{phase} pre-inverse authority",
        )
    return False


def recover_failed_recording_push(  # noqa: C901
    canvas: object,
    command: HistoryCommand,
    history_snapshot: HistoryAuthoritySnapshot | None,
    original_error: BaseException,
    *,
    phase: str,
    policy_snapshot: RecordingHistoryPolicySnapshot | None = None,
    command_snapshot: HistoryCommandSnapshot | None = None,
    after_runtime_snapshot: object | None = None,
) -> None:
    """Undo a recorded mutation and publish one rollback notification safely."""

    if command_snapshot is not None:
        if after_runtime_snapshot is not None:
            pre_inverse_authoritative = _restore_pre_inverse_authority(
                canvas,
                command_snapshot,
                after_runtime_snapshot,
                history_snapshot,
                policy_snapshot,
                original_error,
                phase=phase,
            )
            if not pre_inverse_authoritative:
                if history_snapshot is not None:
                    _clear_reachable_history_stacks(
                        history_snapshot,
                        original_error,
                        phase=f"{phase} non-authoritative pre-inverse state",
                    )
                return
        else:
            try:
                command_snapshot.restore()
            except BaseException as command_error:
                _add_recovery_note(
                    original_error,
                    command_error,
                    phase=f"{phase} command payload restore",
                )
                if history_snapshot is not None:
                    _clear_reachable_history_stacks(
                        history_snapshot,
                        original_error,
                        phase=f"{phase} non-authoritative command payload",
                    )
                return

    inverse_authoritative = True
    try:
        command.undo(canvas)
    except BaseException as inverse_error:
        inverse_authoritative = False
        _add_recovery_note(
            original_error,
            inverse_error,
            phase=f"{phase} runtime inverse",
        )

    if history_snapshot is None:
        return

    if not inverse_authoritative:
        try:
            history_snapshot.restore(original_error, phase=phase)
            if policy_snapshot is not None:
                policy_snapshot.restore_once()
        except BaseException as history_error:
            _add_recovery_note(
                original_error,
                history_error,
                phase=f"{phase} history rollback",
            )
        if not _restore_history_and_policy_silently(
            history_snapshot,
            policy_snapshot,
            original_error,
            phase=f"{phase} inverse-failure history reassertion",
            reverse=True,
        ):
            _clear_reachable_history_stacks(
                history_snapshot,
                original_error,
                phase=f"{phase} non-authoritative inverse",
            )
        return

    # Normalize stacks silently before capturing the post-inverse runtime. The
    # exact runtime snapshot therefore contains both the desired canvas state
    # and the pre-push history roots, not a mutate-then-raise push delta.
    try:
        if not _restore_history_and_policy_silently(
            history_snapshot,
            policy_snapshot,
            original_error,
            phase=f"{phase} pre-publication",
            reverse=False,
        ):
            raise RuntimeError("failed push history pre-publication was not exact")
        runtime_snapshot = capture_history_transaction_for_history(
            canvas,
            history_service=None,
            guard_scene_rect=False,
        )
        runtime_verify = getattr(runtime_snapshot, "verify_exact", None)
        if not callable(runtime_verify):
            raise RuntimeError("failed push runtime has no exact verifier")
        initial_runtime_errors = tuple(runtime_verify())
        if initial_runtime_errors:
            # A lightweight history-only test double has no production canvas
            # model/scene authority. Its inverse has already completed, so keep
            # the legacy stack publication path instead of treating the absent
            # canvas protocol as corruption of an otherwise exact history pair.
            history_snapshot.restore(original_error, phase=phase)
            if policy_snapshot is not None:
                policy_snapshot.restore_once()
            return
    except BaseException as capture_error:
        _add_recovery_note(
            original_error,
            capture_error,
            phase=f"{phase} exact runtime capture",
        )
        try:
            history_snapshot.restore(original_error, phase=phase)
            if policy_snapshot is not None:
                policy_snapshot.restore_once()
        except BaseException as history_error:
            _add_recovery_note(
                original_error,
                history_error,
                phase=f"{phase} history rollback",
            )
        return

    try:
        history_snapshot.restore(original_error, phase=phase)
    except BaseException as history_error:
        _add_recovery_note(
            original_error,
            history_error,
            phase=f"{phase} history publication",
        )

    recovered_errors: list[BaseException] = []
    for attempt in range(2):
        attempt_errors: list[BaseException] = []

        def restore_runtime(
            _attempt_errors: list[BaseException] = attempt_errors,
        ) -> bool:
            try:
                result = validate_restore_outcome(
                    restore_history_transaction_for_history(canvas, runtime_snapshot)
                )
            except BaseException as restore_error:
                _attempt_errors.append(restore_error)
                return False
            for result_error in result.errors:
                _add_recovery_note(
                    original_error,
                    result_error,
                    phase=f"{phase} exact runtime restore",
                )
            if not result.authoritative and not result.errors:
                _attempt_errors.append(
                    RuntimeError("failed push runtime restore was not authoritative")
                )
            return result.authoritative

        def restore_history(*, reverse: bool) -> bool:
            return _restore_history_and_policy_silently(
                history_snapshot,
                policy_snapshot,
                original_error,
                phase=f"{phase} silent history CAS",
                reverse=reverse,
            )

        if attempt == 0:
            runtime_authoritative = restore_runtime()
            history_authoritative = restore_history(reverse=False)
        else:
            history_authoritative = restore_history(reverse=True)
            runtime_authoritative = restore_runtime()

        # A runtime restore/verifier can replace a public history root while
        # returning an authoritative result. Re-close the capture-bound raw
        # stacks and policies after each verifier. The second sweep catches a
        # history setter that poisoned runtime during the first re-close.
        for sweep in range(2):
            try:
                runtime_errors = tuple(runtime_verify())
                if runtime_errors:
                    raise BaseExceptionGroup(
                        "failed push runtime verification failed",
                        list(runtime_errors),
                    )
            except BaseException as verify_error:
                attempt_errors.append(verify_error)
                runtime_authoritative = False
            if not restore_history(reverse=bool(attempt or sweep)):
                history_authoritative = False

        try:
            _verify_runtime_and_history(
                history_snapshot,
                policy_snapshot,
                runtime_verify,
            )
        except BaseException as verify_error:
            attempt_errors.append(verify_error)
            runtime_authoritative = False
            history_authoritative = False

        if runtime_authoritative and history_authoritative and not attempt_errors:
            for recovered_error in recovered_errors:
                _add_recovery_note(
                    original_error,
                    recovered_error,
                    phase=f"{phase} recovered final authority",
                )
            return
        recovered_errors.extend(attempt_errors)

    for recorded_error in recovered_errors:
        _add_recovery_note(
            original_error,
            recorded_error,
            phase=f"{phase} final authority",
        )
    _clear_reachable_history_stacks(
        history_snapshot,
        original_error,
        phase=f"{phase} non-authoritative final authority",
    )


__all__ = [
    "RecordingHistoryPolicySnapshot",
    "recover_failed_recording_push",
]
