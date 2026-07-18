"""Session autosave and crash-recovery policy."""

from .autosave import (
    is_quitting,
    mark_quitting,
    request_snapshot,
    request_snapshot_on_window_close,
    reset_quitting,
    set_snapshot_hook,
    snapshot_unless_quitting,
)
from .logic import (
    SESSION_SCHEMA_VERSION,
    DocDescriptor,
    DocEntry,
    RestoredDoc,
    RestorePlan,
    SessionManifest,
    entries_to_restore,
    is_consumable,
    manifest_from_json,
    manifest_to_json,
    needs_snapshot,
    plan_restore,
    should_persist,
)

__all__ = [
    "SESSION_SCHEMA_VERSION",
    "DocDescriptor",
    "DocEntry",
    "RestorePlan",
    "RestoredDoc",
    "SessionManifest",
    "entries_to_restore",
    "is_consumable",
    "is_quitting",
    "manifest_from_json",
    "manifest_to_json",
    "mark_quitting",
    "needs_snapshot",
    "plan_restore",
    "request_snapshot",
    "request_snapshot_on_window_close",
    "reset_quitting",
    "set_snapshot_hook",
    "should_persist",
    "snapshot_unless_quitting",
]
