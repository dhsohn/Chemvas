from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.domain.document import arrow_from_state

if TYPE_CHECKING:
    from collections.abc import Mapping

    from PyQt6.QtCore import QPointF

    from chemvas.domain.document import Arrow

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
        self, *, handle_overlay_service=None, handle_mutation_service=None
    ) -> None:
        self.handle_overlay_service = handle_overlay_service
        self.handle_mutation_service = handle_mutation_service

    def show_orbital_handles(self, item) -> None:
        if self.handle_overlay_service is not None:
            self.handle_overlay_service.show_orbital_handles(item)

    def show_curved_handles(self, item) -> None:
        if self.handle_overlay_service is not None:
            self.handle_overlay_service.show_curved_handles(item)

    def show_endpoint_handles(self, item) -> None:
        if self.handle_overlay_service is not None:
            self.handle_overlay_service.show_endpoint_handles(item)

    def show_shape_handles(self, item) -> None:
        if self.handle_overlay_service is not None:
            self.handle_overlay_service.show_shape_handles(item)

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
            self.update_orbital_scale(target, scene_pos)
            self.show_orbital_handles(target)
        elif handle_type == "orbital_rotate":
            self.update_orbital_rotate(target, scene_pos)
            self.show_orbital_handles(target)
        elif handle_type == "curved_control":
            self.update_curved_control(target, scene_pos)
            self.show_curved_handles(target)
        elif handle_type in _ENDPOINT_HANDLE_ENDS:
            self.update_arrow_endpoint(
                target,
                scene_pos,
                _ENDPOINT_HANDLE_ENDS[handle_type],
                pressed=arrow_from_state(pressed_state),
            )
            if handle_type.startswith("curved_"):
                self.show_curved_handles(target)
            else:
                self.show_endpoint_handles(target)
        elif handle_type.startswith("shape_"):
            self.update_shape_resize(target, handle_type, scene_pos)
            self.show_shape_handles(target)

    def update_orbital_scale(self, item, pos: QPointF) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_orbital_scale(item, pos)

    def update_orbital_rotate(self, item, pos: QPointF) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_orbital_rotate(item, pos)

    def update_curved_control(self, item, pos: QPointF) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_curved_control(item, pos)

    def update_shape_resize(self, item, anchor: str, pos: QPointF) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_shape_resize(item, anchor, pos)

    def update_arrow_endpoint(
        self, item, pos: QPointF, endpoint: str, *, pressed: Arrow
    ) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_arrow_endpoint(
                item, pos, endpoint, pressed=pressed
            )


__all__ = ["CanvasHandleController"]
