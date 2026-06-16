from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QCursor

from ui.canvas_insert_state import insert_state_for
from ui.input_view_access import scene_pos_from_global_pos_for


def refresh_hover_from_cursor_for(
    canvas,
    *,
    update_hover_highlight: Callable[[QPointF], None] | None = None,
    clear_hover_highlight: Callable[[], None] | None = None,
    hover_enabled: bool = True,
) -> None:
    if not hover_enabled:
        return
    if update_hover_highlight is None and clear_hover_highlight is None:
        return
    insert_state = insert_state_for(canvas)
    if insert_state.template_active or insert_state.smiles_active:
        if clear_hover_highlight is not None:
            clear_hover_highlight()
        return
    scene_pos = scene_pos_from_global_pos_for(canvas, QCursor.pos())
    if scene_pos is not None:
        if callable(update_hover_highlight):
            update_hover_highlight(scene_pos)
        return
    if clear_hover_highlight is not None:
        clear_hover_highlight()


__all__ = ["refresh_hover_from_cursor_for"]
