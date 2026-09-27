"""Application-level registry of open windows and untitled document names."""

from __future__ import annotations

import contextlib
from typing import Any

# App-level registry for Chemvas's single-document-per-window model (like Word
# or PowerPoint): "new canvas" and "open" each spawn their own top-level window
# instead of adding a tab. The registry keeps a reference to every open window
# so it is not garbage-collected while visible, and releases it on close so the
# application can quit once the last window closes. Document numbering is global
# here (Canvas 1, Canvas 2, ...) so stacked windows stay distinguishable, unlike
# the per-window counter on MainWindowState.

_open_windows: list[Any] = []
_document_counter = 0
_reserved_document_names: set[str] = set()


def register_window(window: Any) -> None:
    if window not in _open_windows:
        _open_windows.append(window)


def forget_window(window: Any) -> None:
    with contextlib.suppress(ValueError):
        _open_windows.remove(window)


def open_windows() -> tuple[Any, ...]:
    return tuple(_open_windows)


def reset_window_registry() -> None:
    """Clear app-level window state. Intended for test isolation."""
    global _document_counter
    _open_windows.clear()
    _document_counter = 0
    _reserved_document_names.clear()


def claim_document_name(name: str) -> str:
    """Reserve ``name`` for a restored document, or a new name if it is taken.

    Every untitled or restored name handed out in this process stays taken,
    so a recovered copy never shares its title with an open document.
    """
    if name in _reserved_document_names:
        return next_document_name()
    _reserved_document_names.add(name)
    return name


def release_document_name(name: str) -> None:
    """Return a claimed name whose document never opened."""
    _reserved_document_names.discard(name)


def next_document_name() -> str:
    """Reserve the next application-wide untitled document name."""
    global _document_counter
    while True:
        _document_counter += 1
        name = f"Canvas {_document_counter}"
        if name not in _reserved_document_names:
            _reserved_document_names.add(name)
            return name


__all__ = [
    "claim_document_name",
    "forget_window",
    "next_document_name",
    "open_windows",
    "register_window",
    "release_document_name",
    "reset_window_registry",
]
