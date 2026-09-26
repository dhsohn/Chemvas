from __future__ import annotations

from collections.abc import Callable, Sequence

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem

from chemvas.ui.selection.selection_update_batch import batch_selection_updates

NoteSelector = Callable[[QGraphicsTextItem], None]


def select_pasted_content_for_canvas(
    canvas,
    *,
    atom_ids: set[int],
    scene_items: Sequence[QGraphicsItem | None],
    clear_note_selection: Callable[[], None],
    select_note: NoteSelector,
) -> None:
    with batch_selection_updates(canvas):
        canvas.services.selection.clear_scene_selection(block_signals=True)
        clear_note_selection()
        for atom_id in atom_ids:
            atom_item = canvas.services.atom_label_service.atom_item_for_id(atom_id)
            if atom_item is not None:
                canvas.services.selection.set_items_selected(
                    [atom_item], True, block_signals=False
                )
        for item in scene_items:
            if item is None:
                continue
            if item.data(0) == "note" and isinstance(item, QGraphicsTextItem):
                select_note(item)
            canvas.services.selection.set_items_selected(
                [item], True, block_signals=False
            )


__all__ = [
    "NoteSelector",
    "select_pasted_content_for_canvas",
]
