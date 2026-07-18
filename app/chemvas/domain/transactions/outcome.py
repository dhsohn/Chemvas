from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RestoreOutcome:
    """Result of one absolute transaction restore attempt.

    ``authoritative`` means the complete absolute snapshot was restored.
    ``fallback_to_inverse`` is deliberately independent: a failed absolute
    restore may already have mutated state, in which case applying a relative
    inverse would be unsafe. Secondary failures are retained in ``errors``.
    """

    authoritative: bool
    fallback_to_inverse: bool = False
    errors: tuple[BaseException, ...] = ()

    def __post_init__(self) -> None:
        if type(self.authoritative) is not bool:
            raise TypeError("authoritative must be an exact bool")
        if type(self.fallback_to_inverse) is not bool:
            raise TypeError("fallback_to_inverse must be an exact bool")
        if type(self.errors) is not tuple:
            raise TypeError("errors must be an exact tuple")
        if any(not isinstance(error, BaseException) for error in self.errors):
            raise TypeError("errors must contain only BaseException instances")
        if self.authoritative and self.fallback_to_inverse:
            raise ValueError("an authoritative restore cannot require inverse fallback")


def validate_restore_outcome(result: object) -> RestoreOutcome:
    """Validate an untrusted restore result without duck-typed callbacks."""

    if result is None:
        return RestoreOutcome(authoritative=True)
    if type(result) is not RestoreOutcome:
        raise TypeError(
            "history restore must return None or an exact "
            "HistoryTransactionRestoreResult"
        )

    # Revalidate even though normal construction runs ``__post_init__``.
    # Deserializers or object-level mutation must not weaken this boundary.
    authoritative = object.__getattribute__(result, "authoritative")
    fallback_to_inverse = object.__getattribute__(result, "fallback_to_inverse")
    errors = object.__getattribute__(result, "errors")
    if type(authoritative) is not bool:
        raise TypeError("authoritative must be an exact bool")
    if type(fallback_to_inverse) is not bool:
        raise TypeError("fallback_to_inverse must be an exact bool")
    if type(errors) is not tuple:
        raise TypeError("errors must be an exact tuple")
    if any(not isinstance(error, BaseException) for error in errors):
        raise TypeError("errors must contain only BaseException instances")
    if authoritative and fallback_to_inverse:
        raise ValueError("an authoritative restore cannot require inverse fallback")
    return result


# Transitional names retained while legacy history callers move to the domain
# contract. They are aliases, so the exact-type validation remains intact.
HistoryTransactionRestoreResult = RestoreOutcome
validate_history_transaction_restore_result = validate_restore_outcome


__all__ = [
    "HistoryTransactionRestoreResult",
    "RestoreOutcome",
    "validate_history_transaction_restore_result",
    "validate_restore_outcome",
]
