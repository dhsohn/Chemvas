from __future__ import annotations

from collections.abc import Callable, Sequence

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem

from ui.atom_label_access import atom_item_for_id_for
from ui.selection_scene_access import clear_scene_selection_for
from ui.selection_service_access import refresh_selection_outline_for

NoteSelector = Callable[[QGraphicsTextItem], None]


def select_pasted_content_for_canvas(
    canvas,
    *,
    atom_ids: set[int],
    scene_items: Sequence[QGraphicsItem | None],
    clear_note_selection: Callable[[], None],
    select_note: NoteSelector,
) -> None:
    clear_scene_selection_for(canvas, block_signals=True)
    clear_note_selection()
    for atom_id in atom_ids:
        atom_item = atom_item_for_id_for(canvas, atom_id)
        if atom_item is not None:
            atom_item.setSelected(True)
    for item in scene_items:
        if item is None:
            continue
        if item.data(0) == "note" and isinstance(item, QGraphicsTextItem):
            select_note(item)
        item.setSelected(True)
    refresh_selection_outline_for(canvas)


__all__ = ["NoteSelector", "select_pasted_content_for_canvas"]
