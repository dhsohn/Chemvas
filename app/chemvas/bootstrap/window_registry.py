from __future__ import annotations

import contextlib
from collections.abc import Callable
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


def next_document_name() -> str:
    """Reserve the next application-wide untitled document name."""
    global _document_counter
    _document_counter += 1
    return f"Canvas {_document_counter}"


def open_new_window(
    reference_window: Any | None = None,
    *,
    window_factory: Callable[[], Any] | None = None,
) -> Any:
    initialize_window: Callable[[Any], None] | None = None
    if window_factory is None:
        from chemvas.bootstrap.main_window import (
            build_main_window,
            initialize_main_window_document,
        )

        window_factory = build_main_window
        initialize_window = initialize_main_window_document
    window = window_factory()
    register_window(window)
    if initialize_window is not None:
        initialize_window(window)
    if reference_window is not None:
        _cascade(window, reference_window)
    show = getattr(window, "show", None)
    if callable(show):
        show()
    return window


def _cascade(window: Any, reference_window: Any, *, offset: int = 32) -> None:
    geometry = getattr(reference_window, "geometry", None)
    move = getattr(window, "move", None)
    if not (callable(geometry) and callable(move)):
        return
    reference_geometry = geometry()
    move(reference_geometry.x() + offset, reference_geometry.y() + offset)


__all__ = [
    "forget_window",
    "next_document_name",
    "open_new_window",
    "open_windows",
    "register_window",
    "reset_window_registry",
]
