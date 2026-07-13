"""Per-user, writable app-data locations for Chemvas (recent files, autosave).

The one place that touches ``QStandardPaths``. Everything downstream takes a
plain :class:`pathlib.Path`, so the pure logic and IO helpers stay Qt-free and
testable against a ``tmp_path``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import QStandardPaths


def _candidate_dirs() -> list[Path]:
    """Preferred → last-resort writable locations. Autosave and recent files are
    best-effort, so a read-only or broken profile must never break the editor:
    the temp fallback is essentially always writable."""
    candidates: list[Path] = []
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if location:
        candidates.append(Path(location))
    candidates.append(Path.home() / ".chemvas")
    candidates.append(Path(tempfile.gettempdir()) / "chemvas")
    return candidates


def app_data_dir() -> Path:
    """Return Chemvas's writable app-data directory, creating it if possible.

    On macOS this is ``~/Library/Application Support/Chemvas``, on Linux
    ``~/.local/share/Chemvas``. Never raises: it walks a fallback chain and, if
    none can be created, returns the last candidate anyway — callers tolerate a
    directory that does not exist and simply skip their best-effort writes.
    """
    last = Path(tempfile.gettempdir()) / "chemvas"
    for candidate in _candidate_dirs():
        last = candidate
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
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
