from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.selection_collection_access import selected_scene_items_for
from chemvas.ui.selection_service_access import select_single_structure_item_for
from chemvas.ui.tool_controller import ToolController

if TYPE_CHECKING:
    from chemvas.ui.canvas_color_mutation_service import CanvasColorMutationService
    from chemvas.ui.canvas_graph_service import CanvasGraphService
    from chemvas.ui.canvas_handle_controller import CanvasHandleController
    from chemvas.ui.canvas_hit_testing_service import CanvasHitTestingService
    from chemvas.ui.canvas_note_controller import CanvasNoteController
    from chemvas.ui.canvas_style_controller import CanvasStyleController
    from chemvas.ui.canvas_view import CanvasView
    from chemvas.ui.scene_delete_controller import SceneDeleteController
    from chemvas.ui.scene_transform_controller import SceneTransformController
    from chemvas.ui.selection_controller import SelectionController
    from chemvas.ui.selection_rotation_controller import SelectionRotationController


def build_tool_controller(
    canvas: CanvasView,
    *,
    hit_testing_service: CanvasHitTestingService,
    selection_controller: SelectionController,
    note_controller: CanvasNoteController,
    handle_controller: CanvasHandleController,
    selection_rotation_controller: SelectionRotationController,
    scene_delete_controller: SceneDeleteController,
    scene_transform_controller: SceneTransformController,
    style_controller: CanvasStyleController,
    color_mutation_service: CanvasColorMutationService,
    graph_service: CanvasGraphService,
    history_service,
) -> ToolController:
    return ToolController(
        canvas,
        hit_testing_service=hit_testing_service,
        selection_controller=selection_controller,
        note_controller=note_controller,
        handle_controller=handle_controller,
        selection_rotation_controller=selection_rotation_controller,
        scene_delete_controller=scene_delete_controller,
        scene_transform_controller=scene_transform_controller,
        style_controller=style_controller,
        bond_sets_for_atoms=graph_service.bond_sets_for_atoms,
        color_mutation_service=color_mutation_service,
        selected_scene_items=lambda *, excluded_kinds: selected_scene_items_for(
            canvas,
            excluded_kinds=excluded_kinds,
        ),
        select_single_structure_item=lambda item: select_single_structure_item_for(
            canvas, item
        ),
        atom_symbol_provider=lambda: tool_settings_state_for(canvas).atom_symbol,
        history_service=history_service,
        set_drag_mode=canvas.setDragMode,
        rubber_band_drag_mode=canvas.DragMode.RubberBandDrag,
    )


__all__ = ["build_tool_controller"]
