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


def set_snapshot_hook(hook: Callable[[], object] | None) -> None:
    global _snapshot_hook
    _snapshot_hook = hook


def request_snapshot() -> None:
    if _snapshot_hook is None:
        return
    try:
        _snapshot_hook()
    except Exception:
        pass


__all__ = ["request_snapshot", "set_snapshot_hook"]
