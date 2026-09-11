"""Pure model for the "Open Recent" list — ordering, dedup, cap, (de)serialize.

No Qt, no filesystem: the store layer injects existence checks and does IO. The
list is most-recent-first; entries are absolute path strings.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

MAX_RECENT = 10

# Bump if the on-disk shape changes. Unknown schemas fail closed.
RECENT_SCHEMA_VERSION = 1


def _key(path: str) -> str:
    """Comparison key: lexical-normalized + case-folded so the same file added
    via different spellings (``a/../a/x``, ``A/X`` on macOS) dedupes."""
    return os.path.normcase(os.path.normpath(path))


def add_recent(
    paths: list[str],
    new_path: str,
    *,
    max_entries: int = MAX_RECENT,
    path_key: Callable[[str], str] = _key,
) -> list[str]:
    """Return a new list with ``new_path`` promoted to the front, deduped and
    capped at ``max_entries``. The original spelling of ``new_path`` is kept."""
    new_key = path_key(new_path)
    result = [new_path]
    for path in paths:
        if path_key(path) != new_key:
            result.append(path)
    return result[:max_entries]


def prune_missing(
    paths: list[str], *, exists, path_key: Callable[[str], str] = _key
) -> list[str]:
    """Drop entries for which ``exists(path)`` is falsey (injected for testing)."""
    seen: set[str] = set()
    kept: list[str] = []
    for path in paths:
        if not exists(path):
            continue
        key = path_key(path)
        if key in seen:
            continue
        seen.add(key)
        kept.append(path)
    return kept


def recent_menu_entries(paths: list[str]) -> list[tuple[str, str]]:
    """Disambiguate duplicate filenames without changing their open targets."""
    names = [os.path.basename(path) or path for path in paths]
    counts = Counter(names)
    return [
        (f"{name} — {os.path.dirname(path)}" if counts[name] > 1 else name, path)
        for name, path in zip(names, paths, strict=True)
    ]


def to_json(paths: list[str]) -> dict:
    return {"version": RECENT_SCHEMA_VERSION, "paths": list(paths)}


def from_json(data: object) -> list[str]:
    if (
        not isinstance(data, dict)
        or set(data) != {"version", "paths"}
        or type(data.get("version")) is not int
        or data.get("version") != RECENT_SCHEMA_VERSION
    ):
        return []
    paths = data.get("paths")
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        return []
    return list(paths)


__all__ = [
    "MAX_RECENT",
    "RECENT_SCHEMA_VERSION",
    "add_recent",
    "from_json",
    "prune_missing",
    "recent_menu_entries",
    "to_json",
]
