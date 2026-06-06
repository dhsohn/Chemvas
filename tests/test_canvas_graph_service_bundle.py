from __future__ import annotations

from types import SimpleNamespace

import ui.canvas_graph_service_bundle as canvas_graph_service_bundle
from ui.canvas_graph_service_bundle import (
    CanvasGraphServiceBundle,
    build_canvas_graph_services,
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_canvas_graph_services_wires_graph_state(monkeypatch) -> None:
    monkeypatch.setattr(
        canvas_graph_service_bundle,
        "CanvasGraphService",
        _stub_service_class("CanvasGraphService"),
    )
    canvas = SimpleNamespace()
    graph_state = object()

    services = build_canvas_graph_services(canvas, graph_state=graph_state)

    assert isinstance(services, CanvasGraphServiceBundle)
    assert services.canvas_graph_service.service_name == "CanvasGraphService"
    assert services.canvas_graph_service.args == (canvas, graph_state)
    assert services.canvas_graph_service.kwargs == {}
