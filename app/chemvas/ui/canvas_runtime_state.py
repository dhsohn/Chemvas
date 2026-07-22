from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar
from weakref import ref

from PyQt6.QtCore import QObject, QTimer, pyqtSlot

from chemvas.features.hover import HoverState
from chemvas.ui.atom_coords_access import CanvasAtomCoords3DState
from chemvas.ui.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas_bond_graphics_state import CanvasBondGraphicsState
from chemvas.ui.canvas_callback_state import CanvasCallbackState
from chemvas.ui.canvas_document_metadata_state import CanvasDocumentMetadataState
from chemvas.ui.canvas_graph_state import CanvasGraphState
from chemvas.ui.canvas_group_state import CanvasGroupState
from chemvas.ui.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas_history_state import CanvasHistoryState
from chemvas.ui.canvas_insert_state import CanvasInsertState
from chemvas.ui.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.canvas_smiles_input_state import CanvasSmilesInputState
from chemvas.ui.canvas_text_style_state import CanvasTextStyleState
from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.handle_state import CanvasHandleState
from chemvas.ui.input_view_state import InputViewState
from chemvas.ui.scene_clipboard_state import SceneClipboardState
from chemvas.ui.selection_info_access import maybe_warm_rdkit_for
from chemvas.ui.selection_info_state import SelectionInfoState, selection_info_state_for
from chemvas.ui.selection_outline_state import SelectionOutlineState
from chemvas.ui.selection_style_state import SelectionStyleState
from chemvas.ui.sheet_setup_state import SheetSetupState
from chemvas.ui.spatial_index_state import CanvasSpatialIndexState


class RdkitIdleWarmupBridge(QObject):
    def __init__(self, canvas: Any) -> None:
        super().__init__(canvas)
        self._canvas_ref = ref(canvas)
        self.timer: QTimer | None = None

    @pyqtSlot()
    def warm_when_idle(self) -> None:
        canvas = self._canvas_ref()
        if canvas is None:
            return
        maybe_warm_rdkit_for(canvas)
        # Stop polling once no warmup is outstanding. The timer is re-armed on
        # demand when a new selection needs RDKit (see
        # ``selection_info_access.emit_selection_info_for``), so idle canvases do
        # not keep firing timers.
        if (
            self.timer is not None
            and not selection_info_state_for(canvas).rdkit_warmup_pending
        ):
            self.timer.stop()


@dataclass(slots=True)
class CanvasRuntimeState:
    # Marks this as the canonical, complete state container: state accessors
    # refuse to shadow a missing field on it (see ensure_canvas_state).
    STRICT_STATE_CONTAINER: ClassVar[bool] = True

    document_metadata_state: CanvasDocumentMetadataState
    sheet_setup_state: SheetSetupState
    selection_info_state: SelectionInfoState
    rdkit_idle_timer: QTimer
    rdkit_idle_warmup_bridge: RdkitIdleWarmupBridge
    graph_state: CanvasGraphState
    group_state: CanvasGroupState
    insert_state: CanvasInsertState
    history_state: CanvasHistoryState
    history_service: CanvasHistoryService
    atom_coords_3d_state: CanvasAtomCoords3DState
    atom_graphics_state: CanvasAtomGraphicsState
    bond_graphics_state: CanvasBondGraphicsState
    mark_registry: CanvasMarkRegistry
    spatial_index_state: CanvasSpatialIndexState
    input_view_state: InputViewState
    rotation_state: CanvasRotationState
    handle_state: CanvasHandleState
    selection_style_state: SelectionStyleState
    selection_outline_state: SelectionOutlineState
    text_style_state: CanvasTextStyleState
    tool_settings_state: CanvasToolSettingsState
    hover_preview_state: HoverState
    callback_state: CanvasCallbackState
    scene_clipboard_state: SceneClipboardState
    scene_items_state: CanvasSceneItemsState
    smiles_input_state: CanvasSmilesInputState
    contexts: dict[str, object]

    @classmethod
    def create(cls, canvas: Any) -> CanvasRuntimeState:
        history_state = CanvasHistoryState()
        rdkit_idle_warmup_bridge = RdkitIdleWarmupBridge(canvas)
        rdkit_idle_timer = QTimer(rdkit_idle_warmup_bridge)
        rdkit_idle_timer.setInterval(250)
        rdkit_idle_timer.timeout.connect(rdkit_idle_warmup_bridge.warm_when_idle)
        rdkit_idle_warmup_bridge.timer = rdkit_idle_timer
        # Armed on demand instead of running continuously for every canvas.
        return cls(
            document_metadata_state=CanvasDocumentMetadataState(),
            sheet_setup_state=SheetSetupState(),
            selection_info_state=SelectionInfoState.create(),
            rdkit_idle_timer=rdkit_idle_timer,
            rdkit_idle_warmup_bridge=rdkit_idle_warmup_bridge,
            graph_state=CanvasGraphState(),
            group_state=CanvasGroupState(),
            insert_state=CanvasInsertState(),
            history_state=history_state,
            history_service=CanvasHistoryService(canvas, history_state),
            atom_coords_3d_state=CanvasAtomCoords3DState(),
            atom_graphics_state=CanvasAtomGraphicsState(),
            bond_graphics_state=CanvasBondGraphicsState(),
            mark_registry=CanvasMarkRegistry(),
            spatial_index_state=CanvasSpatialIndexState(),
            input_view_state=InputViewState(),
            rotation_state=CanvasRotationState(),
            handle_state=CanvasHandleState(),
            selection_style_state=SelectionStyleState(),
            selection_outline_state=SelectionOutlineState(),
            text_style_state=CanvasTextStyleState(),
            tool_settings_state=CanvasToolSettingsState(),
            hover_preview_state=HoverState(),
            callback_state=CanvasCallbackState(),
            scene_clipboard_state=SceneClipboardState(),
            scene_items_state=CanvasSceneItemsState(),
            smiles_input_state=CanvasSmilesInputState(),
            contexts={},
        )


def attach_canvas_runtime_state(canvas: Any) -> CanvasRuntimeState:
    state = CanvasRuntimeState.create(canvas)
    canvas.runtime_state = state
    return state


__all__ = ["CanvasRuntimeState", "attach_canvas_runtime_state"]
