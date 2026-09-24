from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, Any

from chemvas.ui.canvas.canvas_text_style_state import set_text_style_for
from chemvas.ui.canvas.canvas_tool_settings_state import set_tool_setting_for
from chemvas.ui.canvas.canvas_window_access import (
    set_document_change_callback_for,
    set_history_change_callback_for,
)
from chemvas.ui.canvas.sheet_setup_access import set_sheet_setup_for, sheet_setup_for

if TYPE_CHECKING:
    from collections.abc import Sequence

CANVAS_TEMPLATE_TOOL_FIELDS = (
    "arrow_line_width",
    "arrow_head_scale",
    "orbital_phase_enabled",
    "mark_kind",
)

CANVAS_TEMPLATE_TEXT_FIELDS = (
    "text_font_family",
    "text_font_size",
    "text_font_weight",
    "text_italic",
    "text_color",
    "text_alignment",
    "text_line_spacing",
    "note_box_enabled",
    "note_box_color",
    "note_box_alpha",
    "note_border_enabled",
    "note_border_color",
    "note_border_width",
    "note_padding",
)


def resolve_active_canvas(
    current_widget,
    last_canvas_tab_index: int,
    canvas_entries: Sequence[tuple[int, object]],
):
    if any(canvas is current_widget for _, canvas in canvas_entries):
        return current_widget
    for tab_index, canvas in canvas_entries:
        if tab_index == last_canvas_tab_index:
            return canvas
    return canvas_entries[0][1] if canvas_entries else None


def active_canvas_tab_index(
    canvas_entries: Sequence[tuple[int, object]], active_canvas
) -> int:
    if active_canvas is None:
        return -1
    for tab_index, canvas in canvas_entries:
        if canvas is active_canvas:
            return tab_index
    return -1


def active_canvas_index(
    canvas_entries: Sequence[tuple[int, object]], active_canvas
) -> int:
    if active_canvas is None:
        return 0
    for canvas_index, (_, canvas) in enumerate(canvas_entries):
        if canvas is active_canvas:
            return canvas_index
    return 0


def copy_canvas_template_settings(canvas, template) -> None:
    if template is None:
        return
    canvas.renderer.set_bond_length(template.renderer.style.bond_length_px)
    set_sheet_setup_for(canvas, *sheet_setup_for(template))
    tool_settings = template.runtime_state.tool_settings_state
    for field_name in CANVAS_TEMPLATE_TOOL_FIELDS:
        set_tool_setting_for(canvas, field_name, getattr(tool_settings, field_name))
    text_style = template.runtime_state.text_style_state
    for field_name in CANVAS_TEMPLATE_TEXT_FIELDS:
        set_text_style_for(canvas, field_name, copy(getattr(text_style, field_name)))


def bind_active_canvas_callbacks(
    canvases: Sequence[Any],
    active_canvas,
    *,
    selection_info_callback,
    tool_change_callback,
    zoom_callback,
    history_change_callback,
    error_callback=None,
    document_change_callback=None,
) -> None:
    for canvas in canvases:
        is_active = canvas is active_canvas
        canvas.runtime_state.selection_info_state.callback = (
            selection_info_callback if is_active else None
        )
        canvas.runtime_state.callback_state.error = (
            error_callback if is_active else None
        )
        canvas.runtime_state.callback_state.tool_change = (
            tool_change_callback if is_active else None
        )
        canvas.runtime_state.callback_state.zoom = zoom_callback if is_active else None
        set_history_change_callback_for(
            canvas, history_change_callback if is_active else None
        )
        set_document_change_callback_for(
            canvas, document_change_callback if is_active else None
        )


__all__ = [
    "CANVAS_TEMPLATE_TEXT_FIELDS",
    "CANVAS_TEMPLATE_TOOL_FIELDS",
    "active_canvas_index",
    "active_canvas_tab_index",
    "bind_active_canvas_callbacks",
    "copy_canvas_template_settings",
    "resolve_active_canvas",
]
