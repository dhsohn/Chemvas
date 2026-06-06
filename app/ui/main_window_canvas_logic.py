from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ui.canvas_text_style_state import set_text_style_for, text_style_state_for
from ui.canvas_tool_settings_state import set_tool_setting_for, tool_settings_state_for
from ui.canvas_window_access import (
    set_error_callback_for,
    set_history_change_callback_for,
    set_selection_info_callback_for,
    set_tool_change_callback_for,
    set_zoom_callback_for,
    snapshot_canvas_state_for,
)
from ui.renderer_style_access import bond_length_px_for, set_bond_length_for
from ui.sheet_setup_access import set_sheet_setup_for

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


@dataclass(frozen=True)
class RestorableCanvasSheet:
    name: str
    content: dict


def resolve_active_canvas(current_widget, last_canvas_tab_index: int, canvas_entries: Sequence[tuple[int, object]]):
    if any(canvas is current_widget for _, canvas in canvas_entries):
        return current_widget
    for tab_index, canvas in canvas_entries:
        if tab_index == last_canvas_tab_index:
            return canvas
    return canvas_entries[0][1] if canvas_entries else None


def active_canvas_tab_index(canvas_entries: Sequence[tuple[int, object]], active_canvas) -> int:
    if active_canvas is None:
        return -1
    for tab_index, canvas in canvas_entries:
        if canvas is active_canvas:
            return tab_index
    return -1


def active_canvas_sheet_index(canvas_entries: Sequence[tuple[int, object]], active_canvas) -> int:
    if active_canvas is None:
        return 0
    for sheet_index, (_, canvas) in enumerate(canvas_entries):
        if canvas is active_canvas:
            return sheet_index
    return 0


def canvas_sheet_name_counter(sheet_names: Sequence[object], prefix: str = "Sheet") -> int:
    marker = f"{prefix} "
    counter = 0
    for name in sheet_names:
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
        set_selection_info_callback_for(canvas, selection_info_callback if is_active else None)
        set_error_callback_for(canvas, error_callback if is_active else None)
        set_tool_change_callback_for(canvas, tool_change_callback if is_active else None)
        set_zoom_callback_for(canvas, zoom_callback if is_active else None)
        set_history_change_callback_for(canvas, history_change_callback if is_active else None)


def build_workbook_sheet_states(
    canvas_entries: Sequence[tuple[int, object]],
    *,
    tab_text_at: Callable[[int], str],
) -> list[dict]:
    sheets: list[dict] = []
    for sheet_index, (tab_index, canvas) in enumerate(canvas_entries):
        sheets.append(
            {
                "name": tab_text_at(tab_index) or f"Sheet {sheet_index + 1}",
                "kind": "canvas",
                "content": snapshot_canvas_state_for(canvas),
            }
        )
    return sheets


def restorable_canvas_sheets(
    sheet_states,
) -> list[RestorableCanvasSheet]:
    sheets: list[RestorableCanvasSheet] = []
    for sheet_state in sheet_states:
        if not isinstance(sheet_state, dict) or sheet_state["kind"] != "canvas":
            raise ValueError("Invalid Chemvas file.")
        name = sheet_state["name"]
        content = sheet_state["content"]
        if not isinstance(content, dict):
            raise ValueError("Invalid Chemvas file.")
        sheets.append(RestorableCanvasSheet(name=str(name), content=content))
    return sheets


__all__ = [
    "CANVAS_TEMPLATE_FIELDS",
    "CANVAS_TEMPLATE_TEXT_FIELDS",
    "CANVAS_TEMPLATE_TOOL_FIELDS",
    "RestorableCanvasSheet",
    "active_canvas_sheet_index",
    "active_canvas_tab_index",
    "bind_active_canvas_callbacks",
    "build_workbook_sheet_states",
    "canvas_sheet_name_counter",
    "copy_canvas_template_settings",
    "resolve_active_canvas",
    "restorable_canvas_sheets",
]
