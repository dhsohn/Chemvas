"""Framework-free transaction outcomes, recovery, and exact savepoints."""

from .bound_attribute import (
    MISSING_ATTRIBUTE,
    BoundAttributePort,
    capture_optional_attribute,
)
from .history_authority import HistoryAuthoritySnapshot, HistoryStackSnapshot
from .outcome import (
    HistoryTransactionRestoreResult,
    RestoreOutcome,
    validate_history_transaction_restore_result,
    validate_restore_outcome,
)
from .recovery import (
    add_history_rollback_error_note,
    add_recovery_error_note,
    restore_history_snapshot_with_retry,
    restore_snapshot_with_retry,
)

__all__ = [
    "MISSING_ATTRIBUTE",
    "BoundAttributePort",
    "HistoryAuthoritySnapshot",
    "HistoryStackSnapshot",
    "HistoryTransactionRestoreResult",
    "RestoreOutcome",
    "add_history_rollback_error_note",
    "add_recovery_error_note",
    "capture_optional_attribute",
    "restore_history_snapshot_with_retry",
    "restore_snapshot_with_retry",
    "validate_history_transaction_restore_result",
    "validate_restore_outcome",
]
