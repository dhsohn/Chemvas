from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.ui.canvas_hit_testing_service import CanvasHitTestingService
from chemvas.ui.canvas_view_ports import scene_pos_from_event_for_view
from chemvas.ui.selection_controller import SelectionController
from chemvas.ui.selection_hit_test_service import SelectionHitTestService
from chemvas.ui.selection_note_service import SelectionNoteService
from chemvas.ui.selection_outline_service import SelectionOutlineService
from chemvas.ui.selection_preference_service import SelectionPreferenceService
from chemvas.ui.selection_structure_service import SelectionStructureService

if TYPE_CHECKING:
    from chemvas.ui.canvas_graph_service import CanvasGraphService
    from chemvas.ui.canvas_view import CanvasView


@dataclass(slots=True)
class SelectionServiceBundle:
    hit_testing_service: CanvasHitTestingService
    selection_controller: SelectionController


def build_selection_services(
    canvas: CanvasView,
    *,
    graph_service: CanvasGraphService,
    hit_testing_service: CanvasHitTestingService | None = None,
    active_tool_name_provider: Callable[[], str | None] | None = None,
) -> SelectionServiceBundle:
    resolved_hit_testing_service = hit_testing_service
    if resolved_hit_testing_service is None:
        resolved_hit_testing_service = CanvasHitTestingService(
            canvas,
            scene_pos_mapper=lambda event: scene_pos_from_event_for_view(canvas, event),
        )
    resolved_graph_service = graph_service
    selection_structure_service = SelectionStructureService(
        canvas, graph_service=resolved_graph_service
    )
    selection_preference_service = SelectionPreferenceService(
        canvas,
        hit_testing_service=resolved_hit_testing_service,
        structure_service=selection_structure_service,
    )
    selection_outline_service = SelectionOutlineService(
        canvas,
        graph_service=resolved_graph_service,
        active_tool_name_provider=active_tool_name_provider,
    )
    selection_note_service = SelectionNoteService(canvas)
    selection_hit_test_service = SelectionHitTestService(
        canvas,
        hit_testing_service=resolved_hit_testing_service,
        structure_service=selection_structure_service,
        graph_service=resolved_graph_service,
    )
    selection_controller = SelectionController(
        canvas,
        hit_testing_service=resolved_hit_testing_service,
        structure_service=selection_structure_service,
        preference_service=selection_preference_service,
        outline_service=selection_outline_service,
        note_service=selection_note_service,
        hit_test_service=selection_hit_test_service,
    )
    return SelectionServiceBundle(
        hit_testing_service=resolved_hit_testing_service,
        selection_controller=selection_controller,
    )


__all__ = ["SelectionServiceBundle", "build_selection_services"]
