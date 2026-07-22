from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.ui.canvas_geometry_controller import CanvasGeometryController
from chemvas.ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService
from chemvas.ui.scene_item_controller import SceneItemController
from chemvas.ui.scene_item_lifecycle_service import SceneItemLifecycleService
from chemvas.ui.selection_highlight_styler import SelectionHighlightStyler

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


@dataclass(slots=True)
class CanvasSceneViewServiceBundle:
    scene_item_controller: SceneItemController
    selection_highlight_styler: SelectionHighlightStyler
    geometry_controller: CanvasGeometryController
    canvas_ring_fill_scene_service: CanvasRingFillSceneService


def build_canvas_scene_view_services(
    canvas: CanvasView | Any,
    *,
    graph_service: Any,
    hit_testing_service: Any,
    history_service: Any,
) -> CanvasSceneViewServiceBundle:
    scene_item_lifecycle_service = SceneItemLifecycleService(
        canvas, graph_service=graph_service
    )
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
    return CanvasSceneViewServiceBundle(
        scene_item_controller=scene_item_controller,
        selection_highlight_styler=selection_highlight_styler,
        geometry_controller=geometry_controller,
        canvas_ring_fill_scene_service=canvas_ring_fill_scene_service,
    )


__all__ = ["CanvasSceneViewServiceBundle", "build_canvas_scene_view_services"]
