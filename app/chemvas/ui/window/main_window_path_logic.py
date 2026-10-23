from __future__ import annotations

from pathlib import Path

CANONICAL_SAVED_DOCUMENT_SUFFIX = ".cdxml"
DESKTOP_DOCUMENT_SUFFIXES = frozenset((".mol", ".cdxml"))
RECENT_DOCUMENT_SUFFIXES = frozenset((".cdxml",))


def _has_suffix(path: str, suffixes: frozenset[str]) -> bool:
    return Path(path).suffix.lower() in suffixes


def is_saved_document_path(path: str) -> bool:
    return Path(path).suffix.lower() == ".cdxml"


def is_desktop_document_path(path: str) -> bool:
    return _has_suffix(path, DESKTOP_DOCUMENT_SUFFIXES)


def is_recent_document_path(path: str) -> bool:
    return _has_suffix(path, RECENT_DOCUMENT_SUFFIXES)


def resolve_save_path(current_path: str | None) -> str | None:
    return current_path or None


def resolve_save_as_path(dialog_path: str | None) -> str | None:
    if not dialog_path:
        return None
    if is_saved_document_path(dialog_path):
        return dialog_path
    return str(Path(dialog_path).with_suffix(CANONICAL_SAVED_DOCUMENT_SUFFIX))


def resolve_load_path(dialog_path: str | None) -> str | None:
    if not dialog_path:
        return None
    return dialog_path
