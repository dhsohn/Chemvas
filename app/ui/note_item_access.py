from __future__ import annotations

from ui.note_item_ports import note_controller_for_access

COMMITTED_NOTE_TEXT_ROLE = 0xC001


def _note_controller_method(canvas, name: str):
    try:
        controller = note_controller_for_access(canvas)
    except AttributeError:
        return None
    method = getattr(controller, name, None)
    return method if callable(method) else None


def new_note_item_for(canvas):
    from ui.note_item import NoteItem

    return NoteItem(canvas)


def committed_note_text_for(item) -> str:
    committed_text = getattr(item, "committed_text", None)
    if callable(committed_text):
        return str(committed_text())
    data = getattr(item, "data", None)
    if callable(data):
        value = data(COMMITTED_NOTE_TEXT_ROLE)
        if value is not None:
            return str(value)
    return str(getattr(item, "committed_note_text", ""))


def set_committed_note_text_for(item, text: str) -> None:
    set_committed_text = getattr(item, "set_committed_text", None)
    if callable(set_committed_text):
        set_committed_text(text)
        return
    committed_text = str(text)
    set_data = getattr(item, "setData", None)
    if callable(set_data):
        set_data(COMMITTED_NOTE_TEXT_ROLE, committed_text)
        return
    item.committed_note_text = committed_text


def apply_note_style_for(canvas, item) -> None:
    method = _note_controller_method(canvas, "apply_note_style")
    if method is not None:
        method(item)


def update_note_box_for(canvas, item) -> None:
    method = _note_controller_method(canvas, "update_note_box")
    if method is not None:
        method(item)


__all__ = [
    "COMMITTED_NOTE_TEXT_ROLE",
    "apply_note_style_for",
    "committed_note_text_for",
    "new_note_item_for",
    "set_committed_note_text_for",
    "update_note_box_for",
]
