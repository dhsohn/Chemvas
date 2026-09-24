from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.ui.export.export_scope import exported_scene
from chemvas.ui.scene.scene_clipboard_copy_io import build_clipboard_mime_data
from chemvas.ui.scene.scene_clipboard_transaction_logic import (
    build_clipboard_copy_plan,
    clipboard_copy_cache_values,
)
from chemvas.ui.selection.selection_queries import selection_items_for_copy_for

if TYPE_CHECKING:
    from collections.abc import Callable


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
    bond_line_width = canvas.renderer.style.bond_line_width
    plan = build_clipboard_copy_plan(
        items,
        payload=payload,
        bond_line_width=bond_line_width,
        device_pixel_ratio=float(canvas.devicePixelRatioF()),
    )
    if plan is None:
        return False
    with exported_scene(canvas.scene(), items):
        mime_data = build_clipboard_mime_data(
            canvas,
            items=items,
            plan=plan,
            payload_mime_type=str(canvas.CLIPBOARD_SELECTION_MIME),
            bond_line_width=bond_line_width,
        )
    paste_source_json, paste_count = clipboard_copy_cache_values(plan.payload_json)
    canvas.runtime_state.scene_clipboard_state.record_paste_source(
        paste_source_json, paste_count
    )
    clipboard.setMimeData(mime_data)
    return True


__all__ = ["copy_selection_to_clipboard_for_canvas"]
