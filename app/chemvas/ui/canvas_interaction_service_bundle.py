from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.ui.canvas_move_controller import CanvasMoveController
from chemvas.ui.canvas_note_controller import CanvasNoteController
from chemvas.ui.selection_rotation_controller import SelectionRotationController

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


@dataclass(slots=True)
class CanvasInteractionServiceBundle:
    note_controller: CanvasNoteController
    move_controller: CanvasMoveController
    selection_rotation_controller: SelectionRotationController


def build_canvas_interaction_services(
    canvas: CanvasView | Any,
    *,
    selection_controller: Any,
    hit_testing_service: Any,
    graph_service: Any,
    history_service: Any,
) -> CanvasInteractionServiceBundle:
    note_controller = CanvasNoteController(
        canvas,
        selection_controller=selection_controller,
        history_service=history_service,
    )
    move_controller = CanvasMoveController(
        canvas,
        hit_testing_service=hit_testing_service,
    )
    selection_rotation_controller = SelectionRotationController(
        canvas,
        move_controller=move_controller,
        graph_service=graph_service,
        history_service=history_service,
    )
    return CanvasInteractionServiceBundle(
        note_controller=note_controller,
        move_controller=move_controller,
        selection_rotation_controller=selection_rotation_controller,
    )


__all__ = ["CanvasInteractionServiceBundle", "build_canvas_interaction_services"]
