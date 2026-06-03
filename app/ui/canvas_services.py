from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ui.atom_label_service import AtomLabelService
from ui.benzene_preview_service import BenzenePreviewService
from ui.bond_hover_preview_service import BondHoverPreviewService
from ui.canvas_atom_mutation_service import CanvasAtomMutationService
from ui.canvas_bond_mutation_service import CanvasBondMutationService
from ui.canvas_chemdraw_shortcut_service import CanvasChemdrawShortcutService
from ui.canvas_color_mutation_service import CanvasColorMutationService
from ui.canvas_document_session_service import CanvasDocumentSessionService
from ui.canvas_geometry_controller import CanvasGeometryController
from ui.canvas_graph_service import CanvasGraphService
from ui.canvas_handle_controller import CanvasHandleController
from ui.canvas_history_recording_service import CanvasHistoryRecordingService
from ui.canvas_hit_testing_service import CanvasHitTestingService
from ui.canvas_input_controller import CanvasInputController
from ui.canvas_mark_scene_service import CanvasMarkSceneService
from ui.canvas_move_controller import CanvasMoveController
from ui.canvas_note_controller import CanvasNoteController
from ui.canvas_pointer_controller import CanvasPointerController
from ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService
from ui.canvas_rotation_preview_controller import CanvasRotationPreviewController
from ui.canvas_scene_decoration_build_service import CanvasSceneDecorationBuildService
from ui.canvas_scene_reset_service import CanvasSceneResetService
from ui.curved_arrow_path_service import CurvedArrowPathService
from ui.handle_mutation_service import HandleMutationService
from ui.handle_overlay_service import HandleOverlayService
from ui.hover_interaction_service import HoverInteractionService
from ui.hover_scene_service import HoverSceneService
from ui.insert_controller import InsertController
from ui.mark_hover_preview_service import MarkHoverPreviewService
from ui.scene_decoration_service import SceneDecorationService
from ui.scene_item_controller import SceneItemController
from ui.scene_ops_controller import SceneOpsController
from ui.selection_controller import SelectionController
from ui.selection_highlight_styler import SelectionHighlightStyler
from ui.selection_rotation_controller import SelectionRotationController
from ui.structure_build_service import StructureBuildService
from ui.structure_insert_service import StructureInsertService
from ui.tools import ToolController


@dataclass(slots=True)
class CanvasServices:
    selection_controller: SelectionController
    scene_item_controller: SceneItemController
    scene_ops_controller: SceneOpsController
    insert_controller: InsertController
    input_controller: CanvasInputController
    handle_controller: CanvasHandleController
    handle_overlay_service: HandleOverlayService
    handle_mutation_service: HandleMutationService
    curved_arrow_path_service: CurvedArrowPathService
    selection_highlight_styler: SelectionHighlightStyler
    move_controller: CanvasMoveController
    note_controller: CanvasNoteController
    pointer_controller: CanvasPointerController
    geometry_controller: CanvasGeometryController
    canvas_atom_mutation_service: CanvasAtomMutationService
    canvas_bond_mutation_service: CanvasBondMutationService
    chemdraw_shortcut_service: CanvasChemdrawShortcutService
    hit_testing_service: CanvasHitTestingService
    canvas_color_mutation_service: CanvasColorMutationService
    canvas_document_session_service: CanvasDocumentSessionService
    canvas_graph_service: CanvasGraphService
    canvas_history_recording_service: CanvasHistoryRecordingService
    canvas_mark_scene_service: CanvasMarkSceneService
    canvas_ring_fill_scene_service: CanvasRingFillSceneService
    canvas_scene_reset_service: CanvasSceneResetService
    rotation_preview_controller: CanvasRotationPreviewController
    atom_label_service: AtomLabelService
    hover_interaction_service: HoverInteractionService
    hover_scene_service: HoverSceneService
    mark_hover_preview_service: MarkHoverPreviewService
    bond_hover_preview_service: BondHoverPreviewService
    structure_build_service: StructureBuildService
    benzene_preview_service: BenzenePreviewService
    scene_decoration_build_service: CanvasSceneDecorationBuildService
    scene_decoration_service: SceneDecorationService
    structure_insert_service: StructureInsertService
    selection_rotation_controller: SelectionRotationController
    tools: ToolController


def build_canvas_services(
    canvas: Any,
    *,
    graph_state,
    insert_state,
    history_service,
) -> CanvasServices:
    return CanvasServices(
        selection_controller=SelectionController(canvas),
        scene_item_controller=SceneItemController(canvas),
        scene_ops_controller=SceneOpsController(canvas),
        insert_controller=InsertController(canvas, insert_state=insert_state),
        input_controller=CanvasInputController(canvas),
        handle_controller=CanvasHandleController(canvas),
        handle_overlay_service=HandleOverlayService(canvas),
        handle_mutation_service=HandleMutationService(canvas),
        curved_arrow_path_service=CurvedArrowPathService(canvas),
        selection_highlight_styler=SelectionHighlightStyler(canvas),
        move_controller=CanvasMoveController(canvas),
        note_controller=CanvasNoteController(canvas),
        pointer_controller=CanvasPointerController(canvas),
        geometry_controller=CanvasGeometryController(canvas),
        canvas_atom_mutation_service=CanvasAtomMutationService(canvas),
        canvas_bond_mutation_service=CanvasBondMutationService(canvas),
        chemdraw_shortcut_service=CanvasChemdrawShortcutService(canvas),
        hit_testing_service=CanvasHitTestingService(canvas),
        canvas_color_mutation_service=CanvasColorMutationService(canvas),
        canvas_document_session_service=CanvasDocumentSessionService(canvas),
        canvas_graph_service=CanvasGraphService(canvas, graph_state),
        canvas_history_recording_service=CanvasHistoryRecordingService(canvas, history_service=history_service),
        canvas_mark_scene_service=CanvasMarkSceneService(canvas),
        canvas_ring_fill_scene_service=CanvasRingFillSceneService(canvas),
        canvas_scene_reset_service=CanvasSceneResetService(canvas),
        rotation_preview_controller=CanvasRotationPreviewController(canvas),
        atom_label_service=AtomLabelService(canvas),
        hover_interaction_service=HoverInteractionService(canvas),
        hover_scene_service=HoverSceneService(canvas),
        mark_hover_preview_service=MarkHoverPreviewService(canvas),
        bond_hover_preview_service=BondHoverPreviewService(canvas),
        structure_build_service=StructureBuildService(canvas),
        benzene_preview_service=BenzenePreviewService(canvas),
        scene_decoration_build_service=CanvasSceneDecorationBuildService(canvas),
        scene_decoration_service=SceneDecorationService(canvas),
        structure_insert_service=StructureInsertService(canvas),
        selection_rotation_controller=SelectionRotationController(canvas),
        tools=ToolController(canvas),
    )


def attach_canvas_services(canvas: Any, services: CanvasServices) -> None:
    for field_name in CanvasServices.__dataclass_fields__:
        setattr(canvas, f"_{field_name}", getattr(services, field_name))
    canvas.tools = services.tools


__all__ = ["CanvasServices", "attach_canvas_services", "build_canvas_services"]
