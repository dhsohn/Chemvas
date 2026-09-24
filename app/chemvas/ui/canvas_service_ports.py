"""A map from a role to its place in the canvas service container.

Access modules ask for a service by role and this module knows which bundle
holds it. Each container path has exactly one name here and every port returns
the concrete service type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.ui.canvas_service_access import canvas_services_for

if TYPE_CHECKING:
    from chemvas.ui.annotations.arrows import ArrowRenderer
    from chemvas.ui.annotations.graphics import (
        AnnotationGraphics,
    )
    from chemvas.ui.atom_label_service import AtomLabelService
    from chemvas.ui.canvas_atom_mutation_service import CanvasAtomMutationService
    from chemvas.ui.canvas_bond_mutation_service import CanvasBondMutationService
    from chemvas.ui.canvas_color_mutation_service import CanvasColorMutationService
    from chemvas.ui.canvas_document_session_service import CanvasDocumentSessionService
    from chemvas.ui.canvas_geometry_controller import CanvasGeometryController
    from chemvas.ui.canvas_history_service import CanvasHistoryService
    from chemvas.ui.canvas_mark_scene_service import CanvasMarkSceneService
    from chemvas.ui.canvas_note_controller import CanvasNoteController
    from chemvas.ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService
    from chemvas.ui.canvas_scene_reset_service import CanvasSceneResetService
    from chemvas.ui.canvas_style_controller import CanvasStyleController
    from chemvas.ui.canvas_tool_mode_controller import CanvasToolModeController
    from chemvas.ui.handle_mutation_service import HandleMutationService
    from chemvas.ui.handle_overlay_service import HandleOverlayService
    from chemvas.ui.history_operations import CanvasHistoryOperations
    from chemvas.ui.insert_controller import InsertController
    from chemvas.ui.scene_clipboard_controller import SceneClipboardController
    from chemvas.ui.scene_decoration_service import SceneDecorationService
    from chemvas.ui.scene_delete_controller import SceneDeleteController
    from chemvas.ui.scene_item_controller import SceneItemController
    from chemvas.ui.scene_transform_controller import SceneTransformController
    from chemvas.ui.structure_build_service import StructureBuildService
    from chemvas.ui.tool_controller import ToolController


def arrow_build_service_for_access(canvas) -> ArrowRenderer:
    return canvas_services_for(canvas).scene_decoration.arrow_build_service


def atom_label_service_for_access(canvas) -> AtomLabelService:
    return canvas_services_for(canvas).atom_label_service


def canvas_window_document_session_service(canvas) -> CanvasDocumentSessionService:
    return canvas_services_for(canvas).document.canvas_document_session_service


def geometry_controller_for_access(canvas) -> CanvasGeometryController:
    return canvas_services_for(canvas).scene_view.geometry_controller


def handle_mutation_service_for_access(canvas) -> HandleMutationService:
    return canvas_services_for(canvas).handles.handle_mutation_service


def handle_overlay_service_for_access(canvas) -> HandleOverlayService:
    return canvas_services_for(canvas).handles.handle_overlay_service


def history_service_for_access(canvas) -> CanvasHistoryService:
    return canvas_services_for(canvas).history_service


def history_operations_for(canvas) -> CanvasHistoryOperations:
    return history_service_for_access(canvas).operations


def tool_mode_controller_for_access(canvas) -> CanvasToolModeController:
    return canvas_services_for(canvas).input.tool_mode_controller


def insert_controller_for_access(canvas) -> InsertController:
    return canvas_services_for(canvas).structure.insert_controller


def mark_scene_service_for_access(canvas) -> CanvasMarkSceneService:
    return canvas_services_for(canvas).scene_decoration.canvas_mark_scene_service


def note_controller_for_access(canvas) -> CanvasNoteController:
    return canvas_services_for(canvas).interaction.note_controller


def ring_fill_scene_service_for_access(canvas) -> CanvasRingFillSceneService:
    return canvas_services_for(canvas).scene_view.canvas_ring_fill_scene_service


def scene_decoration_build_service_for_access(
    canvas,
) -> AnnotationGraphics:
    return canvas_services_for(canvas).scene_decoration.scene_decoration_build_service


def scene_decoration_service_for_access(canvas) -> SceneDecorationService:
    return canvas_services_for(canvas).scene_decoration.scene_decoration_service


def scene_item_controller_for_access(canvas) -> SceneItemController:
    return canvas_services_for(canvas).scene_view.scene_item_controller


def scene_reset_service_for_access(canvas) -> CanvasSceneResetService:
    return canvas_services_for(canvas).document.canvas_scene_reset_service


def scene_transform_controller_for_access(canvas) -> SceneTransformController:
    return canvas_services_for(canvas).scene_operations.scene_transform_controller


def structure_build_service_for_access(canvas) -> StructureBuildService:
    return canvas_services_for(canvas).structure.structure_build_service


def structure_mutation_atom_service(canvas) -> CanvasAtomMutationService:
    return canvas_services_for(canvas).structure.canvas_atom_mutation_service


def structure_mutation_bond_service(canvas) -> CanvasBondMutationService:
    return canvas_services_for(canvas).structure.canvas_bond_mutation_service


def style_controller_for_access(canvas) -> CanvasStyleController:
    return canvas_services_for(canvas).scene_operations.style_controller


def color_mutation_service_for_access(canvas) -> CanvasColorMutationService:
    return canvas_services_for(canvas).scene_operations.canvas_color_mutation_service


def scene_clipboard_controller_for_access(canvas) -> SceneClipboardController:
    return canvas_services_for(canvas).scene_operations.scene_clipboard_controller


def scene_delete_controller_for_access(canvas) -> SceneDeleteController:
    return canvas_services_for(canvas).scene_operations.scene_delete_controller


def tool_controller_for_access(canvas) -> ToolController:
    return canvas_services_for(canvas).tool_controller


__all__ = [
    "arrow_build_service_for_access",
    "atom_label_service_for_access",
    "canvas_window_document_session_service",
    "color_mutation_service_for_access",
    "geometry_controller_for_access",
    "handle_mutation_service_for_access",
    "handle_overlay_service_for_access",
    "history_operations_for",
    "history_service_for_access",
    "insert_controller_for_access",
    "mark_scene_service_for_access",
    "note_controller_for_access",
    "ring_fill_scene_service_for_access",
    "scene_clipboard_controller_for_access",
    "scene_decoration_build_service_for_access",
    "scene_decoration_service_for_access",
    "scene_delete_controller_for_access",
    "scene_item_controller_for_access",
    "scene_reset_service_for_access",
    "scene_transform_controller_for_access",
    "structure_build_service_for_access",
    "structure_mutation_atom_service",
    "structure_mutation_bond_service",
    "style_controller_for_access",
    "tool_controller_for_access",
]
