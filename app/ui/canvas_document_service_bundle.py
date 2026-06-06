from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ui.canvas_document_session_service import CanvasDocumentSessionService
from ui.canvas_history_recording_service import CanvasHistoryRecordingService
from ui.canvas_scene_reset_service import CanvasSceneResetService

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class CanvasDocumentServiceBundle:
    canvas_document_session_service: CanvasDocumentSessionService
    canvas_history_recording_service: CanvasHistoryRecordingService
    canvas_scene_reset_service: CanvasSceneResetService


def build_canvas_document_services(
    canvas: CanvasView | Any,
    *,
    hit_testing_service: Any,
    graph_service: Any,
    structure_build_service: Any,
    history_service: Any,
) -> CanvasDocumentServiceBundle:
    canvas_document_session_service = CanvasDocumentSessionService(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        structure_build_service=structure_build_service,
        history_service=history_service,
    )
    canvas_history_recording_service = CanvasHistoryRecordingService(
        canvas,
        history_service=history_service,
    )
    canvas_scene_reset_service = CanvasSceneResetService(
        canvas,
        hit_testing_service=hit_testing_service,
    )
    return CanvasDocumentServiceBundle(
        canvas_document_session_service=canvas_document_session_service,
        canvas_history_recording_service=canvas_history_recording_service,
        canvas_scene_reset_service=canvas_scene_reset_service,
    )


__all__ = ["CanvasDocumentServiceBundle", "build_canvas_document_services"]
