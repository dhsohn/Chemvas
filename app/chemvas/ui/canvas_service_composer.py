from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chemvas.features.selection import ActiveToolReference
from chemvas.ui.canvas_runtime_services import (
    AuxiliaryServices,
    CanvasRuntimeServices,
    DocumentServices,
    GraphServices,
    HandleServices,
    HoverServices,
    InputServices,
    InteractionServices,
    SceneDecorationServices,
    SceneOperationServices,
    SceneViewServices,
    SelectionServices,
    StructureServices,
    ToolingServices,
)


@dataclass(frozen=True, slots=True)
class CanvasServiceBuilders:
    build_canvas_auxiliary_services: Callable[..., AuxiliaryServices]
    build_canvas_document_services: Callable[..., DocumentServices]
    build_canvas_graph_services: Callable[..., GraphServices]
    build_canvas_input_services: Callable[..., InputServices]
    build_canvas_interaction_services: Callable[..., InteractionServices]
    build_canvas_scene_view_services: Callable[..., SceneViewServices]
    build_handle_services: Callable[..., HandleServices]
    build_hover_services: Callable[..., HoverServices]
    build_scene_decoration_services: Callable[..., SceneDecorationServices]
    build_scene_operation_services: Callable[..., SceneOperationServices]
    build_selection_services: Callable[..., SelectionServices]
    build_structure_services: Callable[..., StructureServices]
    build_tool_services: Callable[..., ToolingServices]


def compose_canvas_services(
    canvas: Any,
    *,
    graph_state,
    insert_state,
    history_service,
    builders: CanvasServiceBuilders,
) -> CanvasRuntimeServices:
    graph_services = builders.build_canvas_graph_services(
        canvas, graph_state=graph_state
    )
    canvas_graph_service = graph_services.canvas_graph_service
    active_tool_reference = ActiveToolReference()

    selection_services = builders.build_selection_services(
        canvas,
        graph_service=canvas_graph_service,
        active_tool_name_provider=active_tool_reference.active_tool_name,
    )
    handle_services = builders.build_handle_services(canvas)
    hover_services = builders.build_hover_services(
        canvas,
        selection_controller=selection_services.selection_controller,
        hit_testing_service=selection_services.hit_testing_service,
        active_tool_provider=active_tool_reference.active_tool,
        active_tool_name_provider=active_tool_reference.active_tool_name,
    )
    interaction_services = builders.build_canvas_interaction_services(
        canvas,
        selection_controller=selection_services.selection_controller,
        hit_testing_service=selection_services.hit_testing_service,
        graph_service=canvas_graph_service,
        history_service=history_service,
    )
    structure_services = builders.build_structure_services(
        canvas,
        hit_testing_service=selection_services.hit_testing_service,
        graph_service=canvas_graph_service,
        move_controller=interaction_services.move_controller,
        insert_state=insert_state,
        history_service=history_service,
    )
    scene_operation_services = builders.build_scene_operation_services(
        canvas,
        selection_controller=selection_services.selection_controller,
        move_controller=interaction_services.move_controller,
        atom_mutation_service=structure_services.canvas_atom_mutation_service,
        bond_mutation_service=structure_services.canvas_bond_mutation_service,
        note_controller=interaction_services.note_controller,
        graph_service=canvas_graph_service,
        history_service=history_service,
    )
    tool_services = builders.build_tool_services(
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
        graph_service=canvas_graph_service,
        history_service=history_service,
    )
    active_tool_reference.tool_controller = tool_services.tools
    scene_decoration_services = builders.build_scene_decoration_services(
        canvas,
        history_service=history_service,
    )
    input_services = builders.build_canvas_input_services(
        canvas,
        hit_testing_service=selection_services.hit_testing_service,
        insert_controller=structure_services.insert_controller,
        hover_interaction_service=hover_services.hover_interaction_service,
        tool_controller=tool_services.tools,
        scene_delete_controller=scene_operation_services.scene_delete_controller,
        scene_clipboard_controller=scene_operation_services.scene_clipboard_controller,
        scene_transform_controller=scene_operation_services.scene_transform_controller,
        mark_scene_service=scene_decoration_services.canvas_mark_scene_service,
        hover_refresh=hover_services.hover_refresh,
        history_service=history_service,
    )
    document_services = builders.build_canvas_document_services(
        canvas,
        hit_testing_service=selection_services.hit_testing_service,
        graph_service=canvas_graph_service,
        structure_build_service=structure_services.structure_build_service,
        history_service=history_service,
    )
    scene_view_services = builders.build_canvas_scene_view_services(
        canvas,
        graph_service=canvas_graph_service,
        hit_testing_service=selection_services.hit_testing_service,
        history_service=history_service,
        scene_transform_controller=scene_operation_services.scene_transform_controller,
    )
    auxiliary_services = builders.build_canvas_auxiliary_services(
        canvas,
        move_controller=interaction_services.move_controller,
        graph_service=canvas_graph_service,
        history_service=history_service,
        hover_refresh=hover_services.hover_refresh,
        structure_build_service=structure_services.structure_build_service,
        note_controller=interaction_services.note_controller,
    )

    return CanvasRuntimeServices(
        auxiliary=auxiliary_services,
        document=document_services,
        graph=graph_services,
        input=input_services,
        interaction=interaction_services,
        scene_view=scene_view_services,
        handles=handle_services,
        hover=hover_services,
        scene_decoration=scene_decoration_services,
        scene_operations=scene_operation_services,
        selection=selection_services,
        structure=structure_services,
        tooling=tool_services,
        history_service=history_service,
    )


__all__ = ["CanvasServiceBuilders", "compose_canvas_services"]
