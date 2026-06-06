from __future__ import annotations

from types import SimpleNamespace

from ui.scene_decoration_ports import (
    mark_scene_service_for_access,
    scene_decoration_build_service_for_access,
    scene_decoration_service_for_access,
)


def test_scene_decoration_ports_return_explicit_services() -> None:
    decoration_service = object()
    build_service = object()
    mark_service = object()
    canvas = SimpleNamespace(
        services=SimpleNamespace(
            scene_decoration_service=decoration_service,
            scene_decoration_build_service=build_service,
            canvas_mark_scene_service=mark_service,
        )
    )

    assert scene_decoration_service_for_access(canvas) is decoration_service
    assert scene_decoration_build_service_for_access(canvas) is build_service
    assert mark_scene_service_for_access(canvas) is mark_service
