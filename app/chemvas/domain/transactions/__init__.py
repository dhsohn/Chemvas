"""Framework-free transaction outcomes and recovery."""

from .outcome import RestoreOutcome, validate_restore_outcome
from .recovery import add_recovery_error_note, restore_snapshot

__all__ = [
    "RestoreOutcome",
    "add_recovery_error_note",
    "restore_snapshot",
    "validate_restore_outcome",
]
