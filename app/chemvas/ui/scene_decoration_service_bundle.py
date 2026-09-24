from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.ui.canvas_mark_scene_service import CanvasMarkSceneService
from chemvas.ui.scene_decoration_service import SceneDecorationService
from chemvas.ui.scene_render_access import scene_render_context_for

if TYPE_CHECKING:
    from chemvas.ui.annotations.arrows import ArrowRenderer
    from chemvas.ui.annotations.graphics import (
        AnnotationGraphics,
    )
    from chemvas.ui.canvas_view import CanvasView


@dataclass(slots=True)
class SceneDecorationServiceBundle:
    arrow_build_service: ArrowRenderer
    canvas_mark_scene_service: CanvasMarkSceneService
    scene_decoration_build_service: AnnotationGraphics
    scene_decoration_service: SceneDecorationService


def build_scene_decoration_services(
    canvas: CanvasView | Any,
    *,
    history_service: Any,
) -> SceneDecorationServiceBundle:
    context = scene_render_context_for(canvas)
    arrow_build_service = context.arrows
    scene_decoration_build_service = context.decorations
    scene_decoration_service = SceneDecorationService(
        canvas, history_service=history_service
    )
    canvas_mark_scene_service = CanvasMarkSceneService(
        canvas,
        scene_decoration_service=scene_decoration_service,
        history_service=history_service,
    )
    return SceneDecorationServiceBundle(
        arrow_build_service=arrow_build_service,
        canvas_mark_scene_service=canvas_mark_scene_service,
        scene_decoration_build_service=scene_decoration_build_service,
        scene_decoration_service=scene_decoration_service,
    )


__all__ = ["SceneDecorationServiceBundle", "build_scene_decoration_services"]
