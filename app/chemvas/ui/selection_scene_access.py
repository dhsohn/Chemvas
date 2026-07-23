from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QObject

from chemvas.ui.canvas_scene_items_state import selected_notes_for
from chemvas.ui.scene_signal_blocking import blocked_scene_signals


def _scene_for(canvas, *, strict: bool = False):
    try:
        scene = canvas.scene
    except AttributeError:
        return None
    if not callable(scene):
        return None
    try:
        scene_obj = scene()
    except RuntimeError:
        # Reads treat a failing scene port as "no scene"; mutations only
        # swallow the deleted-wrapper teardown case and propagate live errors.
        if isinstance(canvas, QObject) and sip.isdeleted(canvas):
            return None
        if strict:
            raise
        return None
    if isinstance(scene_obj, QObject) and sip.isdeleted(scene_obj):
        return None
    return scene_obj


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
    scene_obj = _scene_for(canvas, strict=True)
    if scene_obj is None:
        return False
    if block_signals:
        with blocked_scene_signals(scene_obj):
            scene_obj.clearSelection()
    else:
        scene_obj.clearSelection()
    return True


def set_scene_items_selected_for(
    canvas,
    items,
    selected: bool,
    *,
    block_signals: bool = True,
) -> None:
    scene_obj = _scene_for(canvas, strict=True)
    if scene_obj is not None and block_signals:
        with blocked_scene_signals(scene_obj):
            for item in items:
                item.setSelected(selected)
        return
    for item in items:
        item.setSelected(selected)


__all__ = [
    "clear_scene_selection_for",
    "scene_selected_items_for",
    "selected_scene_notes_for",
    "set_scene_items_selected_for",
]
