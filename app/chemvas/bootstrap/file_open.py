"""Application-level document-open coordination."""

from __future__ import annotations

from typing import Any


def document_open_target(reference_window: Any) -> Any:
    """Share blank-document reuse across menu, startup and OS-open entrypoints."""
    from chemvas.bootstrap.window_registry import open_new_window

    documents = reference_window.services.canvas_document_service
    if documents.reusable_open_target(reference_window) is not None:
        return reference_window
    return open_new_window(reference_window)


def open_document(path: str) -> None:
    """Open ``path`` using Chemvas's single-document-per-window policy."""
    from chemvas.bootstrap.window_registry import open_new_window
    from chemvas.features.session import is_quit_pending
    from chemvas.shell.window_registry import open_windows
    from chemvas.ui.window.main_window_ports import status_bar_for

    windows = open_windows()
    if is_quit_pending():
        if windows:
            status_bar_for(windows[-1]).showMessage(
                f"Cannot open {path} while Chemvas is preparing to quit. "
                "Try again after cancelling Quit or restarting Chemvas.",
                8000,
            )
        return
    reference = windows[-1] if windows else open_new_window()
    services = reference.services
    services.document_action_service.load_canvas_from_path(
        reference, path, target_provider=lambda: document_open_target(reference)
    )


__all__ = ["document_open_target", "open_document"]
