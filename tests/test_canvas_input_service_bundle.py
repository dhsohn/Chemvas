from __future__ import annotations

from types import SimpleNamespace

import chemvas.ui.canvas_input_service_bundle as canvas_input_service_bundle
from chemvas.ui.canvas_input_service_bundle import (
    CanvasInputServiceBundle,
    build_canvas_input_services,
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_canvas_input_services_wires_explicit_collaborators(monkeypatch) -> None:
    for class_name in (
        "CanvasChemdrawShortcutService",
        "CanvasInputController",
        "CanvasPointerController",
        "CanvasToolModeController",
    ):
        monkeypatch.setattr(
            canvas_input_service_bundle, class_name, _stub_service_class(class_name)
        )

    canvas = SimpleNamespace()
    hit_testing_service = object()
    insert_controller = object()
    hover_controller = SimpleNamespace(refresh=object())
    tool_controller = SimpleNamespace(set_active=object())
    scene_delete_controller = object()
    scene_clipboard_controller = object()
    scene_transform_controller = object()
    mark_scene_service = object()

    history_service = object()

    services = build_canvas_input_services(
        canvas,
        hit_testing_service=hit_testing_service,
        insert_controller=insert_controller,
        hover_controller=hover_controller,
        tool_controller=tool_controller,
        scene_delete_controller=scene_delete_controller,
        scene_clipboard_controller=scene_clipboard_controller,
        scene_transform_controller=scene_transform_controller,
        mark_scene_service=mark_scene_service,
        history_service=history_service,
    )

    assert isinstance(services, CanvasInputServiceBundle)
    assert services.tool_mode_controller.kwargs == {
        "insert_controller": insert_controller,
        "hover_refresh": hover_controller.refresh,
        "set_active_tool": tool_controller.set_active,
    }
    assert services.pointer_controller.kwargs == {
        "hit_testing_service": hit_testing_service,
        "insert_controller": insert_controller,
        "hover_controller": hover_controller,
        "tool_controller": tool_controller,
        "scene_transform_controller": scene_transform_controller,
    }
    assert services.chemdraw_shortcut_service.kwargs == {
        "scene_transform_controller": scene_transform_controller,
        "tool_mode_controller": services.tool_mode_controller,
        "mark_scene_service": mark_scene_service,
    }
    assert services.input_controller.kwargs == {
        "scene_delete_controller": scene_delete_controller,
        "scene_clipboard_controller": scene_clipboard_controller,
        "history_service": history_service,
        "hover_controller": hover_controller,
        "chemdraw_shortcut_service": services.chemdraw_shortcut_service,
        "tool_mode_controller": services.tool_mode_controller,
    }
