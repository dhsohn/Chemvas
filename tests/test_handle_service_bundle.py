from __future__ import annotations

from types import SimpleNamespace

import ui.handle_service_bundle as handle_service_bundle
from ui.handle_service_bundle import HandleServiceBundle, build_handle_services


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_handle_services_wires_explicit_collaborators(monkeypatch) -> None:
    for class_name in (
        "CanvasHandleController",
        "CurvedArrowPathService",
        "HandleMutationService",
        "HandleOverlayService",
    ):
        monkeypatch.setattr(handle_service_bundle, class_name, _stub_service_class(class_name))

    canvas = SimpleNamespace()

    services = build_handle_services(canvas)

    assert isinstance(services, HandleServiceBundle)
    assert services.handle_overlay_service.service_name == "HandleOverlayService"
    assert services.curved_arrow_path_service.service_name == "CurvedArrowPathService"
    assert services.handle_mutation_service.kwargs == {
        "curved_arrow_path_service": services.curved_arrow_path_service
    }
    assert services.handle_controller.kwargs == {
        "handle_overlay_service": services.handle_overlay_service,
        "handle_mutation_service": services.handle_mutation_service,
    }
