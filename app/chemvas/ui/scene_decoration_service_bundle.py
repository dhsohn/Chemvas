from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.ui.canvas_mark_scene_service import CanvasMarkSceneService
from chemvas.ui.canvas_scene_decoration_build_service import (
    CanvasSceneDecorationBuildService,
)
from chemvas.ui.scene_decoration_service import SceneDecorationService

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


@dataclass(slots=True)
class SceneDecorationServiceBundle:
    canvas_mark_scene_service: CanvasMarkSceneService
    scene_decoration_build_service: CanvasSceneDecorationBuildService
    scene_decoration_service: SceneDecorationService


def build_scene_decoration_services(
    canvas: CanvasView | Any,
    *,
    history_service: Any,
) -> SceneDecorationServiceBundle:
    scene_decoration_build_service = CanvasSceneDecorationBuildService(canvas)
    scene_decoration_service = SceneDecorationService(
        canvas, history_service=history_service
    )
    canvas_mark_scene_service = CanvasMarkSceneService(
        canvas,
        scene_decoration_service=scene_decoration_service,
    )
    return SceneDecorationServiceBundle(
        canvas_mark_scene_service=canvas_mark_scene_service,
        scene_decoration_build_service=scene_decoration_build_service,
        scene_decoration_service=scene_decoration_service,
    )


__all__ = ["SceneDecorationServiceBundle", "build_scene_decoration_services"]
