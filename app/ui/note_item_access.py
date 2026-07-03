from __future__ import annotations

from ui.canvas_service_ports import note_controller_for_access

COMMITTED_NOTE_TEXT_ROLE = 0xC001
COMMITTED_NOTE_HTML_ROLE = 0xC002


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


def _committed_note_value(item, accessor_name: str, role: int, attr_name: str) -> str:
    accessor = getattr(item, accessor_name, None)
    if callable(accessor):
        return str(accessor())
    data = getattr(item, "data", None)
    if callable(data):
        value = data(role)
        if value is not None:
            return str(value)
    return str(getattr(item, attr_name, ""))


def _set_committed_note_value(item, value, setter_name: str, role: int, attr_name: str) -> None:
    setter = getattr(item, setter_name, None)
    if callable(setter):
        setter(value)
        return
    committed = str(value)
    set_data = getattr(item, "setData", None)
    if callable(set_data):
        set_data(role, committed)
        return
    setattr(item, attr_name, committed)


def committed_note_text_for(item) -> str:
    return _committed_note_value(item, "committed_text", COMMITTED_NOTE_TEXT_ROLE, "committed_note_text")


def set_committed_note_text_for(item, text: str) -> None:
    _set_committed_note_value(item, text, "set_committed_text", COMMITTED_NOTE_TEXT_ROLE, "committed_note_text")


def committed_note_html_for(item) -> str:
    return _committed_note_value(item, "committed_html", COMMITTED_NOTE_HTML_ROLE, "committed_note_html")


def set_committed_note_html_for(item, html: str) -> None:
    _set_committed_note_value(item, html, "set_committed_html", COMMITTED_NOTE_HTML_ROLE, "committed_note_html")


def apply_note_style_for(canvas, item) -> None:
    method = _note_controller_method(canvas, "apply_note_style")
    if method is not None:
        method(item)


def update_note_box_for(canvas, item) -> None:
    method = _note_controller_method(canvas, "update_note_box")
    if method is not None:
        method(item)


__all__ = [
    "COMMITTED_NOTE_HTML_ROLE",
    "COMMITTED_NOTE_TEXT_ROLE",
    "apply_note_style_for",
    "committed_note_html_for",
    "committed_note_text_for",
    "new_note_item_for",
    "set_committed_note_html_for",
    "set_committed_note_text_for",
    "update_note_box_for",
]
