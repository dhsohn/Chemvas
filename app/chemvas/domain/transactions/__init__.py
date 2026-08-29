"""Framework-free transaction outcomes and recovery."""

from .outcome import RestoreOutcome, validate_restore_outcome
from .recovery import add_recovery_error_note, restore_snapshot, run_rollback_step

__all__ = [
    "RestoreOutcome",
    "add_recovery_error_note",
    "restore_snapshot",
    "run_rollback_step",
    "validate_restore_outcome",
]
