from __future__ import annotations

import contextlib
from collections.abc import Callable

# App-level registry for Chemvas's single-document-per-window model (like Word
# or PowerPoint): "new canvas" and "open" each spawn their own top-level window
# instead of adding a tab. The registry keeps a reference to every open window
# so it is not garbage-collected while visible, and releases it on close so the
# application can quit once the last window closes. Document numbering is global
# here (Canvas 1, Canvas 2, ...) so stacked windows stay distinguishable, unlike
# the per-window counter on MainWindowState.

_open_windows: list = []
_document_counter = 0


def register_window(window) -> None:
    if window not in _open_windows:
        _open_windows.append(window)


def forget_window(window) -> None:
    with contextlib.suppress(ValueError):
        _open_windows.remove(window)


def open_windows() -> tuple:
    return tuple(_open_windows)


def reset_window_registry() -> None:
    """Clear app-level window state. Intended for test isolation."""
    global _document_counter
    _open_windows.clear()
    _document_counter = 0


def open_new_window(reference_window=None, *, window_factory: Callable | None = None):
    if window_factory is None:
        from ui.main_window import MainWindow

        window_factory = MainWindow
    window = window_factory()
    register_window(window)
    _name_window_document(window)
    if reference_window is not None:
        _cascade(window, reference_window)
    show = getattr(window, "show", None)
    if callable(show):
        show()
    return window


def _name_window_document(window) -> None:
    global _document_counter
    _document_counter += 1
    name = f"Canvas {_document_counter}"
    try:
        from ui.main_window_service_ports import services_for_window

        services = services_for_window(window)
        canvas = window.tab_references.canvas_tabs.currentWidget()
    except (AttributeError, ImportError, RuntimeError):
        # Best-effort: naming is cosmetic and must never break window creation
        # (e.g. when a test double lacks services or the ui package is sandboxed).
        return
    if canvas is None:
        return
    services.canvas_document_service.set_display_name(canvas, name)
    services.canvas_document_service.refresh_tab_title(window, canvas)
    services.status_service.refresh_status_context(window)


def _cascade(window, reference_window, *, offset: int = 32) -> None:
    geometry = getattr(reference_window, "geometry", None)
    move = getattr(window, "move", None)
    if not (callable(geometry) and callable(move)):
        return
    reference_geometry = geometry()
    move(reference_geometry.x() + offset, reference_geometry.y() + offset)


__all__ = [
    "forget_window",
    "open_new_window",
    "open_windows",
    "register_window",
    "reset_window_registry",
]
