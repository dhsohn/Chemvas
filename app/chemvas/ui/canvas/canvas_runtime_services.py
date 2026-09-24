"""Typed runtime services for a canvas.

Every runtime the canvas assembles is a direct field. The types are named
under ``TYPE_CHECKING`` only: this module imports none of them at run time, so
it stays a leaf of the eager import graph while mypy still sees what the
container holds. ``chemvas.ui.canvas.canvas_services`` builds it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.ui.annotations.arrows import ArrowRenderer
    from chemvas.ui.annotations.graphics import AnnotationGraphics
    from chemvas.ui.canvas.canvas_atom_mutation_service import CanvasAtomMutationService
    from chemvas.ui.canvas.canvas_bond_mutation_service import CanvasBondMutationService
    from chemvas.ui.canvas.canvas_chemdraw_shortcut_service import (
        CanvasChemdrawShortcutService,
    )
    from chemvas.ui.canvas.canvas_color_mutation_service import (
        CanvasColorMutationService,
    )
    from chemvas.ui.canvas.canvas_document_session_service import (
        CanvasDocumentSessionService,
    )
    from chemvas.ui.canvas.canvas_geometry_controller import CanvasGeometryController
    from chemvas.ui.canvas.canvas_graph_service import CanvasGraphService
    from chemvas.ui.canvas.canvas_handle_controller import CanvasHandleController
    from chemvas.ui.canvas.canvas_history_recording_service import (
        CanvasHistoryRecordingService,
    )
    from chemvas.ui.canvas.canvas_history_service import CanvasHistoryService
    from chemvas.ui.canvas.canvas_hit_testing_service import CanvasHitTestingService
    from chemvas.ui.canvas.canvas_input_controller import CanvasInputController
    from chemvas.ui.canvas.canvas_mark_scene_service import CanvasMarkSceneService
    from chemvas.ui.canvas.canvas_move_controller import CanvasMoveController
    from chemvas.ui.canvas.canvas_note_controller import CanvasNoteController
    from chemvas.ui.canvas.canvas_pointer_controller import CanvasPointerController
    from chemvas.ui.canvas.canvas_ring_fill_scene_service import (
        CanvasRingFillSceneService,
    )
    from chemvas.ui.canvas.canvas_scene_reset_service import CanvasSceneResetService
    from chemvas.ui.canvas.canvas_style_controller import CanvasStyleController
    from chemvas.ui.canvas.canvas_tool_mode_controller import CanvasToolModeController
    from chemvas.ui.insert.insert_controller import InsertController
    from chemvas.ui.molecule.atom_label_service import AtomLabelService
    from chemvas.ui.molecule.structure_build_service import StructureBuildService
    from chemvas.ui.scene.scene_clipboard_controller import SceneClipboardController
    from chemvas.ui.scene.scene_decoration_service import SceneDecorationService
    from chemvas.ui.scene.scene_delete_controller import SceneDeleteController
    from chemvas.ui.scene.scene_item_controller import SceneItemController
    from chemvas.ui.scene.scene_transform_controller import SceneTransformController
    from chemvas.ui.selection.selection_controller import SelectionController
    from chemvas.ui.selection.selection_rotation_controller import (
        SelectionRotationController,
    )
    from chemvas.ui.tools.handle_mutation_service import HandleMutationService
    from chemvas.ui.tools.handle_overlay_service import HandleOverlayService
    from chemvas.ui.tools.hover import HoverController
    from chemvas.ui.tools.tool_controller import ToolController


@dataclass(slots=True, kw_only=True)
class CanvasRuntimeServices:
    graph_service: CanvasGraphService
    hit_testing_service: CanvasHitTestingService
    selection: SelectionController
    hover: HoverController
    tool_controller: ToolController
    atom_label_service: AtomLabelService
    history_service: CanvasHistoryService
    # handles
    handle_controller: CanvasHandleController
    handle_overlay_service: HandleOverlayService
    handle_mutation_service: HandleMutationService
    # interaction
    note_controller: CanvasNoteController
    move_controller: CanvasMoveController
    selection_rotation_controller: SelectionRotationController
    # structure
    canvas_atom_mutation_service: CanvasAtomMutationService
    canvas_bond_mutation_service: CanvasBondMutationService
    structure_build_service: StructureBuildService
    insert_controller: InsertController
    # scene operations
    scene_clipboard_controller: SceneClipboardController
    scene_delete_controller: SceneDeleteController
    scene_transform_controller: SceneTransformController
    style_controller: CanvasStyleController
    canvas_color_mutation_service: CanvasColorMutationService
    # scene decoration
    arrow_build_service: ArrowRenderer
    canvas_mark_scene_service: CanvasMarkSceneService
    scene_decoration_build_service: AnnotationGraphics
    scene_decoration_service: SceneDecorationService
    # input
    input_controller: CanvasInputController
    pointer_controller: CanvasPointerController
    tool_mode_controller: CanvasToolModeController
    chemdraw_shortcut_service: CanvasChemdrawShortcutService
    # document
    canvas_document_session_service: CanvasDocumentSessionService
    canvas_history_recording_service: CanvasHistoryRecordingService
    canvas_scene_reset_service: CanvasSceneResetService
    # scene view
    scene_item_controller: SceneItemController
    geometry_controller: CanvasGeometryController
    canvas_ring_fill_scene_service: CanvasRingFillSceneService


__all__ = ["CanvasRuntimeServices"]
