"""macOS 'open document' handling.

On macOS, double-clicking a ``.chemvas`` file (or dropping it on the Dock icon)
delivers a ``QEvent.FileOpen`` Apple Event rather than a command-line argument;
Windows and Linux pass the path in ``argv``, which ``main()`` reads directly via
``_startup_document_path``. Install :class:`FileOpenEventFilter` on the
``QApplication`` so those events reach the document loader too.
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


__all__ = ["FileOpenEventFilter"]
