from __future__ import annotations

from types import SimpleNamespace

import pytest

from chemvas.ui import canvas_service_ports as ports
from tests.runtime_services import canvas_runtime_services


def _canvas_with_service(service_name: str, service):
    return SimpleNamespace(services=canvas_runtime_services(**{service_name: service}))


@pytest.mark.parametrize(
    ("selector", "service_name"),
    [
        (ports.arrow_build_service_for_access, "arrow_build_service"),
        (ports.atom_label_service_for_access, "atom_label_service"),
        (
            ports.canvas_window_document_session_service,
            "canvas_document_session_service",
        ),
        (ports.geometry_controller_for_access, "geometry_controller"),
        (ports.handle_mutation_service_for_access, "handle_mutation_service"),
        (ports.handle_overlay_service_for_access, "handle_overlay_service"),
        (ports.structure_mutation_atom_service, "canvas_atom_mutation_service"),
        (ports.structure_mutation_bond_service, "canvas_bond_mutation_service"),
        (ports.insert_controller_for_access, "insert_controller"),
        (ports.mark_scene_service_for_access, "canvas_mark_scene_service"),
        (ports.note_controller_for_access, "note_controller"),
        (ports.ring_fill_scene_service_for_access, "canvas_ring_fill_scene_service"),
        (
            ports.scene_decoration_build_service_for_access,
            "scene_decoration_build_service",
        ),
        (ports.scene_decoration_service_for_access, "scene_decoration_service"),
        (ports.scene_item_controller_for_access, "scene_item_controller"),
        (ports.scene_reset_service_for_access, "canvas_scene_reset_service"),
        (ports.style_controller_for_access, "style_controller"),
        (ports.color_mutation_service_for_access, "canvas_color_mutation_service"),
        (ports.scene_clipboard_controller_for_access, "scene_clipboard_controller"),
        (ports.scene_delete_controller_for_access, "scene_delete_controller"),
        (ports.tool_controller_for_access, "tool_controller"),
        (ports.structure_build_service_for_access, "structure_build_service"),
    ],
)
def test_canvas_service_port_returns_attached_service(
    selector, service_name: str
) -> None:
    service = object()
    canvas = _canvas_with_service(service_name, service)

    assert selector(canvas) is service
