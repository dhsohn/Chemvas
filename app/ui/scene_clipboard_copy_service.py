from __future__ import annotations

from collections.abc import Callable

from ui.canvas_format_access import clipboard_selection_mime_for
from ui.input_view_access import device_pixel_ratio_for
from ui.renderer_style_access import bond_line_width_for
from ui.scene_clipboard_access import (
    set_clipboard_paste_count_for,
    set_clipboard_paste_source_json_for,
    visible_canvas_items_to_hide_for_copy,
)
from ui.scene_clipboard_copy_io import build_clipboard_mime_data
from ui.scene_clipboard_transaction_logic import (
    build_clipboard_copy_plan,
    clipboard_copy_cache_values,
)
from ui.selection_collection_access import selection_items_for_copy_for


def copy_selection_to_clipboard_for_canvas(
    canvas,
    *,
    clipboard,
    payload_provider: Callable[[], dict | None],
) -> bool:
    items = selection_items_for_copy_for(canvas)
    if not items:
        return False
    payload = payload_provider()
    bond_line_width = bond_line_width_for(canvas)
    plan = build_clipboard_copy_plan(
        items,
        payload=payload,
        bond_line_width=bond_line_width,
        device_pixel_ratio=device_pixel_ratio_for(canvas),
    )
    if plan is None:
        return False
    hidden = visible_canvas_items_to_hide_for_copy(
        canvas,
        plan.source,
        selected_items=set(items),
    )
    for item in hidden:
        item.setVisible(False)
    try:
        mime_data = build_clipboard_mime_data(
            canvas,
            items=items,
            plan=plan,
            payload_mime_type=clipboard_selection_mime_for(canvas),
            bond_line_width=bond_line_width,
        )
    finally:
        for item in hidden:
            item.setVisible(True)
    paste_source_json, paste_count = clipboard_copy_cache_values(plan.payload_json)
    set_clipboard_paste_source_json_for(canvas, paste_source_json)
    set_clipboard_paste_count_for(canvas, paste_count)
    clipboard.setMimeData(mime_data)
    return True


__all__ = ["copy_selection_to_clipboard_for_canvas"]
