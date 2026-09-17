"""Typed, feature-grouped runtime services for a canvas.

Group fields hold the concrete ``*ServiceBundle`` dataclasses built in
``chemvas.ui.canvas_services``; single runtimes are stored directly. The types
are named under ``TYPE_CHECKING`` only: this module imports none of them at run
time, so it stays a leaf of the eager import graph while mypy still sees what
the container holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.ui.atom_label_service import AtomLabelService
    from chemvas.ui.canvas_document_service_bundle import CanvasDocumentServiceBundle
    from chemvas.ui.canvas_graph_service import CanvasGraphService
    from chemvas.ui.canvas_history_service import CanvasHistoryService
    from chemvas.ui.canvas_input_service_bundle import CanvasInputServiceBundle
    from chemvas.ui.canvas_interaction_service_bundle import (
        CanvasInteractionServiceBundle,
    )
    from chemvas.ui.canvas_scene_view_service_bundle import (
        CanvasSceneViewServiceBundle,
    )
    from chemvas.ui.handle_service_bundle import HandleServiceBundle
    from chemvas.ui.hover import HoverController
    from chemvas.ui.scene_decoration_service_bundle import (
        SceneDecorationServiceBundle,
    )
    from chemvas.ui.scene_operation_service_bundle import SceneOperationServiceBundle
    from chemvas.ui.selection_service_bundle import SelectionServiceBundle
    from chemvas.ui.structure_service_bundle import StructureServiceBundle
    from chemvas.ui.tool_controller import ToolController


@dataclass(slots=True, kw_only=True)
class CanvasRuntimeServices:
    document: CanvasDocumentServiceBundle
    graph_service: CanvasGraphService
    input: CanvasInputServiceBundle
    interaction: CanvasInteractionServiceBundle
    scene_view: CanvasSceneViewServiceBundle
    handles: HandleServiceBundle
    hover: HoverController
    scene_decoration: SceneDecorationServiceBundle
    scene_operations: SceneOperationServiceBundle
    selection: SelectionServiceBundle
    structure: StructureServiceBundle
    tool_controller: ToolController
    atom_label_service: AtomLabelService
    history_service: CanvasHistoryService


__all__ = ["CanvasRuntimeServices"]
