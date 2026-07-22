from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.features.selection import ActiveToolReference
from chemvas.ui.canvas_runtime_services import (
    CanvasRuntimeServices,
    DocumentServices,
    GraphServices,
    HandleServices,
    InputServices,
    InteractionServices,
    SceneDecorationServices,
    SceneOperationServices,
    SceneViewServices,
    SelectionServices,
    StructureServices,
    ToolingServices,
)

if TYPE_CHECKING:
    from chemvas.ui.hover import HoverController


@dataclass(frozen=True, slots=True)
class CanvasServiceBuilders:
    build_atom_label_service: Callable[..., Any]
    build_canvas_document_services: Callable[..., DocumentServices]
    build_canvas_graph_services: Callable[..., GraphServices]
    build_canvas_input_services: Callable[..., InputServices]
    build_canvas_interaction_services: Callable[..., InteractionServices]
    build_canvas_scene_view_services: Callable[..., SceneViewServices]
    build_handle_services: Callable[..., HandleServices]
    build_hover_controller: Callable[..., HoverController]
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
    hover_controller = builders.build_hover_controller(
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
    input_services = builders.build_canvas_input_services(
        canvas,
        hit_testing_service=selection_services.hit_testing_service,
        insert_controller=structure_services.insert_controller,
        hover_controller=hover_controller,
        tool_controller=tool_services.tools,
        scene_delete_controller=scene_operation_services.scene_delete_controller,
        scene_clipboard_controller=scene_operation_services.scene_clipboard_controller,
        scene_transform_controller=scene_operation_services.scene_transform_controller,
        mark_scene_service=scene_decoration_services.canvas_mark_scene_service,
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
    )
    atom_label_service = builders.build_atom_label_service(
        canvas,
        move_controller=interaction_services.move_controller,
        graph_service=canvas_graph_service,
        history_service=history_service,
        hover_refresh=hover_controller.refresh,
    )

    return CanvasRuntimeServices(
        document=document_services,
        graph=graph_services,
        input=input_services,
        interaction=interaction_services,
        scene_view=scene_view_services,
        handles=handle_services,
        hover=hover_controller,
        scene_decoration=scene_decoration_services,
        scene_operations=scene_operation_services,
        selection=selection_services,
        structure=structure_services,
        tooling=tool_services,
        atom_label_service=atom_label_service,
        history_service=history_service,
    )


__all__ = ["CanvasServiceBuilders", "compose_canvas_services"]
