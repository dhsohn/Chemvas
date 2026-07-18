from __future__ import annotations


def activate_tool_no_drag(canvas) -> None:
    canvas.setDragMode(canvas.DragMode.NoDrag)


def clear_temporary_tool_overlay(
    canvas,
    *,
    preview_item=None,
    clear_handles: bool = False,
    clear_handles_callback=None,
):
    if clear_handles and clear_handles_callback is not None:
        clear_handles_callback()
    if preview_item is None:
        return None
    try:
        scene = canvas.scene()
        if preview_item.scene() is scene:
            scene.removeItem(preview_item)
    except RuntimeError:
        pass
    return None


__all__ = ["activate_tool_no_drag", "clear_temporary_tool_overlay"]
