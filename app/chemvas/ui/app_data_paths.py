"""Per-user, writable app-data locations for Chemvas (recent files, autosave).

The one place that touches ``QStandardPaths``. Everything downstream takes a
plain :class:`pathlib.Path`, so the pure logic and IO helpers stay Qt-free and
testable against a ``tmp_path``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QStandardPaths


def _candidate_dirs() -> list[Path]:
    """Preferred → last-resort writable locations. Autosave and recent files are
    best-effort, so a read-only or broken profile must never break the editor:
    the temp fallback is essentially always writable."""
    candidates: list[Path] = []
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    if location:
        candidates.append(Path(location))
    candidates.append(Path.home() / ".chemvas")
    candidates.append(Path(tempfile.gettempdir()) / "chemvas")
    return candidates


def _is_usable(directory: Path) -> bool:
    """Create ``directory`` and confirm it is actually writable.

    ``mkdir(exist_ok=True)`` also "succeeds" for an existing read-only directory,
    so a broken profile would be selected and every autosave/recent write would
    then silently fail. Prove write access with a throwaway probe file instead.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".chemvas-write-test-{os.getpid()}"
        probe.write_text("")
        probe.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def app_data_dir() -> Path:
    """Return Chemvas's writable app-data directory, creating it if possible.

    On macOS this is ``~/Library/Application Support/Chemvas``, on Linux
    ``~/.local/share/Chemvas``. Never raises: it walks a fallback chain, probing
    each candidate for real write access, and if none is usable returns the last
    one anyway — callers tolerate a directory they cannot write and skip their
    best-effort writes.
    """
    last = Path(tempfile.gettempdir()) / "chemvas"
    for candidate in _candidate_dirs():
        last = candidate
        if _is_usable(candidate):
            return candidate
    return last


def recent_documents_file() -> Path:
    return app_data_dir() / "recent.json"


def sessions_dir() -> Path:
    directory = app_data_dir() / "sessions"
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return directory


__all__ = ["app_data_dir", "recent_documents_file", "sessions_dir"]
