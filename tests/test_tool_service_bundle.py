from __future__ import annotations

from types import SimpleNamespace

import ui.tool_service_bundle as tool_service_bundle
from ui.tool_service_bundle import build_tool_services


class _StubToolController:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


def test_build_tool_services_injects_tool_context_ports(monkeypatch) -> None:
    monkeypatch.setattr(tool_service_bundle, "ToolController", _StubToolController)
    canvas = SimpleNamespace()
    hit_testing_service = object()
    selection_controller = object()
    note_controller = object()
    handle_controller = object()
    selection_rotation_controller = object()
    scene_delete_controller = object()
    scene_transform_controller = object()
    style_controller = object()
    color_mutation_service = object()
    graph_service = SimpleNamespace(bond_sets_for_atoms=object())
    history_service = object()
    canvas.tool_settings_state = SimpleNamespace(atom_symbol="Br")
    canvas.setDragMode = object()
    canvas.DragMode = SimpleNamespace(RubberBandDrag="rubber")

    services = build_tool_services(
        canvas,
        hit_testing_service=hit_testing_service,
        selection_controller=selection_controller,
        note_controller=note_controller,
        handle_controller=handle_controller,
        selection_rotation_controller=selection_rotation_controller,
        scene_delete_controller=scene_delete_controller,
        scene_transform_controller=scene_transform_controller,
        style_controller=style_controller,
        color_mutation_service=color_mutation_service,
        graph_service=graph_service,
        history_service=history_service,
    )

    assert isinstance(services.tools, _StubToolController)
    assert services.tools.args == (canvas,)
    assert services.tools.kwargs["hit_testing_service"] is hit_testing_service
    assert services.tools.kwargs["selection_controller"] is selection_controller
    assert services.tools.kwargs["note_controller"] is note_controller
    assert services.tools.kwargs["handle_controller"] is handle_controller
    assert services.tools.kwargs["selection_rotation_controller"] is selection_rotation_controller
    assert services.tools.kwargs["scene_delete_controller"] is scene_delete_controller
    assert services.tools.kwargs["scene_transform_controller"] is scene_transform_controller
    assert services.tools.kwargs["style_controller"] is style_controller
    assert services.tools.kwargs["bond_sets_for_atoms"] is graph_service.bond_sets_for_atoms
    assert services.tools.kwargs["color_mutation_service"] is color_mutation_service
    assert callable(services.tools.kwargs["selected_scene_items"])
    assert callable(services.tools.kwargs["select_single_structure_item"])
    assert services.tools.kwargs["atom_symbol_provider"]() == "Br"
    assert services.tools.kwargs["history_service"] is history_service
    assert services.tools.kwargs["set_drag_mode"] is canvas.setDragMode
    assert services.tools.kwargs["rubber_band_drag_mode"] is canvas.DragMode.RubberBandDrag
