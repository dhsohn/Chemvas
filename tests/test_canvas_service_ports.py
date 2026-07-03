from __future__ import annotations

from types import SimpleNamespace

import pytest
from ui import canvas_service_ports as ports


def _canvas_with_service(service_name: str, service):
    return SimpleNamespace(services=SimpleNamespace(**{service_name: service}))


@pytest.mark.parametrize(
    ("selector", "service_name"),
    [
        (ports.atom_label_service_for_access, "atom_label_service"),
        (ports.benzene_preview_service_for_access, "benzene_preview_service"),
        (ports.bond_hover_preview_service_for_access, "bond_hover_preview_service"),
        (ports.canvas_window_document_session_service, "canvas_document_session_service"),
        (ports.curved_arrow_path_service_for_access, "curved_arrow_path_service"),
        (ports.geometry_controller_for_access, "geometry_controller"),
        (ports.handle_mutation_service_for_access, "handle_mutation_service"),
        (ports.handle_overlay_service_for_access, "handle_overlay_service"),
        (ports.history_atom_mutation_service_for, "canvas_atom_mutation_service"),
        (ports.history_bond_mutation_service_for, "canvas_bond_mutation_service"),
        (ports.history_hit_testing_service_for, "hit_testing_service"),
        (ports.history_recording_service_for_access, "canvas_history_recording_service"),
        (ports.hover_interaction_service_for_access, "hover_interaction_service"),
        (ports.hover_scene_service_for_access, "hover_scene_service"),
        (ports.insert_controller_for_access, "insert_controller"),
        (ports.mark_hover_preview_service_for_access, "mark_hover_preview_service"),
        (ports.mark_scene_service_for_access, "canvas_mark_scene_service"),
        (ports.move_controller_for_access, "move_controller"),
        (ports.note_controller_for_access, "note_controller"),
        (ports.ring_fill_scene_service_for_access, "canvas_ring_fill_scene_service"),
        (ports.scene_decoration_build_service_for_access, "scene_decoration_build_service"),
        (ports.scene_decoration_service_for_access, "scene_decoration_service"),
        (ports.scene_item_controller_for_access, "scene_item_controller"),
        (ports.scene_reset_service_for_access, "canvas_scene_reset_service"),
        (ports.selection_highlight_styler_for_access, "selection_highlight_styler"),
        (ports.selection_service_for_access, "selection_controller"),
        (ports.structure_build_service_for_access, "structure_build_service"),
        (ports.structure_insert_build_service_for_access, "structure_build_service"),
        (ports.structure_mutation_atom_service, "canvas_atom_mutation_service"),
        (ports.structure_mutation_bond_service, "canvas_bond_mutation_service"),
        (ports.structure_mutation_build_service, "structure_build_service"),
    ],
)
def test_canvas_service_port_returns_attached_service(selector, service_name: str) -> None:
    service = object()
    canvas = _canvas_with_service(service_name, service)

    assert selector(canvas) is service
