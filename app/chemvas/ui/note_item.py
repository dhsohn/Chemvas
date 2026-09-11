from __future__ import annotations

from typing import override

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.ui.canvas_service_ports import note_controller_for_access
from chemvas.ui.graphics_items import ExportTextItem


class NoteItem(ExportTextItem):
    def __init__(self, canvas) -> None:
        super().__init__()
        self._canvas = canvas
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self._last_text = ""
        self._last_html = ""
        self._fitting_text_width = False
        document = self.document()
        assert document is not None
        document.contentsChanged.connect(self._fit_text_width)

    def _fit_text_width(self) -> None:
        """Give paragraphs the longest natural line's width, without wrapping."""
        if self._fitting_text_width:
            return
        self._fitting_text_width = True
        try:
            self.setTextWidth(-1)
            document = self.document()
            if document is not None:
                self.setTextWidth(document.idealWidth())
        finally:
            self._fitting_text_width = False

    @override
    def sceneEvent(self, event) -> bool:
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
            and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
            and self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable
        ):
            # Backtab has no note-editing command. Do not let Qt move focus
            # into the window's toolbar/status-bar tab chain instead.
            event.accept()
            return True
        return super().sceneEvent(event)

    @override
    def keyPressEvent(self, event) -> None:
        cursor = self.textCursor()
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
            and self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable
            and not cursor.hasSelection()
            and not cursor.block().text()
            and cursor.currentList() is None
        ):
            # Qt resets a formatted empty block on Return. Notes deliberately
            # apply line spacing, so preserve it and insert the requested block.
            cursor.insertBlock(cursor.blockFormat(), cursor.charFormat())
            self.setTextCursor(cursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def committed_text(self) -> str:
        return self._last_text

    def set_committed_text(self, text: str) -> None:
        self._last_text = str(text)

    def committed_html(self) -> str:
        return self._last_html

    def set_committed_html(self, html: str) -> None:
        self._last_html = str(html)

    @override
    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        note_controller_for_access(self._canvas).handle_note_focus_out(self)


__all__ = ["NoteItem"]
