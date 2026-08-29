from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .outcome import RestoreOutcome, validate_restore_outcome

if TYPE_CHECKING:
    from collections.abc import Callable


def add_recovery_error_note(
    original_error: BaseException,
    recovery_error: BaseException,
    *,
    phase: str,
) -> None:
    """Attach a secondary recovery failure without replacing the primary."""

    original_error.add_note(
        "Transaction recovery also encountered an error during "
        f"{phase}: {type(recovery_error).__name__}: {recovery_error}"
    )


def run_rollback_step(
    original_error: BaseException,
    phase: str,
    operation: Callable[[], Any],
    *,
    default: Any = None,
) -> Any:
    """Run one best-effort compensation step under an in-flight failure.

    Cancellation signals must remain the primary exception, so a step that
    raises is recorded as a note on *original_error* and the remaining
    compensation continues with *default* in place of its result.
    """

    try:
        return operation()
    except Exception as rollback_error:
        add_recovery_error_note(
            original_error,
            rollback_error,
            phase=phase,
        )
        return default


def restore_snapshot(
    restore: Callable[[], RestoreOutcome],
    *,
    description: str,
) -> RestoreOutcome:
    """Run one restore and require a structured authority result."""

    try:
        result = validate_restore_outcome(restore())
    except Exception as restore_error:
        return RestoreOutcome(
            authoritative=False,
            fallback_to_inverse=False,
            errors=(restore_error,),
        )
    if result.authoritative or result.errors:
        return result
    return RestoreOutcome(
        authoritative=False,
        fallback_to_inverse=result.fallback_to_inverse,
        errors=(RuntimeError(f"{description} restore was not authoritative"),),
    )


__all__ = ["add_recovery_error_note", "restore_snapshot", "run_rollback_step"]
