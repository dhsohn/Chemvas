from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem

from ui.atom_label_access import atom_item_for_id_for
from ui.selection_scene_access import (
    clear_scene_selection_for,
    scene_selected_items_for,
    selected_scene_notes_for,
    set_scene_items_selected_for,
)
from ui.selection_service_access import (
    clear_note_selection_for,
    refresh_selection_outline_for,
    select_note_for,
)

NoteSelector = Callable[[QGraphicsTextItem], None]


@dataclass(frozen=True, slots=True)
class SceneClipboardSelectionSnapshot:
    scene_items: list[QGraphicsItem]
    notes: list[QGraphicsTextItem]


def capture_clipboard_selection_snapshot_for_canvas(canvas) -> SceneClipboardSelectionSnapshot:
    return SceneClipboardSelectionSnapshot(
        scene_items=scene_selected_items_for(canvas),
        notes=selected_scene_notes_for(canvas),
    )


def restore_clipboard_selection_snapshot_for_canvas(
    canvas,
    snapshot: SceneClipboardSelectionSnapshot,
) -> None:
    clear_scene_selection_for(canvas, block_signals=True)
    clear_note_selection_for(canvas)
    set_scene_items_selected_for(canvas, snapshot.scene_items, True, block_signals=True)
    for note in snapshot.notes:
        select_note_for(canvas, note, additive=True)
    refresh_selection_outline_for(canvas)


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


__all__ = [
    "NoteSelector",
    "SceneClipboardSelectionSnapshot",
    "capture_clipboard_selection_snapshot_for_canvas",
    "restore_clipboard_selection_snapshot_for_canvas",
    "select_pasted_content_for_canvas",
]
