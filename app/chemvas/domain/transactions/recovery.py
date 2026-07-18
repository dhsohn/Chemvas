from __future__ import annotations

from collections.abc import Callable

from .outcome import RestoreOutcome, validate_restore_outcome


def add_recovery_error_note(
    original_error: BaseException,
    recovery_error: BaseException,
    *,
    phase: str,
) -> None:
    """Attach a secondary recovery failure without replacing the primary."""

    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(
            "Transaction recovery also encountered an error during "
            f"{phase}: {type(recovery_error).__name__}: {recovery_error}"
        )
    except BaseException:
        # Diagnostics are always secondary to the exception that initiated
        # recovery, including cancellation and termination exceptions.
        return


def restore_snapshot_with_retry(
    restore: Callable[[], RestoreOutcome],
    *,
    description: str,
) -> RestoreOutcome:
    """Run at most two exact restores and require structured authority."""

    accumulated_errors: list[BaseException] = []
    fallback_to_inverse_is_safe = True
    for attempt in range(2):
        try:
            result = validate_restore_outcome(restore())
        except BaseException as restore_error:
            result = RestoreOutcome(
                authoritative=False,
                fallback_to_inverse=False,
                errors=(restore_error,),
            )
        fallback_to_inverse_is_safe = (
            fallback_to_inverse_is_safe and result.fallback_to_inverse
        )
        attempt_errors = list(result.errors)
        if result.authoritative:
            return RestoreOutcome(
                authoritative=True,
                fallback_to_inverse=False,
                errors=tuple((*accumulated_errors, *attempt_errors)),
            )
        if not attempt_errors:
            attempt_errors.append(
                RuntimeError(
                    f"{description} restore attempt {attempt + 1} was not authoritative"
                )
            )
        accumulated_errors.extend(attempt_errors)

    return RestoreOutcome(
        authoritative=False,
        fallback_to_inverse=fallback_to_inverse_is_safe,
        errors=tuple(accumulated_errors),
    )


# Compatibility names for callers that still describe these domain operations
# through the legacy UI-history vocabulary.
add_history_rollback_error_note = add_recovery_error_note
restore_history_snapshot_with_retry = restore_snapshot_with_retry


__all__ = [
    "add_history_rollback_error_note",
    "add_recovery_error_note",
    "restore_history_snapshot_with_retry",
    "restore_snapshot_with_retry",
]
