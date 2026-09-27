from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.domain.document import arrow_from_state

if TYPE_CHECKING:
    from collections.abc import Mapping

    from PyQt6.QtCore import QPointF

    from chemvas.ui.tools.handle_mutation_service import HandleMutationService
    from chemvas.ui.tools.handle_overlay_service import HandleOverlayService

# The arrow end each endpoint handle moves. Curved arrows keep their own
# handle set, with the control handle between the ends.
_ENDPOINT_HANDLE_ENDS = {
    "arrow_start": "start",
    "arrow_end": "end",
    "curved_start": "start",
    "curved_end": "end",
}


class CanvasHandleController:
    def __init__(
        self,
        *,
        handle_overlay_service: HandleOverlayService,
        handle_mutation_service: HandleMutationService,
    ) -> None:
        self.handle_overlay_service = handle_overlay_service
        self.handle_mutation_service = handle_mutation_service

    def update_handle_drag(
        self, handle, scene_pos: QPointF, pressed_state: Mapping[str, object]
    ) -> None:
        """Apply one frame of a handle drag.

        ``pressed_state`` is the target's state when the drag began. Endpoint
        handles compute each frame from it; other handles apply the pointer to
        the current record.
        """
        handle_type = handle.data(1)
        target = handle.data(2)
        if target is None:
            return
        if handle_type == "orbital_scale":
            self.handle_mutation_service.update_orbital_scale(target, scene_pos)
            self.handle_overlay_service.show_orbital_handles(target)
        elif handle_type == "orbital_rotate":
            self.handle_mutation_service.update_orbital_rotate(target, scene_pos)
            self.handle_overlay_service.show_orbital_handles(target)
        elif handle_type == "curved_control":
            self.handle_mutation_service.update_curved_control(target, scene_pos)
            self.handle_overlay_service.show_curved_handles(target)
        elif handle_type in _ENDPOINT_HANDLE_ENDS:
            self.handle_mutation_service.update_arrow_endpoint(
                target,
                scene_pos,
                _ENDPOINT_HANDLE_ENDS[handle_type],
                pressed=arrow_from_state(pressed_state),
            )
            if handle_type.startswith("curved_"):
                self.handle_overlay_service.show_curved_handles(target)
            else:
                self.handle_overlay_service.show_endpoint_handles(target)
        elif handle_type.startswith("shape_"):
            self.handle_mutation_service.update_shape_resize(
                target, handle_type, scene_pos
            )
            self.handle_overlay_service.show_shape_handles(target)


__all__ = ["CanvasHandleController"]
