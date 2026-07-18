from __future__ import annotations

from types import SimpleNamespace

import chemvas.ui.scene_decoration_service_bundle as scene_decoration_service_bundle
from chemvas.ui.scene_decoration_service_bundle import (
    SceneDecorationServiceBundle,
    build_scene_decoration_services,
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_scene_decoration_services_wires_explicit_collaborators(
    monkeypatch,
) -> None:
    for class_name in (
        "CanvasMarkSceneService",
        "CanvasSceneDecorationBuildService",
        "SceneDecorationService",
    ):
        monkeypatch.setattr(
            scene_decoration_service_bundle, class_name, _stub_service_class(class_name)
        )

    canvas = SimpleNamespace()
    history_service = object()

    services = build_scene_decoration_services(canvas, history_service=history_service)

    assert isinstance(services, SceneDecorationServiceBundle)
    assert (
        services.scene_decoration_build_service.service_name
        == "CanvasSceneDecorationBuildService"
    )
    assert services.scene_decoration_service.kwargs == {
        "history_service": history_service
    }
    assert services.canvas_mark_scene_service.kwargs == {
        "scene_decoration_service": services.scene_decoration_service
    }
