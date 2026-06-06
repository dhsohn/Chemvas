from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem

from ui.note_item_ports import note_controller_for_access


class NoteItem(QGraphicsTextItem):
    def __init__(self, canvas) -> None:
        super().__init__()
        self._canvas = canvas
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self._last_text = ""

    def committed_text(self) -> str:
        return self._last_text

    def set_committed_text(self, text: str) -> None:
        self._last_text = str(text)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        note_controller_for_access(self._canvas).handle_note_focus_out(self)


__all__ = ["NoteItem"]
