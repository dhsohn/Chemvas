"""Per-user, writable app-data locations for Chemvas (recent files, autosave).

The one place that touches ``QStandardPaths``. Everything downstream takes a
plain :class:`pathlib.Path`, so the pure logic and IO helpers stay Qt-free and
testable against a ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QStandardPaths

# Falls back to a dotfile in $HOME if Qt cannot resolve a writable app-data dir
# (e.g. a stripped test environment with no application name set).
_FALLBACK_DIR = Path.home() / ".chemvas"


def app_data_dir() -> Path:
    """Return (creating if needed) Chemvas's writable app-data directory.

    On macOS this is ``~/Library/Application Support/Chemvas``, on Linux
    ``~/.local/share/Chemvas`` — Qt derives the trailing app segment from the
    ``QApplication`` name set in ``chemvas.main``.
    """
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    directory = Path(location) if location else _FALLBACK_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def recent_documents_file() -> Path:
    return app_data_dir() / "recent.json"


def sessions_dir() -> Path:
    directory = app_data_dir() / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


__all__ = ["app_data_dir", "recent_documents_file", "sessions_dir"]
