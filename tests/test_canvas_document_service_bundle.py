from __future__ import annotations

from types import SimpleNamespace

import ui.canvas_document_service_bundle as canvas_document_service_bundle
from ui.canvas_document_service_bundle import (
    CanvasDocumentServiceBundle,
    build_canvas_document_services,
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_canvas_document_services_wires_explicit_collaborators(monkeypatch) -> None:
    for class_name in (
        "CanvasDocumentSessionService",
        "CanvasHistoryRecordingService",
        "CanvasSceneResetService",
    ):
        monkeypatch.setattr(canvas_document_service_bundle, class_name, _stub_service_class(class_name))

    canvas = SimpleNamespace()
    hit_testing_service = object()
    graph_service = object()
    structure_build_service = object()
    history_service = object()

    services = build_canvas_document_services(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        structure_build_service=structure_build_service,
        history_service=history_service,
    )

    assert isinstance(services, CanvasDocumentServiceBundle)
    assert services.canvas_document_session_service.kwargs == {
        "hit_testing_service": hit_testing_service,
        "graph_service": graph_service,
        "structure_build_service": structure_build_service,
        "history_service": history_service,
    }
    assert services.canvas_history_recording_service.kwargs == {
        "history_service": history_service,
    }
    assert services.canvas_scene_reset_service.kwargs == {
        "hit_testing_service": hit_testing_service,
    }
