from __future__ import annotations

from typing import Any

from chemvas.features.selection import ActiveToolReference
from chemvas.ui.atom_label_service import AtomLabelService
from chemvas.ui.canvas_document_service_bundle import build_canvas_document_services
from chemvas.ui.canvas_graph_service import CanvasGraphService
from chemvas.ui.canvas_input_service_bundle import build_canvas_input_services
from chemvas.ui.canvas_interaction_service_bundle import (
    build_canvas_interaction_services,
)
from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices
from chemvas.ui.canvas_scene_view_service_bundle import build_canvas_scene_view_services
from chemvas.ui.handle_service_bundle import build_handle_services
from chemvas.ui.hover import build_hover_controller
from chemvas.ui.scene_decoration_service_bundle import build_scene_decoration_services
from chemvas.ui.scene_operation_service_bundle import build_scene_operation_services
from chemvas.ui.selection_service_bundle import build_selection_services
from chemvas.ui.structure_service_bundle import build_structure_services
from chemvas.ui.tool_controller_factory import build_tool_controller


def build_canvas_services(
    canvas: Any,
    *,
    graph_state,
    insert_state,
    history_service,
) -> CanvasRuntimeServices:
    graph_service = CanvasGraphService(canvas, graph_state=graph_state)
    active_tool_reference = ActiveToolReference()

    selection_services = build_selection_services(
        canvas,
        graph_service=graph_service,
        active_tool_name_provider=active_tool_reference.active_tool_name,
    )
    handle_services = build_handle_services(canvas)
    interaction_services = build_canvas_interaction_services(
        canvas,
        selection_controller=selection_services.selection_controller,
        hit_testing_service=selection_services.hit_testing_service,
        graph_service=graph_service,
        history_service=history_service,
    )
    structure_services = build_structure_services(
        canvas,
        hit_testing_service=selection_services.hit_testing_service,
        graph_service=graph_service,
        move_controller=interaction_services.move_controller,
        insert_state=insert_state,
        history_service=history_service,
    )
    scene_operation_services = build_scene_operation_services(
        canvas,
        selection_controller=selection_services.selection_controller,
        move_controller=interaction_services.move_controller,
        atom_mutation_service=structure_services.canvas_atom_mutation_service,
        bond_mutation_service=structure_services.canvas_bond_mutation_service,
        note_controller=interaction_services.note_controller,
        graph_service=graph_service,
        history_service=history_service,
    )
    tool_controller = build_tool_controller(
        canvas,
        hit_testing_service=selection_services.hit_testing_service,
        selection_controller=selection_services.selection_controller,
        note_controller=interaction_services.note_controller,
        handle_controller=handle_services.handle_controller,
        selection_rotation_controller=interaction_services.selection_rotation_controller,
        scene_delete_controller=scene_operation_services.scene_delete_controller,
        scene_transform_controller=scene_operation_services.scene_transform_controller,
        style_controller=scene_operation_services.style_controller,
        color_mutation_service=scene_operation_services.canvas_color_mutation_service,
        graph_service=graph_service,
        history_service=history_service,
    )
    active_tool_reference.tool_controller = tool_controller
    scene_decoration_services = build_scene_decoration_services(
        canvas,
        history_service=history_service,
    )
    hover_controller = build_hover_controller(
        canvas,
        selection_controller=selection_services.selection_controller,
        hit_testing_service=selection_services.hit_testing_service,
        insert_controller=structure_services.insert_controller,
        scene_decoration_build_service=(
            scene_decoration_services.scene_decoration_build_service
        ),
        mark_scene_service=scene_decoration_services.canvas_mark_scene_service,
        active_tool_name_provider=active_tool_reference.active_tool_name,
    )
    input_services = build_canvas_input_services(
        canvas,
        hit_testing_service=selection_services.hit_testing_service,
        insert_controller=structure_services.insert_controller,
        hover_controller=hover_controller,
        tool_controller=tool_controller,
        scene_delete_controller=scene_operation_services.scene_delete_controller,
        scene_clipboard_controller=scene_operation_services.scene_clipboard_controller,
        scene_transform_controller=scene_operation_services.scene_transform_controller,
        mark_scene_service=scene_decoration_services.canvas_mark_scene_service,
        history_service=history_service,
    )
    document_services = build_canvas_document_services(
        canvas,
        hit_testing_service=selection_services.hit_testing_service,
        graph_service=graph_service,
        structure_build_service=structure_services.structure_build_service,
        history_service=history_service,
    )
    scene_view_services = build_canvas_scene_view_services(
        canvas,
        graph_service=graph_service,
        hit_testing_service=selection_services.hit_testing_service,
        history_service=history_service,
    )
    atom_label_service = AtomLabelService(
        canvas,
        move_controller=interaction_services.move_controller,
        graph_service=graph_service,
        history_service=history_service,
        hover_refresh=hover_controller.refresh,
    )

    return CanvasRuntimeServices(
        document=document_services,
        graph_service=graph_service,
        input=input_services,
        interaction=interaction_services,
        scene_view=scene_view_services,
        handles=handle_services,
        hover=hover_controller,
        scene_decoration=scene_decoration_services,
        scene_operations=scene_operation_services,
        selection=selection_services,
        structure=structure_services,
        tool_controller=tool_controller,
        atom_label_service=atom_label_service,
        history_service=history_service,
    )


def attach_canvas_services(canvas: Any, services: CanvasRuntimeServices) -> None:
    canvas.services = services


__all__ = [
    "CanvasRuntimeServices",
    "attach_canvas_services",
    "build_canvas_services",
]
