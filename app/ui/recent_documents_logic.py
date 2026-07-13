"""Pure model for the "Open Recent" list — ordering, dedup, cap, (de)serialize.

No Qt, no filesystem: the store layer injects existence checks and does IO. The
list is most-recent-first; entries are absolute path strings.
"""

from __future__ import annotations

import os

MAX_RECENT = 10

# Bump if the on-disk shape changes; load tolerates unknown/most-recent formats.
RECENT_SCHEMA_VERSION = 1


def _key(path: str) -> str:
    """Comparison key: lexical-normalized + case-folded so the same file added
    via different spellings (``a/../a/x``, ``A/X`` on macOS) dedupes."""
    return os.path.normcase(os.path.normpath(path))


def add_recent(paths: list[str], new_path: str, *, max_entries: int = MAX_RECENT) -> list[str]:
    """Return a new list with ``new_path`` promoted to the front, deduped and
    capped at ``max_entries``. The original spelling of ``new_path`` is kept."""
    new_key = _key(new_path)
    result = [new_path]
    for path in paths:
        if _key(path) != new_key:
            result.append(path)
    return result[:max_entries]


def prune_missing(paths: list[str], *, exists) -> list[str]:
    """Drop entries for which ``exists(path)`` is falsey (injected for testing)."""
    seen: set[str] = set()
    kept: list[str] = []
    for path in paths:
        key = _key(path)
        if key in seen:
            continue
        if exists(path):
            seen.add(key)
            kept.append(path)
    return kept


def recent_menu_entries(paths: list[str]) -> list[tuple[str, str]]:
    """Map paths to ``(label, full_path)`` for the menu. Label is the file name;
    the full path is the tooltip / the value to open."""
    return [(os.path.basename(path) or path, path) for path in paths]


def to_json(paths: list[str]) -> dict:
    return {"version": RECENT_SCHEMA_VERSION, "paths": list(paths)}


def from_json(data: object) -> list[str]:
    if not isinstance(data, dict):
        return []
    paths = data.get("paths")
    if not isinstance(paths, list):
        return []
    return [path for path in paths if isinstance(path, str)]


__all__ = [
    "MAX_RECENT",
    "RECENT_SCHEMA_VERSION",
    "add_recent",
    "from_json",
    "prune_missing",
    "recent_menu_entries",
    "to_json",
]
