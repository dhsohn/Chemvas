from __future__ import annotations

from types import SimpleNamespace

import ui.canvas_interaction_service_bundle as canvas_interaction_service_bundle
from ui.canvas_interaction_service_bundle import (
    CanvasInteractionServiceBundle,
    build_canvas_interaction_services,
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_canvas_interaction_services_wires_explicit_collaborators(monkeypatch) -> None:
    for class_name in (
        "CanvasMoveController",
        "CanvasNoteController",
        "SelectionRotationController",
    ):
        monkeypatch.setattr(canvas_interaction_service_bundle, class_name, _stub_service_class(class_name))

    canvas = SimpleNamespace()
    selection_controller = object()
    hit_testing_service = object()
    graph_service = object()
    history_service = object()

    services = build_canvas_interaction_services(
        canvas,
        selection_controller=selection_controller,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        history_service=history_service,
    )

    assert isinstance(services, CanvasInteractionServiceBundle)
    assert services.note_controller.kwargs == {
        "selection_controller": selection_controller,
        "history_service": history_service,
    }
    assert services.move_controller.kwargs == {"hit_testing_service": hit_testing_service}
    assert services.selection_rotation_controller.kwargs == {
        "move_controller": services.move_controller,
        "graph_service": graph_service,
        "history_service": history_service,
    }
