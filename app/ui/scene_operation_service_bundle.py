from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ui.canvas_color_mutation_service import CanvasColorMutationService
from ui.canvas_style_controller import CanvasStyleController
from ui.scene_clipboard_controller import SceneClipboardController
from ui.scene_delete_controller import SceneDeleteController
from ui.scene_transform_controller import SceneTransformController

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class SceneOperationServiceBundle:
    scene_clipboard_controller: SceneClipboardController
    scene_delete_controller: SceneDeleteController
    scene_transform_controller: SceneTransformController
    style_controller: CanvasStyleController
    canvas_color_mutation_service: CanvasColorMutationService


def build_scene_operation_services(
    canvas: CanvasView | Any,
    *,
    selection_controller: Any,
    move_controller: Any,
    atom_mutation_service: Any,
    bond_mutation_service: Any,
    note_controller: Any,
    graph_service: Any,
    history_service: Any,
) -> SceneOperationServiceBundle:
    style_controller = CanvasStyleController(
        canvas,
        note_controller=note_controller,
    )
    scene_clipboard_controller = SceneClipboardController(
        canvas,
        selection_controller=selection_controller,
        bond_mutation_service=bond_mutation_service,
    )
    scene_delete_controller = SceneDeleteController(
        canvas,
        move_controller=move_controller,
        atom_mutation_service=atom_mutation_service,
        bond_mutation_service=bond_mutation_service,
        style_controller=style_controller,
        history_service=history_service,
    )
    scene_transform_controller = SceneTransformController(
        canvas,
        move_controller=move_controller,
        graph_service=graph_service,
        history_service=history_service,
    )
    canvas_color_mutation_service = CanvasColorMutationService(
        canvas,
        graph_service=graph_service,
        history_service=history_service,
    )
    return SceneOperationServiceBundle(
        scene_clipboard_controller=scene_clipboard_controller,
        scene_delete_controller=scene_delete_controller,
        scene_transform_controller=scene_transform_controller,
        style_controller=style_controller,
        canvas_color_mutation_service=canvas_color_mutation_service,
    )


__all__ = ["SceneOperationServiceBundle", "build_scene_operation_services"]
