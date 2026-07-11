from __future__ import annotations

from collections.abc import Callable

from core.history import (
    HistoryTransactionRestoreResult,
    validate_history_transaction_restore_result,
)


def restore_history_snapshot_with_retry(
    restore: Callable[[], HistoryTransactionRestoreResult],
    *,
    description: str,
) -> HistoryTransactionRestoreResult:
    """Run at most two exact restores and require structured authority.

    Errors from a recovered first attempt remain available to the owner as
    secondary diagnostics. A silent non-authoritative result is converted to
    an explicit error so persistent partial restores can never look clean.
    """

    accumulated_errors: list[BaseException] = []
    fallback_to_inverse_is_safe = True
    for attempt in range(2):
        try:
            result = validate_history_transaction_restore_result(restore())
        except BaseException as restore_error:
            result = HistoryTransactionRestoreResult(
                authoritative=False,
                fallback_to_inverse=False,
                errors=(restore_error,),
            )
        fallback_to_inverse_is_safe = (
            fallback_to_inverse_is_safe and result.fallback_to_inverse
        )
        attempt_errors = list(result.errors)
        if result.authoritative:
            return HistoryTransactionRestoreResult(
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

    return HistoryTransactionRestoreResult(
        authoritative=False,
        fallback_to_inverse=fallback_to_inverse_is_safe,
        errors=tuple(accumulated_errors),
    )


__all__ = ["restore_history_snapshot_with_retry"]
