"""Assemble every runtime service a canvas owns, in dependency order."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from chemvas.features.selection import ActiveToolReference
from chemvas.ui.canvas.canvas_atom_mutation_service import CanvasAtomMutationService
from chemvas.ui.canvas.canvas_bond_mutation_service import CanvasBondMutationService
from chemvas.ui.canvas.canvas_chemdraw_shortcut_service import (
    CanvasChemdrawShortcutService,
)
from chemvas.ui.canvas.canvas_color_mutation_service import CanvasColorMutationService
from chemvas.ui.canvas.canvas_document_session_service import (
    CanvasDocumentSessionService,
)
from chemvas.ui.canvas.canvas_geometry_controller import CanvasGeometryController
from chemvas.ui.canvas.canvas_graph_service import CanvasGraphService
from chemvas.ui.canvas.canvas_handle_controller import CanvasHandleController
from chemvas.ui.canvas.canvas_history_recording_service import (
    CanvasHistoryRecordingService,
)
from chemvas.ui.canvas.canvas_hit_testing_service import CanvasHitTestingService
from chemvas.ui.canvas.canvas_input_controller import CanvasInputController
from chemvas.ui.canvas.canvas_mark_scene_service import CanvasMarkSceneService
from chemvas.ui.canvas.canvas_move_controller import CanvasMoveController
from chemvas.ui.canvas.canvas_note_controller import CanvasNoteController
from chemvas.ui.canvas.canvas_pointer_controller import CanvasPointerController
from chemvas.ui.canvas.canvas_ring_fill_scene_service import CanvasRingFillSceneService
from chemvas.ui.canvas.canvas_runtime_services import CanvasRuntimeServices
from chemvas.ui.canvas.canvas_scene_reset_service import CanvasSceneResetService
from chemvas.ui.canvas.canvas_style_controller import CanvasStyleController
from chemvas.ui.canvas.canvas_tool_mode_controller import CanvasToolModeController
from chemvas.ui.canvas.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.canvas.canvas_view_ports import scene_pos_from_event_for_view
from chemvas.ui.insert.insert_controller import InsertController
from chemvas.ui.molecule.atom_label_service import AtomLabelService
from chemvas.ui.molecule.structure_build_service import StructureBuildService
from chemvas.ui.scene.scene_clipboard_controller import SceneClipboardController
from chemvas.ui.scene.scene_decoration_service import SceneDecorationService
from chemvas.ui.scene.scene_delete_controller import SceneDeleteController
from chemvas.ui.scene.scene_item_controller import SceneItemController
from chemvas.ui.scene.scene_item_lifecycle_service import SceneItemLifecycleService
from chemvas.ui.scene.scene_transform_controller import SceneTransformController
from chemvas.ui.selection.selection_controller import SelectionController
from chemvas.ui.selection.selection_queries import selected_scene_items_for
from chemvas.ui.selection.selection_rotation_controller import (
    SelectionRotationController,
)
from chemvas.ui.selection.selection_state import selection_for
from chemvas.ui.tools.handle_mutation_service import HandleMutationService
from chemvas.ui.tools.handle_overlay_service import HandleOverlayService
from chemvas.ui.tools.hover import HoverController
from chemvas.ui.tools.tool_controller import ToolController

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_history_service import CanvasHistoryService


def build_canvas_services(
    canvas: Any,
    *,
    graph_state,
    insert_state,
    history_service: CanvasHistoryService,
) -> CanvasRuntimeServices:
    graph_service = CanvasGraphService(canvas, graph_state=graph_state)
    active_tool_reference = ActiveToolReference()

    hit_testing_service = CanvasHitTestingService(
        canvas,
        scene_pos_mapper=lambda event: scene_pos_from_event_for_view(canvas, event),
        viewport_transform=lambda: canvas.viewportTransform(),
    )
    selection = SelectionController(
        canvas,
        graph_service=graph_service,
        active_tool_name_provider=active_tool_reference.active_tool_name,
        hit_testing_service=hit_testing_service,
    )

    handle_overlay_service = HandleOverlayService(canvas)
    handle_mutation_service = HandleMutationService(canvas)
    handle_controller = CanvasHandleController(
        canvas,
        handle_overlay_service=handle_overlay_service,
        handle_mutation_service=handle_mutation_service,
    )

    note_controller = CanvasNoteController(
        canvas,
        selection_controller=selection,
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

    canvas_atom_mutation_service = CanvasAtomMutationService(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
    )
    canvas_bond_mutation_service = CanvasBondMutationService(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        atom_label_relayout=lambda atom_ids: (
            canvas.services.atom_label_service.relayout_atom_labels(atom_ids)
        ),
    )
    structure_build_service = StructureBuildService(
        canvas,
        hit_testing_service=hit_testing_service,
        move_controller=move_controller,
        graph_service=graph_service,
    )
    insert_controller = InsertController(
        canvas,
        insert_state=insert_state,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
    )

    style_controller = CanvasStyleController(
        canvas,
        note_controller=note_controller,
        history_service=history_service,
    )
    scene_clipboard_controller = SceneClipboardController(
        canvas,
        selection_controller=selection,
        bond_mutation_service=canvas_bond_mutation_service,
    )
    scene_delete_controller = SceneDeleteController(
        canvas,
        move_controller=move_controller,
        atom_mutation_service=canvas_atom_mutation_service,
        bond_mutation_service=canvas_bond_mutation_service,
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
        note_controller=note_controller,
        history_service=history_service,
    )

    tool_controller = ToolController(
        canvas,
        hit_testing_service=hit_testing_service,
        move_controller=move_controller,
        selection_controller=selection,
        note_controller=note_controller,
        handle_controller=handle_controller,
        selection_rotation_controller=selection_rotation_controller,
        scene_delete_controller=scene_delete_controller,
        scene_transform_controller=scene_transform_controller,
        style_controller=style_controller,
        bond_sets_for_atoms=graph_service.bond_sets_for_atoms,
        color_mutation_service=canvas_color_mutation_service,
        selected_scene_items=lambda *, excluded_kinds: selected_scene_items_for(
            canvas,
            excluded_kinds=excluded_kinds,
        ),
        select_single_structure_item=lambda item: selection_for(
            canvas
        ).select_single_structure_item(item),
        atom_symbol_provider=lambda: tool_settings_state_for(canvas).atom_symbol,
        history_service=history_service,
        set_drag_mode=canvas.setDragMode,
        rubber_band_drag_mode=canvas.DragMode.RubberBandDrag,
    )
    active_tool_reference.tool_controller = tool_controller

    render_context = canvas.render_context
    arrow_build_service = render_context.arrows
    scene_decoration_build_service = render_context.decorations
    scene_decoration_service = SceneDecorationService(
        canvas, history_service=history_service
    )
    canvas_mark_scene_service = CanvasMarkSceneService(
        canvas,
        scene_decoration_service=scene_decoration_service,
        history_service=history_service,
    )

    hover_controller = HoverController(
        canvas,
        selection_controller=selection,
        hit_testing_service=hit_testing_service,
        insert_controller=insert_controller,
        scene_decoration_build_service=scene_decoration_build_service,
        mark_scene_service=canvas_mark_scene_service,
        active_tool_name_provider=active_tool_reference.active_tool_name,
    )

    tool_mode_controller = CanvasToolModeController(
        canvas,
        insert_controller=insert_controller,
        hover_refresh=hover_controller.refresh,
        set_active_tool=tool_controller.set_active,
    )
    pointer_controller = CanvasPointerController(
        canvas,
        hit_testing_service=hit_testing_service,
        insert_controller=insert_controller,
        hover_controller=hover_controller,
        tool_controller=tool_controller,
        scene_transform_controller=scene_transform_controller,
    )
    chemdraw_shortcut_service = CanvasChemdrawShortcutService(
        canvas,
        scene_transform_controller=scene_transform_controller,
        tool_mode_controller=tool_mode_controller,
        mark_scene_service=canvas_mark_scene_service,
    )
    input_controller = CanvasInputController(
        canvas,
        scene_delete_controller=scene_delete_controller,
        scene_clipboard_controller=scene_clipboard_controller,
        history_service=history_service,
        hover_controller=hover_controller,
        chemdraw_shortcut_service=chemdraw_shortcut_service,
        tool_mode_controller=tool_mode_controller,
        prepare_for_document_edit=tool_controller.prepare_for_document_edit,
        cancel_active_gesture=tool_controller.cancel_active_gesture,
    )

    canvas_document_session_service = CanvasDocumentSessionService(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        history_service=history_service,
    )
    canvas_history_recording_service = CanvasHistoryRecordingService(
        canvas,
        history_service=history_service,
    )
    canvas_scene_reset_service = CanvasSceneResetService(
        canvas,
        hit_testing_service=hit_testing_service,
    )

    scene_item_lifecycle_service = SceneItemLifecycleService(
        canvas, graph_service=graph_service
    )
    scene_item_controller = SceneItemController(
        canvas,
        graph_service=graph_service,
        lifecycle_service=scene_item_lifecycle_service,
    )
    geometry_controller = CanvasGeometryController(
        canvas,
        hit_testing_service=hit_testing_service,
        history_service=history_service,
    )
    canvas_ring_fill_scene_service = CanvasRingFillSceneService(canvas)

    atom_label_service = AtomLabelService(
        canvas,
        move_controller=move_controller,
        graph_service=graph_service,
        history_service=history_service,
        hover_refresh=hover_controller.refresh,
    )

    return CanvasRuntimeServices(
        graph_service=graph_service,
        hit_testing_service=hit_testing_service,
        selection=selection,
        hover=hover_controller,
        tool_controller=tool_controller,
        atom_label_service=atom_label_service,
        history_service=history_service,
        handle_controller=handle_controller,
        handle_overlay_service=handle_overlay_service,
        handle_mutation_service=handle_mutation_service,
        note_controller=note_controller,
        move_controller=move_controller,
        selection_rotation_controller=selection_rotation_controller,
        canvas_atom_mutation_service=canvas_atom_mutation_service,
        canvas_bond_mutation_service=canvas_bond_mutation_service,
        structure_build_service=structure_build_service,
        insert_controller=insert_controller,
        scene_clipboard_controller=scene_clipboard_controller,
        scene_delete_controller=scene_delete_controller,
        scene_transform_controller=scene_transform_controller,
        style_controller=style_controller,
        canvas_color_mutation_service=canvas_color_mutation_service,
        arrow_build_service=arrow_build_service,
        canvas_mark_scene_service=canvas_mark_scene_service,
        scene_decoration_build_service=scene_decoration_build_service,
        scene_decoration_service=scene_decoration_service,
        input_controller=input_controller,
        pointer_controller=pointer_controller,
        tool_mode_controller=tool_mode_controller,
        chemdraw_shortcut_service=chemdraw_shortcut_service,
        canvas_document_session_service=canvas_document_session_service,
        canvas_history_recording_service=canvas_history_recording_service,
        canvas_scene_reset_service=canvas_scene_reset_service,
        scene_item_controller=scene_item_controller,
        geometry_controller=geometry_controller,
        canvas_ring_fill_scene_service=canvas_ring_fill_scene_service,
    )


def attach_canvas_services(canvas: Any, services: CanvasRuntimeServices) -> None:
    canvas.services = services


__all__ = [
    "CanvasRuntimeServices",
    "attach_canvas_services",
    "build_canvas_services",
]
