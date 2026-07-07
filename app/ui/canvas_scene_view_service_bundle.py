from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ui.canvas_geometry_controller import CanvasGeometryController
from ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService
from ui.canvas_rotation_preview_controller import CanvasRotationPreviewController
from ui.scene_item_controller import SceneItemController
from ui.scene_item_lifecycle_service import SceneItemLifecycleService
from ui.selection_highlight_styler import SelectionHighlightStyler

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class CanvasSceneViewServiceBundle:
    scene_item_controller: SceneItemController
    selection_highlight_styler: SelectionHighlightStyler
    geometry_controller: CanvasGeometryController
    canvas_ring_fill_scene_service: CanvasRingFillSceneService
    rotation_preview_controller: CanvasRotationPreviewController


def build_canvas_scene_view_services(
    canvas: CanvasView | Any,
    *,
    graph_service: Any,
    hit_testing_service: Any,
    history_service: Any,
    scene_transform_controller: Any,
) -> CanvasSceneViewServiceBundle:
    scene_item_lifecycle_service = SceneItemLifecycleService(canvas, graph_service=graph_service)
    scene_item_controller = SceneItemController(
        canvas,
        graph_service=graph_service,
        lifecycle_service=scene_item_lifecycle_service,
    )
    selection_highlight_styler = SelectionHighlightStyler(canvas)
    geometry_controller = CanvasGeometryController(
        canvas,
        hit_testing_service=hit_testing_service,
        history_service=history_service,
    )
    canvas_ring_fill_scene_service = CanvasRingFillSceneService(canvas)
    rotation_preview_controller = CanvasRotationPreviewController(
        canvas,
        scene_transform_controller=scene_transform_controller,
    )
    return CanvasSceneViewServiceBundle(
        scene_item_controller=scene_item_controller,
        selection_highlight_styler=selection_highlight_styler,
        geometry_controller=geometry_controller,
        canvas_ring_fill_scene_service=canvas_ring_fill_scene_service,
        rotation_preview_controller=rotation_preview_controller,
    )


__all__ = ["CanvasSceneViewServiceBundle", "build_canvas_scene_view_services"]
