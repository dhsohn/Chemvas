from __future__ import annotations

from types import SimpleNamespace

import chemvas.ui.scene_operation_service_bundle as scene_operation_service_bundle
from chemvas.ui.scene_operation_service_bundle import (
    SceneOperationServiceBundle,
    build_scene_operation_services,
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_scene_operation_services_wires_explicit_collaborators(
    monkeypatch,
) -> None:
    for class_name in (
        "CanvasColorMutationService",
        "CanvasStyleController",
        "SceneClipboardController",
        "SceneDeleteController",
        "SceneTransformController",
    ):
        monkeypatch.setattr(
            scene_operation_service_bundle, class_name, _stub_service_class(class_name)
        )

    canvas = SimpleNamespace()
    selection_controller = object()
    move_controller = object()
    atom_mutation_service = object()
    bond_mutation_service = object()
    note_controller = object()
    graph_service = object()
    history_service = object()

    services = build_scene_operation_services(
        canvas,
        selection_controller=selection_controller,
        move_controller=move_controller,
        atom_mutation_service=atom_mutation_service,
        bond_mutation_service=bond_mutation_service,
        note_controller=note_controller,
        graph_service=graph_service,
        history_service=history_service,
    )

    assert isinstance(services, SceneOperationServiceBundle)
    assert services.style_controller.kwargs == {"note_controller": note_controller}
    assert services.scene_clipboard_controller.kwargs == {
        "selection_controller": selection_controller,
        "bond_mutation_service": bond_mutation_service,
    }
    assert services.scene_delete_controller.kwargs == {
        "move_controller": move_controller,
        "atom_mutation_service": atom_mutation_service,
        "bond_mutation_service": bond_mutation_service,
        "style_controller": services.style_controller,
        "history_service": history_service,
    }
    assert services.scene_transform_controller.kwargs == {
        "move_controller": move_controller,
        "graph_service": graph_service,
        "history_service": history_service,
    }
    assert services.canvas_color_mutation_service.kwargs == {
        "graph_service": graph_service,
        "history_service": history_service,
    }
