from __future__ import annotations

from typing import Any

from chemvas.ui.atom_label_service import AtomLabelService
from chemvas.ui.canvas_document_service_bundle import build_canvas_document_services
from chemvas.ui.canvas_graph_service_bundle import build_canvas_graph_services
from chemvas.ui.canvas_input_service_bundle import build_canvas_input_services
from chemvas.ui.canvas_interaction_service_bundle import (
    build_canvas_interaction_services,
)
from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices
from chemvas.ui.canvas_scene_view_service_bundle import build_canvas_scene_view_services
from chemvas.ui.canvas_service_composer import (
    CanvasServiceBuilders,
    compose_canvas_services,
)
from chemvas.ui.handle_service_bundle import build_handle_services
from chemvas.ui.hover import build_hover_controller
from chemvas.ui.scene_decoration_service_bundle import build_scene_decoration_services
from chemvas.ui.scene_operation_service_bundle import build_scene_operation_services
from chemvas.ui.selection_service_bundle import build_selection_services
from chemvas.ui.structure_service_bundle import build_structure_services
from chemvas.ui.tool_service_bundle import build_tool_services


def build_canvas_services(
    canvas: Any,
    *,
    graph_state,
    insert_state,
    history_service,
) -> CanvasRuntimeServices:
    builders = CanvasServiceBuilders(
        build_atom_label_service=AtomLabelService,
        build_canvas_document_services=build_canvas_document_services,
        build_canvas_graph_services=build_canvas_graph_services,
        build_canvas_input_services=build_canvas_input_services,
        build_canvas_interaction_services=build_canvas_interaction_services,
        build_canvas_scene_view_services=build_canvas_scene_view_services,
        build_handle_services=build_handle_services,
        build_hover_controller=build_hover_controller,
        build_scene_decoration_services=build_scene_decoration_services,
        build_scene_operation_services=build_scene_operation_services,
        build_selection_services=build_selection_services,
        build_structure_services=build_structure_services,
        build_tool_services=build_tool_services,
    )
    return compose_canvas_services(
        canvas,
        graph_state=graph_state,
        insert_state=insert_state,
        history_service=history_service,
        builders=builders,
    )


def attach_canvas_services(canvas: Any, services: CanvasRuntimeServices) -> None:
    canvas.services = services


__all__ = [
    "CanvasRuntimeServices",
    "attach_canvas_services",
    "build_canvas_services",
]
