"""Translate Qt file-open events into an application path callback."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QEvent, QObject

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QFileOpenEvent


class FileOpenEventFilter(QObject):
    def __init__(self, handler: Callable[[str], None]) -> None:
        super().__init__()
        self._handler = handler

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.FileOpen:
            path = cast("QFileOpenEvent", event).file()
            if path:
                self._handler(path)
            return True
        return False


__all__ = ["FileOpenEventFilter"]
