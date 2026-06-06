from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ui.active_tool_reference import ActiveToolReference
from ui.canvas_service_types import CanvasServices


@dataclass(frozen=True, slots=True)
class CanvasServiceBuilders:
    build_canvas_auxiliary_services: Any
    build_canvas_document_services: Any
    build_canvas_graph_services: Any
    build_canvas_input_services: Any
    build_canvas_interaction_services: Any
    build_canvas_scene_view_services: Any
    build_handle_services: Any
    build_hover_services: Any
    build_scene_decoration_services: Any
    build_scene_operation_services: Any
    build_selection_services: Any
    build_structure_services: Any
    build_tool_services: Any


def compose_canvas_services(
    canvas: Any,
    *,
    graph_state,
    insert_state,
    history_service,
    builders: CanvasServiceBuilders,
) -> CanvasServices:
    graph_services = builders.build_canvas_graph_services(canvas, graph_state=graph_state)
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

    return CanvasServices(
        selection_controller=selection_services.selection_controller,
        scene_item_controller=scene_view_services.scene_item_controller,
        scene_clipboard_controller=scene_operation_services.scene_clipboard_controller,
        scene_delete_controller=scene_operation_services.scene_delete_controller,
        scene_transform_controller=scene_operation_services.scene_transform_controller,
        insert_controller=structure_services.insert_controller,
        input_controller=input_services.input_controller,
        handle_controller=handle_services.handle_controller,
        handle_overlay_service=handle_services.handle_overlay_service,
        handle_mutation_service=handle_services.handle_mutation_service,
        curved_arrow_path_service=handle_services.curved_arrow_path_service,
        selection_highlight_styler=scene_view_services.selection_highlight_styler,
        move_controller=interaction_services.move_controller,
        note_controller=interaction_services.note_controller,
        pointer_controller=input_services.pointer_controller,
        geometry_controller=scene_view_services.geometry_controller,
        canvas_atom_mutation_service=structure_services.canvas_atom_mutation_service,
        canvas_bond_mutation_service=structure_services.canvas_bond_mutation_service,
        chemdraw_shortcut_service=input_services.chemdraw_shortcut_service,
        hit_testing_service=selection_services.hit_testing_service,
        canvas_color_mutation_service=scene_operation_services.canvas_color_mutation_service,
        canvas_document_session_service=document_services.canvas_document_session_service,
        canvas_graph_service=canvas_graph_service,
        history_service=history_service,
        canvas_history_recording_service=document_services.canvas_history_recording_service,
        canvas_mark_scene_service=scene_decoration_services.canvas_mark_scene_service,
        canvas_ring_fill_scene_service=scene_view_services.canvas_ring_fill_scene_service,
        canvas_scene_reset_service=document_services.canvas_scene_reset_service,
        rotation_preview_controller=scene_view_services.rotation_preview_controller,
        atom_label_service=auxiliary_services.atom_label_service,
        hover_interaction_service=hover_services.hover_interaction_service,
        hover_scene_service=hover_services.hover_scene_service,
        mark_hover_preview_service=hover_services.mark_hover_preview_service,
        bond_hover_preview_service=hover_services.bond_hover_preview_service,
        structure_build_service=structure_services.structure_build_service,
        benzene_preview_service=auxiliary_services.benzene_preview_service,
        scene_decoration_build_service=scene_decoration_services.scene_decoration_build_service,
        scene_decoration_service=scene_decoration_services.scene_decoration_service,
        structure_insert_service=auxiliary_services.structure_insert_service,
        selection_rotation_controller=interaction_services.selection_rotation_controller,
        style_controller=scene_operation_services.style_controller,
        tool_mode_controller=input_services.tool_mode_controller,
        tools=tool_services.tools,
    )


__all__ = ["CanvasServiceBuilders", "compose_canvas_services"]
