from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor, QTextCursor

if TYPE_CHECKING:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QGraphicsTextItem

COMMITTED_NOTE_TEXT_ROLE = 0xC001
COMMITTED_NOTE_HTML_ROLE = 0xC002


@dataclass(frozen=True, kw_only=True)
class NoteTextState:
    """Text and editor state shared by note commands and document savepoints."""

    html: str
    cursor_anchor: int
    cursor_position: int
    interaction_flags: Qt.TextInteractionFlag
    default_text_color: QColor
    committed_text: str
    committed_html: str

    @classmethod
    def capture(cls, item: QGraphicsTextItem) -> NoteTextState:
        cursor = item.textCursor()
        return cls(
            html=item.toHtml(),
            cursor_anchor=cursor.anchor(),
            cursor_position=cursor.position(),
            interaction_flags=item.textInteractionFlags(),
            default_text_color=QColor(item.defaultTextColor()),
            committed_text=committed_note_text_for(item),
            committed_html=committed_note_html_for(item),
        )

    def apply(self, item: QGraphicsTextItem) -> None:
        # Leave Qt's native undo stack intact when only the cursor changed.
        if item.toHtml() != self.html:
            item.setHtml(self.html)
        item.setDefaultTextColor(QColor(self.default_text_color))
        item.setTextInteractionFlags(self.interaction_flags)
        cursor = QTextCursor(item.document())
        cursor.setPosition(self.cursor_anchor)
        cursor.setPosition(self.cursor_position, QTextCursor.MoveMode.KeepAnchor)
        item.setTextCursor(cursor)
        set_committed_note_text_for(item, self.committed_text)
        set_committed_note_html_for(item, self.committed_html)


def new_note_item_for(canvas):
    from chemvas.ui.annotations.items import NoteItem

    return NoteItem(
        canvas.runtime_state.note_state,
        on_focus_out=lambda item: canvas.services.note_controller.handle_note_focus_out(
            item
        ),
    )


def _committed_note_value(item, accessor_name: str, role: int) -> str:
    accessor = getattr(item, accessor_name, None)
    if callable(accessor):
        return str(accessor())
    data = getattr(item, "data", None)
    if callable(data):
        value = data(role)
        if value is not None:
            return str(value)
    raise AttributeError(f"Note item does not implement {accessor_name}().")


def _set_committed_note_value(item, value, setter_name: str, role: int) -> None:
    setter = getattr(item, setter_name, None)
    if callable(setter):
        setter(value)
        return
    committed = str(value)
    set_data = getattr(item, "setData", None)
    if callable(set_data):
        set_data(role, committed)
        return
    raise AttributeError(f"Note item does not implement {setter_name}().")


def committed_note_text_for(item) -> str:
    return _committed_note_value(item, "committed_text", COMMITTED_NOTE_TEXT_ROLE)


def set_committed_note_text_for(item, text: str) -> None:
    _set_committed_note_value(
        item,
        text,
        "set_committed_text",
        COMMITTED_NOTE_TEXT_ROLE,
    )


def committed_note_html_for(item) -> str:
    return _committed_note_value(item, "committed_html", COMMITTED_NOTE_HTML_ROLE)


def set_committed_note_html_for(item, html: str) -> None:
    _set_committed_note_value(
        item,
        html,
        "set_committed_html",
        COMMITTED_NOTE_HTML_ROLE,
    )


def apply_note_style_for(canvas, item) -> None:
    canvas.services.note_controller.apply_note_style(item)


__all__ = [
    "COMMITTED_NOTE_HTML_ROLE",
    "COMMITTED_NOTE_TEXT_ROLE",
    "NoteTextState",
    "apply_note_style_for",
    "committed_note_html_for",
    "committed_note_text_for",
    "new_note_item_for",
    "set_committed_note_html_for",
    "set_committed_note_text_for",
]
