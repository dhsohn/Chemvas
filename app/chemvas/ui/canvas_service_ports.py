from __future__ import annotations

from typing import Any

from chemvas.ui.canvas_service_access import canvas_services_for


def atom_label_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).auxiliary.atom_label_service


def benzene_preview_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).auxiliary.benzene_preview_service


def canvas_window_document_session_service(canvas) -> Any:
    return canvas_services_for(canvas).document.canvas_document_session_service


def curved_arrow_path_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).handles.curved_arrow_path_service


def geometry_controller_for_access(canvas) -> Any:
    return canvas_services_for(canvas).scene_view.geometry_controller


def handle_mutation_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).handles.handle_mutation_service


def handle_overlay_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).handles.handle_overlay_service


def history_atom_mutation_service_for(canvas) -> Any:
    return canvas_services_for(canvas).structure.canvas_atom_mutation_service


def history_bond_mutation_service_for(canvas) -> Any:
    return canvas_services_for(canvas).structure.canvas_bond_mutation_service


def history_hit_testing_service_for(canvas) -> Any:
    return canvas_services_for(canvas).selection.hit_testing_service


def history_recording_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).document.canvas_history_recording_service


def insert_controller_for_access(canvas) -> Any:
    return canvas_services_for(canvas).structure.insert_controller


def mark_scene_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).scene_decoration.canvas_mark_scene_service


def move_controller_for_access(canvas) -> Any:
    return canvas_services_for(canvas).interaction.move_controller


def note_controller_for_access(canvas) -> Any:
    return canvas_services_for(canvas).interaction.note_controller


def ring_fill_scene_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).scene_view.canvas_ring_fill_scene_service


def scene_decoration_build_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).scene_decoration.scene_decoration_build_service


def scene_decoration_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).scene_decoration.scene_decoration_service


def scene_item_controller_for_access(canvas) -> Any:
    return canvas_services_for(canvas).scene_view.scene_item_controller


def scene_reset_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).document.canvas_scene_reset_service


def selection_highlight_styler_for_access(canvas) -> Any:
    return canvas_services_for(canvas).scene_view.selection_highlight_styler


def selection_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).selection.selection_controller


def structure_build_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).structure.structure_build_service


def structure_insert_build_service_for_access(canvas) -> Any:
    return canvas_services_for(canvas).structure.structure_build_service


def structure_mutation_atom_service(canvas) -> Any:
    return canvas_services_for(canvas).structure.canvas_atom_mutation_service


def structure_mutation_bond_service(canvas) -> Any:
    return canvas_services_for(canvas).structure.canvas_bond_mutation_service


def structure_mutation_build_service(canvas) -> Any:
    return canvas_services_for(canvas).structure.structure_build_service


__all__ = [
    "atom_label_service_for_access",
    "benzene_preview_service_for_access",
    "canvas_window_document_session_service",
    "curved_arrow_path_service_for_access",
    "geometry_controller_for_access",
    "handle_mutation_service_for_access",
    "handle_overlay_service_for_access",
    "history_atom_mutation_service_for",
    "history_bond_mutation_service_for",
    "history_hit_testing_service_for",
    "history_recording_service_for_access",
    "insert_controller_for_access",
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
