"""Load/save the Open-Recent list to ``recent.json`` (atomic writes).

Best-effort by contract: every function swallows IO errors and returns/writes
what it can, so a broken or read-only app-data dir can never break a Save or
an Open. Reads prune entries whose file has since disappeared.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import TYPE_CHECKING

from chemvas.core.document_io import atomic_write_text
from chemvas.ui.app_data_paths import recent_documents_file
from chemvas.ui.main_window_path_logic import is_recent_document_path
from chemvas.ui.recent_documents_logic import (
    add_recent,
    from_json,
    prune_missing,
    to_json,
)

if TYPE_CHECKING:
    from pathlib import Path


def _target(path: Path | None) -> Path:
    return path if path is not None else recent_documents_file()


def load_recent(*, path: Path | None = None) -> list[str]:
    target = _target(path)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    supported = [entry for entry in from_json(data) if is_recent_document_path(entry)]
    return prune_missing(supported, exists=os.path.exists)


def save_recent(paths: list[str], *, path: Path | None = None) -> None:
    supported = [entry for entry in paths if is_recent_document_path(entry)]
    with contextlib.suppress(OSError):
        atomic_write_text(_target(path), json.dumps(to_json(supported), indent=2))


def record_recent(new_path: str, *, path: Path | None = None) -> list[str]:
    """Promote ``new_path`` to the front of the recent list and persist it."""
    target = _target(path)
    if not is_recent_document_path(new_path):
        return load_recent(path=target)
    updated = add_recent(load_recent(path=target), os.path.abspath(new_path))
    save_recent(updated, path=target)
    return updated


def clear_recent(*, path: Path | None = None) -> None:
    save_recent([], path=path)


__all__ = ["clear_recent", "load_recent", "record_recent", "save_recent"]
