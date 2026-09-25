from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem

from chemvas.ui.selection.selection_queries import (
    scene_selected_items_for,
    selected_scene_notes_for,
)
from chemvas.ui.selection.selection_update_batch import batch_selection_updates

NoteSelector = Callable[[QGraphicsTextItem], None]


@dataclass(frozen=True)
class SceneClipboardSelectionSnapshot:
    scene_items: list[QGraphicsItem]
    notes: list[QGraphicsTextItem]


def capture_clipboard_selection_snapshot_for_canvas(
    canvas,
) -> SceneClipboardSelectionSnapshot:
    return SceneClipboardSelectionSnapshot(
        scene_items=scene_selected_items_for(canvas),
        notes=selected_scene_notes_for(canvas),
    )


def restore_clipboard_selection_snapshot_for_canvas(
    canvas,
    snapshot: SceneClipboardSelectionSnapshot,
) -> None:
    canvas.services.selection.clear_scene_selection(block_signals=True)
    canvas.services.selection.clear_note_selection()
    canvas.services.selection.set_items_selected(
        snapshot.scene_items, True, block_signals=True
    )
    for note in snapshot.notes:
        canvas.services.selection.select_note(note, additive=True)
    canvas.services.selection.update_selection_outline()


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
    "SceneClipboardSelectionSnapshot",
    "capture_clipboard_selection_snapshot_for_canvas",
    "restore_clipboard_selection_snapshot_for_canvas",
    "select_pasted_content_for_canvas",
]
