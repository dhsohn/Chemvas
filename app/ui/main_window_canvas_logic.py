from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


CANVAS_TEMPLATE_FIELDS = (
    "arrow_line_width",
    "arrow_head_scale",
    "orbital_phase_enabled",
    "text_font_size",
    "text_font_weight",
    "text_italic",
    "mark_kind",
)


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


def coerce_active_sheet_index(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
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
    canvas.renderer.set_bond_length(template.renderer.style.bond_length_px)
    set_sheet_setup = getattr(canvas, "set_sheet_setup", None)
    if callable(set_sheet_setup):
        set_sheet_setup(
            getattr(template, "sheet_size", "A4"),
            getattr(template, "sheet_orientation", "landscape"),
        )
    for field_name in CANVAS_TEMPLATE_FIELDS:
        setattr(canvas, field_name, getattr(template, field_name))


def bind_active_canvas_callbacks(
    canvases: Sequence[object],
    active_canvas,
    *,
    selection_info_callback,
    tool_change_callback,
    zoom_callback,
    history_change_callback,
) -> None:
    for canvas in canvases:
        is_active = canvas is active_canvas
        canvas.set_selection_info_callback(selection_info_callback if is_active else None)
        canvas.set_tool_change_callback(tool_change_callback if is_active else None)
        canvas.set_zoom_callback(zoom_callback if is_active else None)
        set_history_change_callback = getattr(canvas, "set_history_change_callback", None)
        if callable(set_history_change_callback):
            set_history_change_callback(history_change_callback if is_active else None)


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
                "content": canvas.snapshot_state(),
            }
        )
    return sheets


def restorable_canvas_sheets(
    sheet_states,
    *,
    default_name_factory: Callable[[], str],
) -> list[RestorableCanvasSheet]:
    sheets: list[RestorableCanvasSheet] = []
    for sheet_state in sheet_states:
        if not isinstance(sheet_state, dict):
            continue
        if sheet_state.get("kind", "canvas") != "canvas":
            continue
        name = sheet_state.get("name")
        if name is None:
            name = default_name_factory()
        content = sheet_state.get("content", {})
        if not isinstance(content, dict):
            content = {}
        sheets.append(RestorableCanvasSheet(name=str(name), content=content))
    return sheets


def clamp_active_sheet_index(active_sheet_index: int, canvas_count: int) -> int:
    if canvas_count <= 0:
        return 0
    return max(0, min(active_sheet_index, canvas_count - 1))


__all__ = [
    "CANVAS_TEMPLATE_FIELDS",
    "RestorableCanvasSheet",
    "active_canvas_sheet_index",
    "active_canvas_tab_index",
    "bind_active_canvas_callbacks",
    "build_workbook_sheet_states",
    "canvas_sheet_name_counter",
    "clamp_active_sheet_index",
    "coerce_active_sheet_index",
    "copy_canvas_template_settings",
    "resolve_active_canvas",
    "restorable_canvas_sheets",
]
