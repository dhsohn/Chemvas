"""Application-level document-open coordination."""

from __future__ import annotations


def open_document(path: str) -> None:
    """Open ``path`` using Chemvas's single-document-per-window policy."""
    from chemvas.bootstrap.window_registry import open_new_window, open_windows
    from chemvas.ui.main_window_ports import services_for_window

    windows = open_windows()
    reference = windows[-1] if windows else open_new_window()
    services = services_for_window(reference)
    documents = services.canvas_document_service

    def target_provider() -> object:
        if documents.reusable_open_target(reference) is not None:
            return reference
        return open_new_window(reference)

    services.document_action_service.load_canvas_from_path(
        reference, path, target_provider=target_provider
    )


__all__ = ["open_document"]
