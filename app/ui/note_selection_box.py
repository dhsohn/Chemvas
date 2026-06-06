from __future__ import annotations

from ui.selection_service_access import selection_service_from_canvas


def update_note_selection_box_for(canvas, item) -> None:
    try:
        controller = selection_service_from_canvas(canvas)
    except AttributeError:
        controller = None
    update_note_selection_box = getattr(controller, "update_note_selection_box", None)
    if callable(update_note_selection_box):
        update_note_selection_box(item)


__all__ = ["update_note_selection_box_for"]
