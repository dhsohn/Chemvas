from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ui.canvas_chemdraw_shortcut_service import CanvasChemdrawShortcutService
from ui.canvas_input_controller import CanvasInputController
from ui.canvas_pointer_controller import CanvasPointerController
from ui.canvas_tool_mode_controller import CanvasToolModeController

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class CanvasInputServiceBundle:
    input_controller: CanvasInputController
    pointer_controller: CanvasPointerController
    tool_mode_controller: CanvasToolModeController
    chemdraw_shortcut_service: CanvasChemdrawShortcutService


def build_canvas_input_services(
    canvas: CanvasView | Any,
    *,
    hit_testing_service: Any,
    insert_controller: Any,
    hover_interaction_service: Any,
    tool_controller: Any,
    scene_delete_controller: Any,
    scene_clipboard_controller: Any,
    scene_transform_controller: Any,
    mark_scene_service: Any,
    hover_refresh: Callable[..., None],
    history_service: Any,
) -> CanvasInputServiceBundle:
    tool_mode_controller = CanvasToolModeController(
        canvas,
        insert_controller=insert_controller,
        hover_refresh=hover_refresh,
        set_active_tool=tool_controller.set_active,
    )
    pointer_controller = CanvasPointerController(
        canvas,
        hit_testing_service=hit_testing_service,
        insert_controller=insert_controller,
        hover_interaction_service=hover_interaction_service,
        tool_controller=tool_controller,
        scene_transform_controller=scene_transform_controller,
        hover_refresh=hover_refresh,
    )
    chemdraw_shortcut_service = CanvasChemdrawShortcutService(
        canvas,
        scene_transform_controller=scene_transform_controller,
        tool_mode_controller=tool_mode_controller,
        mark_scene_service=mark_scene_service,
    )
    input_controller = CanvasInputController(
        canvas,
        scene_delete_controller=scene_delete_controller,
        scene_clipboard_controller=scene_clipboard_controller,
        history_service=history_service,
        hover_refresh=hover_refresh,
        chemdraw_shortcut_service=chemdraw_shortcut_service,
        tool_mode_controller=tool_mode_controller,
    )
    return CanvasInputServiceBundle(
        input_controller=input_controller,
        pointer_controller=pointer_controller,
        tool_mode_controller=tool_mode_controller,
        chemdraw_shortcut_service=chemdraw_shortcut_service,
    )


__all__ = ["CanvasInputServiceBundle", "build_canvas_input_services"]
