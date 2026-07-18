from __future__ import annotations

from types import SimpleNamespace

import chemvas.ui.canvas_scene_view_service_bundle as canvas_scene_view_service_bundle
from chemvas.ui.canvas_scene_view_service_bundle import (
    CanvasSceneViewServiceBundle,
    build_canvas_scene_view_services,
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_canvas_scene_view_services_wires_explicit_collaborators(
    monkeypatch,
) -> None:
    for class_name in (
        "CanvasGeometryController",
        "CanvasRingFillSceneService",
        "CanvasRotationPreviewController",
        "SceneItemController",
        "SceneItemLifecycleService",
        "SelectionHighlightStyler",
    ):
        monkeypatch.setattr(
            canvas_scene_view_service_bundle,
            class_name,
            _stub_service_class(class_name),
        )

    canvas = SimpleNamespace()
    graph_service = object()
    hit_testing_service = object()
    history_service = object()
    scene_transform_controller = object()

    services = build_canvas_scene_view_services(
        canvas,
        graph_service=graph_service,
        hit_testing_service=hit_testing_service,
        history_service=history_service,
        scene_transform_controller=scene_transform_controller,
    )

    assert isinstance(services, CanvasSceneViewServiceBundle)
    lifecycle_service = services.scene_item_controller.kwargs["lifecycle_service"]
    assert services.scene_item_controller.kwargs == {
        "graph_service": graph_service,
        "lifecycle_service": lifecycle_service,
    }
    assert lifecycle_service.service_name == "SceneItemLifecycleService"
    assert lifecycle_service.args == (canvas,)
    assert lifecycle_service.kwargs == {"graph_service": graph_service}
    assert services.selection_highlight_styler.args == (canvas,)
    assert services.geometry_controller.kwargs == {
        "hit_testing_service": hit_testing_service,
        "history_service": history_service,
    }
    assert services.canvas_ring_fill_scene_service.args == (canvas,)
    assert services.rotation_preview_controller.args == (canvas,)
    assert services.rotation_preview_controller.kwargs == {
        "scene_transform_controller": scene_transform_controller,
    }
