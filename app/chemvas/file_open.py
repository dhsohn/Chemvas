"""macOS 'open document' handling.

On macOS, double-clicking a ``.chemvas`` file (or dropping it on the Dock icon)
delivers a ``QEvent.FileOpen`` Apple Event rather than a command-line argument;
Windows and Linux pass the path in ``argv``, which ``main()`` reads directly via
``_startup_document_path``. Install :class:`FileOpenEventFilter` on the
``QApplication`` (with :func:`open_document` as its handler) so those events reach
the document loader too.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QFileOpenEvent


class FileOpenEventFilter(QObject):
    def __init__(self, handler: Callable[[str], None]) -> None:
        super().__init__()
        self._handler = handler

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.FileOpen:
            path = cast(QFileOpenEvent, event).file()
            if path:
                self._handler(path)
            return True
        return False


def open_document(path: str) -> None:
    """Open ``path`` honoring Chemvas's single-document-per-window model.

    Reuses a blank, unsaved, single-canvas window (the empty window opened at
    startup) when one is available, so a cold-start file open doesn't leave an
    extra empty window behind. Otherwise opens the document in a fresh window —
    matching the File ▸ Open action rather than adding a tab to an existing,
    already-occupied window. The destination window is resolved only after the
    file reads successfully, so an unreadable file never spawns an empty window.
    """
    from ui.main_window_app import open_new_window, open_windows
    from ui.main_window_ports import services_for_window

    windows = open_windows()
    reference = windows[-1] if windows else open_new_window()
    services = services_for_window(reference)
    documents = services.canvas_document_service

    def target_provider() -> object:
        if documents.reusable_open_target(reference) is not None:
            return reference
        return open_new_window(reference)

    services.document_action_service.load_canvas_from_path(reference, path, target_provider=target_provider)


__all__ = ["FileOpenEventFilter", "open_document"]
