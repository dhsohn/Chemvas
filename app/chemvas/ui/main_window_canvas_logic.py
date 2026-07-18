from __future__ import annotations

from collections.abc import Sequence

from chemvas.ui.canvas_text_style_state import set_text_style_for, text_style_state_for
from chemvas.ui.canvas_tool_settings_state import (
    set_tool_setting_for,
    tool_settings_state_for,
)
from chemvas.ui.canvas_window_access import (
    set_error_callback_for,
    set_history_change_callback_for,
    set_selection_info_callback_for,
    set_tool_change_callback_for,
    set_zoom_callback_for,
)
from chemvas.ui.renderer_style_access import bond_length_px_for, set_bond_length_for
from chemvas.ui.sheet_setup_access import set_sheet_setup_for

CANVAS_TEMPLATE_TOOL_FIELDS = (
    "arrow_line_width",
    "arrow_head_scale",
    "orbital_phase_enabled",
    "mark_kind",
)

CANVAS_TEMPLATE_TEXT_FIELDS = (
    "text_font_size",
    "text_font_weight",
    "text_italic",
)

CANVAS_TEMPLATE_FIELDS = CANVAS_TEMPLATE_TOOL_FIELDS + CANVAS_TEMPLATE_TEXT_FIELDS


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


def canvas_name_counter(canvas_names: Sequence[object], prefix: str = "Canvas") -> int:
    marker = f"{prefix} "
    counter = 0
    for name in canvas_names:
        text = str(name)
        if not text.startswith(marker):
            continue
        suffix = text[len(marker) :]
        if suffix.isdigit():
            counter = max(counter, int(suffix))
    return counter


def copy_canvas_template_settings(canvas, template) -> None:
    if template is None:
        return
    set_bond_length_for(canvas, bond_length_px_for(template))
    set_sheet_setup_for(canvas, template.sheet_size, template.sheet_orientation)
    tool_settings = tool_settings_state_for(template)
    for field_name in CANVAS_TEMPLATE_TOOL_FIELDS:
        set_tool_setting_for(canvas, field_name, getattr(tool_settings, field_name))
    text_style = text_style_state_for(template)
    for field_name in CANVAS_TEMPLATE_TEXT_FIELDS:
        set_text_style_for(canvas, field_name, getattr(text_style, field_name))


def bind_active_canvas_callbacks(
    canvases: Sequence[object],
    active_canvas,
    *,
    selection_info_callback,
    tool_change_callback,
    zoom_callback,
    history_change_callback,
    error_callback=None,
) -> None:
    for canvas in canvases:
        is_active = canvas is active_canvas
        set_selection_info_callback_for(
            canvas, selection_info_callback if is_active else None
        )
        set_error_callback_for(canvas, error_callback if is_active else None)
        set_tool_change_callback_for(
            canvas, tool_change_callback if is_active else None
        )
        set_zoom_callback_for(canvas, zoom_callback if is_active else None)
        set_history_change_callback_for(
            canvas, history_change_callback if is_active else None
        )


__all__ = [
    "CANVAS_TEMPLATE_FIELDS",
    "CANVAS_TEMPLATE_TEXT_FIELDS",
    "CANVAS_TEMPLATE_TOOL_FIELDS",
    "active_canvas_index",
    "active_canvas_tab_index",
    "bind_active_canvas_callbacks",
    "canvas_name_counter",
    "copy_canvas_template_settings",
    "resolve_active_canvas",
]
