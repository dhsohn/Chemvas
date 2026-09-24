from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


# ``canvas`` and ``preview_item`` are Any because core is Qt-free by contract:
# the only thing this module knows about them is the duck-typed call it makes.
def activate_tool_no_drag(canvas: Any) -> None:
    canvas.setDragMode(canvas.DragMode.NoDrag)


def clear_temporary_tool_overlay(
    canvas: Any,
    *,
    preview_item: Any = None,
    clear_handles: bool = False,
    clear_handles_callback: Callable[[], None] | None = None,
) -> None:
    if clear_handles and clear_handles_callback is not None:
        clear_handles_callback()
    if preview_item is None:
        return None
    with contextlib.suppress(RuntimeError):
        scene = canvas.scene()
        if preview_item.scene() is scene:
            scene.removeItem(preview_item)
    return None


__all__ = ["activate_tool_no_drag", "clear_temporary_tool_overlay"]
