from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from chemvas.domain.document import AnnotationCollection
from chemvas.features.graph import CanvasGraphState
from chemvas.features.hover import HoverState
from chemvas.features.rendering import ValenceWarningCache
from chemvas.ui.canvas.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas.canvas_bond_graphics_state import CanvasBondGraphicsState
from chemvas.ui.canvas.canvas_calculation_plan_state import CanvasCalculationPlanState
from chemvas.ui.canvas.canvas_callback_state import CanvasCallbackState
from chemvas.ui.canvas.canvas_document_metadata_state import CanvasDocumentMetadataState
from chemvas.ui.canvas.canvas_group_state import CanvasGroupState
from chemvas.ui.canvas.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas.canvas_history_state import CanvasHistoryState
from chemvas.ui.canvas.canvas_insert_state import CanvasInsertState
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.canvas.canvas_text_style_state import CanvasTextStyleState
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.canvas.input_view_state import InputViewState
from chemvas.ui.canvas.sheet_setup_state import SheetSetupState
from chemvas.ui.canvas.spatial_index_state import CanvasSpatialIndexState
from chemvas.ui.molecule.atom_coords_access import CanvasAtomCoords3DState
from chemvas.ui.scene.scene_clipboard_state import SceneClipboardState
from chemvas.ui.scene.scene_render_context import SceneRenderState
from chemvas.ui.selection.selection_info_state import SelectionInfoState
from chemvas.ui.selection.selection_state import SelectionState
from chemvas.ui.selection.selection_update_batch import batch_selection_updates
from chemvas.ui.tools.handle_state import CanvasHandleState

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_view import CanvasView


@dataclass(slots=True, kw_only=True)
class CanvasRuntimeState(SceneRenderState):
    # The canonical, complete state container. State accessors read their field
    # off it directly, and ``slots=True`` makes a renamed or misspelled field
    # raise instead of quietly becoming a second copy of the state.
    document_metadata_state: CanvasDocumentMetadataState
    calculation_plan_state: CanvasCalculationPlanState
    selection_info_state: SelectionInfoState
    group_state: CanvasGroupState
    insert_state: CanvasInsertState
    history_state: CanvasHistoryState
    history_service: CanvasHistoryService
    spatial_index_state: CanvasSpatialIndexState
    input_view_state: InputViewState
    handle_state: CanvasHandleState
    selection_state: SelectionState
    hover_preview_state: HoverState
    callback_state: CanvasCallbackState
    scene_clipboard_state: SceneClipboardState
    valence_warnings: ValenceWarningCache

    @classmethod
    def create(cls, canvas: CanvasView) -> CanvasRuntimeState:
        from chemvas.ui.history.history_operations import CanvasHistoryOperations

        history_state = CanvasHistoryState()
        return cls(
            document_metadata_state=CanvasDocumentMetadataState(),
            calculation_plan_state=CanvasCalculationPlanState(),
            sheet_setup_state=SheetSetupState(),
            selection_info_state=SelectionInfoState(),
            graph_state=CanvasGraphState(),
            group_state=CanvasGroupState(),
            insert_state=CanvasInsertState(),
            history_state=history_state,
            history_service=CanvasHistoryService(
                CanvasHistoryOperations(canvas),
                history_state,
                replay_context=partial(batch_selection_updates, canvas),
            ),
            atom_coords_3d_state=CanvasAtomCoords3DState(),
            atom_graphics_state=CanvasAtomGraphicsState(),
            bond_graphics_state=CanvasBondGraphicsState(),
            mark_registry=CanvasMarkRegistry(),
            spatial_index_state=CanvasSpatialIndexState(),
            input_view_state=InputViewState(),
            rotation_state=CanvasRotationState(),
            handle_state=CanvasHandleState(),
            selection_state=SelectionState(),
            text_style_state=CanvasTextStyleState(),
            tool_settings_state=CanvasToolSettingsState(),
            hover_preview_state=HoverState(),
            callback_state=CanvasCallbackState(),
            scene_clipboard_state=SceneClipboardState(),
            scene_items_state=CanvasSceneItemsState(),
            shape_state=AnnotationCollection(),
            valence_warnings=ValenceWarningCache(),
            ts_bracket_state=AnnotationCollection(),
        )


def attach_canvas_runtime_state(canvas: CanvasView) -> CanvasRuntimeState:
    state = CanvasRuntimeState.create(canvas)
    canvas.runtime_state = state
    return state


__all__ = ["CanvasRuntimeState", "attach_canvas_runtime_state"]
