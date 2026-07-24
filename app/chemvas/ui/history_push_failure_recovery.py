from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chemvas.core.history import HistoryCommand
from chemvas.domain.transactions import (
    HistoryAuthoritySnapshot,
    validate_restore_outcome,
)
from chemvas.ui.history_canvas_access import (
    restore_history_transaction_for_history,
)
from chemvas.ui.transactions.history_command import HistoryCommandSnapshot

_MISSING_POLICY_VALUE = object()


@dataclass(frozen=True, slots=True)
class RecordingHistoryPolicySnapshot:
    """The recording policy (enabled flag, stack limit) frozen at capture."""

    state: Any
    values: tuple[tuple[str, object], ...]

    @classmethod
    def capture(
        cls,
        history_snapshot: HistoryAuthoritySnapshot,
    ) -> RecordingHistoryPolicySnapshot:
        state = history_snapshot.state
        values = tuple(
            (name, getattr(state, name))
            for name in ("enabled", "limit")
            if getattr(state, name, _MISSING_POLICY_VALUE) is not _MISSING_POLICY_VALUE
        )
        return cls(state=state, values=values)

    def restore_once(self) -> None:
        for name, value in self.values:
            if getattr(self.state, name) != value:
                setattr(self.state, name, value)

    def verify(self) -> None:
        for name, value in self.values:
            actual = getattr(self.state, name)
            if actual is not value and actual != value:
                raise RuntimeError(f"failed push history policy {name!r} changed")


def _add_recovery_note(
    original_error: BaseException,
    secondary_error: BaseException,
    *,
    phase: str,
) -> None:
    original_error.add_note(
        f"{phase} also encountered {type(secondary_error).__name__}: {secondary_error}"
    )


def _clear_history_stacks_fail_closed(
    history_snapshot: HistoryAuthoritySnapshot,
    original_error: BaseException,
    *,
    phase: str,
) -> None:
    # The stacks no longer describe the document; empty them in place rather
    # than exposing commands that would replay against unknown state.
    for stack in (history_snapshot.history, history_snapshot.redo_stack):
        try:
            stack[:] = []
        except BaseException as clear_error:
            _add_recovery_note(
                original_error,
                clear_error,
                phase=f"{phase} conservative clear",
            )


def _restore_history_and_policy(
    history_snapshot: HistoryAuthoritySnapshot,
    policy_snapshot: RecordingHistoryPolicySnapshot | None,
    original_error: BaseException,
    *,
    phase: str,
) -> bool:
    try:
        if not history_snapshot.restore_silently(original_error, phase=phase):
            return False
        if policy_snapshot is not None:
            policy_snapshot.restore_once()
        history_snapshot.verify_exact_items()
        if policy_snapshot is not None:
            policy_snapshot.verify()
    except BaseException as restore_error:
        _add_recovery_note(original_error, restore_error, phase=phase)
        return False
    return True


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

    authoritative = True
    errors: list[BaseException] = []
    try:
        result = validate_restore_outcome(
            restore_history_transaction_for_history(canvas, after_runtime_snapshot)
        )
        errors.extend(result.errors)
        if not result.authoritative:
            authoritative = False
            if not result.errors:
                errors.append(
                    RuntimeError(
                        "failed push after-runtime restore was not authoritative"
                    )
                )
    except BaseException as restore_error:
        errors.append(restore_error)
        authoritative = False
    try:
        if history_snapshot is not None and not _restore_history_and_policy(
            history_snapshot,
            policy_snapshot,
            original_error,
            phase=f"{phase} pre-inverse history authority",
        ):
            authoritative = False
        command_snapshot.restore()
        command_snapshot.verify()
    except BaseException as command_error:
        errors.append(command_error)
        authoritative = False
    for authority_error in errors:
        _add_recovery_note(
            original_error,
            authority_error,
            phase=f"{phase} pre-inverse authority",
        )
    return authoritative


def recover_failed_recording_push(
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
    """Undo a recorded mutation and publish one rollback notification safely.

    Restore once, verify once, and fail closed: when any restore is not
    authoritative the captured stacks are emptied in place instead of
    exposing commands that no longer describe the document.
    """

    if command_snapshot is not None:
        if after_runtime_snapshot is not None:
            if not _restore_pre_inverse_authority(
                canvas,
                command_snapshot,
                after_runtime_snapshot,
                history_snapshot,
                policy_snapshot,
                original_error,
                phase=phase,
            ):
                if history_snapshot is not None:
                    _clear_history_stacks_fail_closed(
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
                    _clear_history_stacks_fail_closed(
                        history_snapshot,
                        original_error,
                        phase=f"{phase} non-authoritative command payload",
                    )
                return

    try:
        command.undo(canvas)
    except BaseException as inverse_error:
        _add_recovery_note(
            original_error,
            inverse_error,
            phase=f"{phase} runtime inverse",
        )

    if history_snapshot is None:
        return

    # Restore the pre-push stacks in place first, then publish one rollback
    # notification; a notification failure (or a failed inverse whose stacks
    # still restored exactly) is a note, not a reason to drop already-exact
    # stacks. Only a failed stack restore leaves stacks that cannot describe
    # the document, so only that empties them fail-closed.
    stacks_restored = _restore_history_and_policy(
        history_snapshot,
        policy_snapshot,
        original_error,
        phase=f"{phase} history rollback",
    )
    if stacks_restored:
        try:
            history_snapshot.restore(original_error, phase=phase)
        except BaseException as publication_error:
            _add_recovery_note(
                original_error,
                publication_error,
                phase=f"{phase} rollback publication",
            )
    if not stacks_restored:
        _clear_history_stacks_fail_closed(
            history_snapshot,
            original_error,
            phase=f"{phase} non-authoritative inverse",
        )


__all__ = [
    "RecordingHistoryPolicySnapshot",
    "recover_failed_recording_push",
]
