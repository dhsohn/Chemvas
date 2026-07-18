from __future__ import annotations

from types import SimpleNamespace

import chemvas.ui.structure_service_bundle as structure_service_bundle
from chemvas.ui.structure_service_bundle import (
    StructureServiceBundle,
    build_structure_services,
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_structure_services_wires_explicit_collaborators(monkeypatch) -> None:
    for class_name in (
        "CanvasAtomMutationService",
        "CanvasBondMutationService",
        "InsertController",
        "StructureBuildService",
    ):
        monkeypatch.setattr(
            structure_service_bundle, class_name, _stub_service_class(class_name)
        )

    canvas = SimpleNamespace()
    hit_testing_service = object()
    graph_service = object()
    move_controller = object()
    insert_state = object()
    history_service = object()

    services = build_structure_services(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        move_controller=move_controller,
        insert_state=insert_state,
        history_service=history_service,
    )

    assert isinstance(services, StructureServiceBundle)
    assert services.canvas_atom_mutation_service.kwargs == {
        "hit_testing_service": hit_testing_service,
        "graph_service": graph_service,
    }
    assert services.canvas_bond_mutation_service.kwargs == {
        "hit_testing_service": hit_testing_service,
        "graph_service": graph_service,
    }
    assert services.structure_build_service.kwargs == {
        "hit_testing_service": hit_testing_service,
        "move_controller": move_controller,
        "graph_service": graph_service,
    }
    assert services.insert_controller.kwargs == {
        "insert_state": insert_state,
        "hit_testing_service": hit_testing_service,
        "graph_service": graph_service,
        "structure_build_service": services.structure_build_service,
        "history_service": history_service,
    }
