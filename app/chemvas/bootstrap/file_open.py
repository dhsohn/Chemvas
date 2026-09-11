"""Application-level document-open coordination."""

from __future__ import annotations

from typing import Any


def document_open_target(reference_window: Any) -> Any:
    """Share blank-document reuse across menu, startup and OS-open entrypoints."""
    from chemvas.bootstrap.window_registry import open_new_window
    from chemvas.ui.main_window_ports import services_for_window

    documents = services_for_window(reference_window).canvas_document_service
    if documents.reusable_open_target(reference_window) is not None:
        return reference_window
    return open_new_window(reference_window)


def open_document(path: str) -> None:
    """Open ``path`` using Chemvas's single-document-per-window policy."""
    from chemvas.bootstrap.window_registry import (
        open_new_window,
        open_windows,
    )
    from chemvas.features.session import is_quit_pending
    from chemvas.ui.main_window_ports import services_for_window

    windows = open_windows()
    if is_quit_pending():
        if windows:
            windows[-1].statusBar().showMessage(
                f"Cannot open {path} while Chemvas is preparing to quit. "
                "Try again after cancelling Quit or restarting Chemvas.",
                8000,
            )
        return
    reference = windows[-1] if windows else open_new_window()
    services = services_for_window(reference)
    services.document_action_service.load_canvas_from_path(
        reference, path, target_provider=lambda: document_open_target(reference)
    )


__all__ = ["document_open_target", "open_document"]
