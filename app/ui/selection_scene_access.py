from __future__ import annotations

from ui.canvas_scene_items_state import selected_notes_for


def _scene_for(canvas):
    scene = getattr(canvas, "scene", None)
    if not callable(scene):
        return None
    try:
        return scene()
    except RuntimeError:
        return None


def scene_selected_items_for(canvas) -> list:
    scene_obj = _scene_for(canvas)
    if scene_obj is None:
        return []
    return list(scene_obj.selectedItems())


def selected_scene_notes_for(canvas):
    scene_obj = _scene_for(canvas)
    if scene_obj is None:
        return []
    notes = []
    for note in selected_notes_for(canvas):
        try:
            attached_scene = note.scene()
        except RuntimeError:
            continue
        if attached_scene is scene_obj:
            notes.append(note)
    return notes


def clear_scene_selection_for(canvas, *, block_signals: bool = False) -> bool:
    scene_obj = _scene_for(canvas)
    if scene_obj is None:
        return False
    if block_signals:
        scene_obj.blockSignals(True)
        try:
            scene_obj.clearSelection()
        finally:
            scene_obj.blockSignals(False)
        return True
    scene_obj.clearSelection()
    return True


def set_scene_items_selected_for(canvas, items, selected: bool, *, block_signals: bool = True) -> None:
    scene_obj = _scene_for(canvas)
    if scene_obj is not None and block_signals:
        scene_obj.blockSignals(True)
        try:
            for item in items:
                item.setSelected(selected)
        finally:
            scene_obj.blockSignals(False)
        return
    for item in items:
        item.setSelected(selected)


__all__ = [
    "clear_scene_selection_for",
    "scene_selected_items_for",
    "selected_scene_notes_for",
    "set_scene_items_selected_for",
]
