from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def atom_label_service_for_access(canvas):
    return canvas_services_for(canvas).atom_label_service


def benzene_preview_service_for_access(canvas):
    return canvas_services_for(canvas).benzene_preview_service


def bond_hover_preview_service_for_access(canvas):
    return canvas_services_for(canvas).bond_hover_preview_service


def canvas_window_document_session_service(canvas):
    return canvas_services_for(canvas).canvas_document_session_service


def curved_arrow_path_service_for_access(canvas):
    return canvas_services_for(canvas).curved_arrow_path_service


def geometry_controller_for_access(canvas):
    return canvas_services_for(canvas).geometry_controller


def handle_mutation_service_for_access(canvas):
    return canvas_services_for(canvas).handle_mutation_service


def handle_overlay_service_for_access(canvas):
    return canvas_services_for(canvas).handle_overlay_service


def history_atom_mutation_service_for(canvas):
    return canvas_services_for(canvas).canvas_atom_mutation_service


def history_bond_mutation_service_for(canvas):
    return canvas_services_for(canvas).canvas_bond_mutation_service


def history_hit_testing_service_for(canvas):
    return canvas_services_for(canvas).hit_testing_service


def history_recording_service_for_access(canvas):
    return canvas_services_for(canvas).canvas_history_recording_service


def hover_interaction_service_for_access(canvas):
    return canvas_services_for(canvas).hover_interaction_service


def hover_scene_service_for_access(canvas):
    return canvas_services_for(canvas).hover_scene_service


def insert_controller_for_access(canvas):
    return canvas_services_for(canvas).insert_controller


def mark_hover_preview_service_for_access(canvas):
    return canvas_services_for(canvas).mark_hover_preview_service


def mark_scene_service_for_access(canvas):
    return canvas_services_for(canvas).canvas_mark_scene_service


def move_controller_for_access(canvas):
    return canvas_services_for(canvas).move_controller


def note_controller_for_access(canvas):
    return canvas_services_for(canvas).note_controller


def ring_fill_scene_service_for_access(canvas):
    return canvas_services_for(canvas).canvas_ring_fill_scene_service


def scene_decoration_build_service_for_access(canvas):
    return canvas_services_for(canvas).scene_decoration_build_service


def scene_decoration_service_for_access(canvas):
    return canvas_services_for(canvas).scene_decoration_service


def scene_item_controller_for_access(canvas):
    return canvas_services_for(canvas).scene_item_controller


def scene_reset_service_for_access(canvas):
    return canvas_services_for(canvas).canvas_scene_reset_service


def selection_highlight_styler_for_access(canvas):
    return canvas_services_for(canvas).selection_highlight_styler


def selection_service_for_access(canvas):
    return canvas_services_for(canvas).selection_controller


def structure_build_service_for_access(canvas):
    return canvas_services_for(canvas).structure_build_service


def structure_insert_build_service_for_access(canvas):
    return canvas_services_for(canvas).structure_build_service


def structure_mutation_atom_service(canvas):
    return canvas_services_for(canvas).canvas_atom_mutation_service


def structure_mutation_bond_service(canvas):
    return canvas_services_for(canvas).canvas_bond_mutation_service


def structure_mutation_build_service(canvas):
    return canvas_services_for(canvas).structure_build_service


__all__ = [
    "atom_label_service_for_access",
    "benzene_preview_service_for_access",
    "bond_hover_preview_service_for_access",
    "canvas_window_document_session_service",
    "curved_arrow_path_service_for_access",
    "geometry_controller_for_access",
    "handle_mutation_service_for_access",
    "handle_overlay_service_for_access",
    "history_atom_mutation_service_for",
    "history_bond_mutation_service_for",
    "history_hit_testing_service_for",
    "history_recording_service_for_access",
    "hover_interaction_service_for_access",
    "hover_scene_service_for_access",
    "insert_controller_for_access",
    "mark_hover_preview_service_for_access",
    "mark_scene_service_for_access",
    "move_controller_for_access",
    "note_controller_for_access",
    "ring_fill_scene_service_for_access",
    "scene_decoration_build_service_for_access",
    "scene_decoration_service_for_access",
    "scene_item_controller_for_access",
    "scene_reset_service_for_access",
    "selection_highlight_styler_for_access",
    "selection_service_for_access",
    "structure_build_service_for_access",
    "structure_insert_build_service_for_access",
    "structure_mutation_atom_service",
    "structure_mutation_bond_service",
    "structure_mutation_build_service",
]
