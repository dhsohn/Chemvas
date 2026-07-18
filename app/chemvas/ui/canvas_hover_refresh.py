from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QCursor

from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.input_view_access import scene_pos_from_global_pos_for


def _scene_pos_from_cursor_or_none(canvas) -> QPointF | None:
    try:
        return scene_pos_from_global_pos_for(canvas, QCursor.pos())
    except AttributeError:
        return None


def refresh_hover_from_cursor_for(
    canvas,
    *,
    update_hover_highlight: Callable[[QPointF], None] | None = None,
    clear_hover_highlight: Callable[[], None] | None = None,
    render_template_preview: Callable[[QPointF], None] | None = None,
    render_smiles_preview: Callable[[QPointF], None] | None = None,
    hover_enabled: bool = True,
) -> None:
    if not hover_enabled:
        return
    if (
        update_hover_highlight is None
        and clear_hover_highlight is None
        and render_template_preview is None
        and render_smiles_preview is None
    ):
        return
    scene_pos = _scene_pos_from_cursor_or_none(canvas)
    insert_state = insert_state_for(canvas)
    if insert_state.template_active or insert_state.smiles_active:
        if clear_hover_highlight is not None:
            clear_hover_highlight()
        if (
            scene_pos is not None
            and insert_state.template_active
            and callable(render_template_preview)
        ):
            render_template_preview(scene_pos)
        elif (
            scene_pos is not None
            and insert_state.smiles_active
            and callable(render_smiles_preview)
        ):
            render_smiles_preview(scene_pos)
        return
    if scene_pos is not None:
        if callable(update_hover_highlight):
            update_hover_highlight(scene_pos)
        return
    if clear_hover_highlight is not None:
        clear_hover_highlight()


__all__ = ["refresh_hover_from_cursor_for"]
