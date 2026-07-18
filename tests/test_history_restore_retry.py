from __future__ import annotations

import pytest
from chemvas.core.history import HistoryTransactionRestoreResult
from chemvas.domain.transactions import restore_history_snapshot_with_retry


@pytest.mark.parametrize(
    "fallback_order",
    [(False, True), (True, False)],
)
def test_mixed_partial_restore_attempts_never_allow_inverse_fallback(
    fallback_order: tuple[bool, bool],
) -> None:
    attempts = iter(fallback_order)

    result = restore_history_snapshot_with_retry(
        lambda: HistoryTransactionRestoreResult(
            authoritative=False,
            fallback_to_inverse=next(attempts),
        ),
        description="mixed exact transaction",
    )

    assert result.authoritative is False
    assert result.fallback_to_inverse is False
    assert len(result.errors) == 2


def test_all_explicit_no_mutation_attempts_allow_inverse_fallback() -> None:
    result = restore_history_snapshot_with_retry(
        lambda: HistoryTransactionRestoreResult(
            authoritative=False,
            fallback_to_inverse=True,
        ),
        description="safe exact transaction",
    )

    assert result.authoritative is False
    assert result.fallback_to_inverse is True


@pytest.mark.parametrize("malformed", (True, object()))
def test_malformed_restore_result_is_secondary_and_never_authoritative(
    malformed: object,
) -> None:
    result = restore_history_snapshot_with_retry(
        lambda: malformed,  # type: ignore[arg-type,return-value]
        description="malformed transaction",
    )

    assert result.authoritative is False
    assert result.fallback_to_inverse is False
    assert len(result.errors) == 2
    assert all(isinstance(error, TypeError) for error in result.errors)


def test_none_restore_result_retains_legacy_authoritative_contract() -> None:
    result = restore_history_snapshot_with_retry(
        lambda: None,  # type: ignore[return-value]
        description="legacy transaction",
    )

    assert result.authoritative is True
    assert result.errors == ()


def test_restore_result_constructor_rejects_malformed_fields() -> None:
    with pytest.raises(TypeError, match="exact bool"):
        HistoryTransactionRestoreResult(authoritative=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact tuple"):
        HistoryTransactionRestoreResult(
            authoritative=False,
            errors=[],  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="BaseException"):
        HistoryTransactionRestoreResult(
            authoritative=False,
            errors=("not an exception",),  # type: ignore[arg-type]
        )
