"""A tiny indirection so saving can nudge autosave without importing it.

The session recovery service installs its ``snapshot_now`` here on startup; the
document-action service calls :func:`request_snapshot` right after a successful
save. That keeps the on-disk session manifest current the moment a file path
changes — including a Save chosen from the close prompt on quit, which the
periodic timer would otherwise miss — so the next launch reopens the right file.

Best-effort by design: no hook installed (tests, headless tooling) is a no-op,
and a failing hook never propagates into the save path.
"""

from __future__ import annotations

from collections.abc import Callable

# The hook may return a value (snapshot_now reports success); the return is
# ignored here.
_snapshot_hook: Callable[[], object] | None = None

# Set once app-wide quit begins (aboutToQuit). A window close deferred snapshot
# checks it so quit-driven closes never truncate the open-set manifest.
_quitting = False


def set_snapshot_hook(hook: Callable[[], object] | None) -> None:
    global _snapshot_hook
    _snapshot_hook = hook


def mark_quitting() -> None:
    global _quitting
    _quitting = True


def is_quitting() -> bool:
    return _quitting


def reset_quitting() -> None:
    """Test-only: clear the process-wide quitting flag between tests."""
    global _quitting
    _quitting = False


def snapshot_unless_quitting() -> None:
    """Deferred after a window closes: snapshot only while the app is still
    running (a standalone window close). During an app-wide quit the quitting
    flag is set first, so the full open-set manifest is preserved for restore."""
    if not _quitting:
        request_snapshot()


def request_snapshot_on_window_close() -> None:
    """Schedule the deferred close snapshot on the next event-loop turn.

    The QTimer is imported lazily and kept here (not in main_window) so the
    window stays free of concrete Qt timer/dialog defaults, per the architecture
    boundary test.
    """
    from PyQt6.QtCore import QTimer

    QTimer.singleShot(0, snapshot_unless_quitting)


def request_snapshot() -> None:
    if _snapshot_hook is None:
        return
    try:
        _snapshot_hook()
    except Exception:
        pass


__all__ = [
    "is_quitting",
    "mark_quitting",
    "request_snapshot",
    "request_snapshot_on_window_close",
    "reset_quitting",
    "set_snapshot_hook",
    "snapshot_unless_quitting",
]
