from __future__ import annotations

from typing import Any

from ui.canvas_auxiliary_service_bundle import build_canvas_auxiliary_services
from ui.canvas_document_service_bundle import build_canvas_document_services
from ui.canvas_graph_service_bundle import build_canvas_graph_services
from ui.canvas_input_service_bundle import build_canvas_input_services
from ui.canvas_interaction_service_bundle import build_canvas_interaction_services
from ui.canvas_scene_view_service_bundle import build_canvas_scene_view_services
from ui.canvas_service_composer import CanvasServiceBuilders, compose_canvas_services
from ui.canvas_service_types import CanvasServices
from ui.handle_service_bundle import build_handle_services
from ui.hover_service_bundle import build_hover_services
from ui.scene_decoration_service_bundle import build_scene_decoration_services
from ui.scene_operation_service_bundle import build_scene_operation_services
from ui.selection_service_bundle import build_selection_services
from ui.structure_service_bundle import build_structure_services
from ui.tool_service_bundle import build_tool_services


def build_canvas_services(
    canvas: Any,
    *,
    graph_state,
    insert_state,
    history_service,
) -> CanvasServices:
    builders = CanvasServiceBuilders(
        build_canvas_auxiliary_services=build_canvas_auxiliary_services,
        build_canvas_document_services=build_canvas_document_services,
        build_canvas_graph_services=build_canvas_graph_services,
        build_canvas_input_services=build_canvas_input_services,
        build_canvas_interaction_services=build_canvas_interaction_services,
        build_canvas_scene_view_services=build_canvas_scene_view_services,
        build_handle_services=build_handle_services,
        build_hover_services=build_hover_services,
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


def attach_canvas_services(canvas: Any, services: CanvasServices) -> None:
    canvas.services = services


__all__ = ["CanvasServices", "attach_canvas_services", "build_canvas_services"]
