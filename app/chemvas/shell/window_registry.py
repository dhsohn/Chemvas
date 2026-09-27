"""Application-level registry of open windows and untitled document names."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

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
# An exception that escaped a window's own event handler, and that window, kept
# until the desktop exception boundary reports the exception.
_failed_window: tuple[BaseException, object] | None = None


def register_window(window: Any) -> None:
    if window not in _open_windows:
        _open_windows.append(window)


def forget_window(window: Any) -> None:
    with contextlib.suppress(ValueError):
        _open_windows.remove(window)


def open_windows() -> tuple[Any, ...]:
    return tuple(_open_windows)


@contextlib.contextmanager
def failures_reported_in(window: object) -> Iterator[None]:
    """Have an exception escaping this block reported in ``window``.

    PyQt hands an exception that escapes a virtual event handler to
    ``sys.excepthook`` only after the handler has unwound, so the window is
    kept with that exception until the desktop exception boundary takes it,
    not for the span of the block.
    """
    global _failed_window
    try:
        yield
    except Exception as error:
        _failed_window = (error, window)
        raise


def take_failed_window(error: BaseException) -> object | None:
    """Return the window ``error`` escaped from, and forget any kept window."""
    global _failed_window
    failure, _failed_window = _failed_window, None
    if failure is None or failure[0] is not error:
        return None
    return failure[1]


def reset_window_registry() -> None:
    """Clear app-level window state. Intended for test isolation."""
    global _document_counter, _failed_window
    _open_windows.clear()
    _document_counter = 0
    _reserved_document_names.clear()
    _failed_window = None


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
    "failures_reported_in",
    "forget_window",
    "next_document_name",
    "open_windows",
    "register_window",
    "release_document_name",
    "reset_window_registry",
    "take_failed_window",
]
