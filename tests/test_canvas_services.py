"""Canvas setup assembles one complete, correctly typed service graph."""

from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

from chemvas.adapters.qt.renderer import Renderer
from chemvas.ui.annotations.arrows import ArrowRenderer
from chemvas.ui.annotations.graphics import AnnotationGraphics
from chemvas.ui.canvas.canvas_atom_mutation_service import CanvasAtomMutationService
from chemvas.ui.canvas.canvas_bond_mutation_service import CanvasBondMutationService
from chemvas.ui.canvas.canvas_chemdraw_shortcut_service import (
    CanvasChemdrawShortcutService,
)
from chemvas.ui.canvas.canvas_color_mutation_service import CanvasColorMutationService
from chemvas.ui.canvas.canvas_document_session_service import (
    CanvasDocumentSessionService,
)
from chemvas.ui.canvas.canvas_geometry_controller import CanvasGeometryController
from chemvas.ui.canvas.canvas_graph_service import CanvasGraphService
from chemvas.ui.canvas.canvas_handle_controller import CanvasHandleController
from chemvas.ui.canvas.canvas_history_recording_service import (
    CanvasHistoryRecordingService,
)
from chemvas.ui.canvas.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas.canvas_hit_testing_service import CanvasHitTestingService
from chemvas.ui.canvas.canvas_input_controller import CanvasInputController
from chemvas.ui.canvas.canvas_mark_scene_service import CanvasMarkSceneService
from chemvas.ui.canvas.canvas_move_controller import CanvasMoveController
from chemvas.ui.canvas.canvas_note_controller import CanvasNoteController
from chemvas.ui.canvas.canvas_pointer_controller import CanvasPointerController
from chemvas.ui.canvas.canvas_ring_fill_scene_service import CanvasRingFillSceneService
from chemvas.ui.canvas.canvas_runtime_services import CanvasRuntimeServices
from chemvas.ui.canvas.canvas_scene_reset_service import CanvasSceneResetService
from chemvas.ui.canvas.canvas_services import attach_canvas_services
from chemvas.ui.canvas.canvas_style_controller import CanvasStyleController
from chemvas.ui.canvas.canvas_tool_mode_controller import CanvasToolModeController
from chemvas.ui.canvas.canvas_view import CanvasView
from chemvas.ui.insert.insert_controller import InsertController
from chemvas.ui.molecule.atom_label_service import AtomLabelService
from chemvas.ui.molecule.structure_build_service import StructureBuildService
from chemvas.ui.scene.scene_clipboard_controller import SceneClipboardController
from chemvas.ui.scene.scene_decoration_service import SceneDecorationService
from chemvas.ui.scene.scene_delete_controller import SceneDeleteController
from chemvas.ui.scene.scene_item_controller import SceneItemController
from chemvas.ui.scene.scene_transform_controller import SceneTransformController
from chemvas.ui.selection.selection_controller import SelectionController
from chemvas.ui.selection.selection_rotation_controller import (
    SelectionRotationController,
)
from chemvas.ui.tools.handle_mutation_service import HandleMutationService
from chemvas.ui.tools.handle_overlay_service import HandleOverlayService
from chemvas.ui.tools.hover import HoverController
from chemvas.ui.tools.tool_controller import ToolController

EXPECTED_TYPES: dict[str, type] = {
    "graph_service": CanvasGraphService,
    "hit_testing_service": CanvasHitTestingService,
    "selection": SelectionController,
    "hover": HoverController,
    "tool_controller": ToolController,
    "atom_label_service": AtomLabelService,
    "history_service": CanvasHistoryService,
    "handle_controller": CanvasHandleController,
    "handle_overlay_service": HandleOverlayService,
    "handle_mutation_service": HandleMutationService,
    "note_controller": CanvasNoteController,
    "move_controller": CanvasMoveController,
    "selection_rotation_controller": SelectionRotationController,
    "canvas_atom_mutation_service": CanvasAtomMutationService,
    "canvas_bond_mutation_service": CanvasBondMutationService,
    "structure_build_service": StructureBuildService,
    "insert_controller": InsertController,
    "scene_clipboard_controller": SceneClipboardController,
    "scene_delete_controller": SceneDeleteController,
    "scene_transform_controller": SceneTransformController,
    "style_controller": CanvasStyleController,
    "canvas_color_mutation_service": CanvasColorMutationService,
    "arrow_build_service": ArrowRenderer,
    "canvas_mark_scene_service": CanvasMarkSceneService,
    "scene_decoration_build_service": AnnotationGraphics,
    "scene_decoration_service": SceneDecorationService,
    "input_controller": CanvasInputController,
    "pointer_controller": CanvasPointerController,
    "tool_mode_controller": CanvasToolModeController,
    "chemdraw_shortcut_service": CanvasChemdrawShortcutService,
    "canvas_document_session_service": CanvasDocumentSessionService,
    "canvas_history_recording_service": CanvasHistoryRecordingService,
    "canvas_scene_reset_service": CanvasSceneResetService,
    "scene_item_controller": SceneItemController,
    "geometry_controller": CanvasGeometryController,
    "canvas_ring_fill_scene_service": CanvasRingFillSceneService,
}


def test_expected_types_cover_every_runtime_field() -> None:
    assert set(EXPECTED_TYPES) == {f.name for f in fields(CanvasRuntimeServices)}


@pytest.fixture
def canvas(qt_application):
    view = CanvasView(renderer=Renderer())
    try:
        yield view
    finally:
        view.deleteLater()


def test_canvas_setup_assembles_every_runtime_with_its_declared_type(
    canvas,
) -> None:
    services = canvas.services

    assert isinstance(services, CanvasRuntimeServices)
    for name, expected in EXPECTED_TYPES.items():
        assert isinstance(getattr(services, name), expected), name


def test_canvas_setup_shares_one_instance_per_runtime(canvas) -> None:
    services = canvas.services

    assert services.history_service is canvas.runtime_state.history_service
    assert services.arrow_build_service is canvas.render_context.arrows
    assert services.scene_decoration_build_service is canvas.render_context.decorations
    assert services.tool_controller.active is not None
    assert services.tool_controller.active.name == "bond"


def test_attach_canvas_services_stores_the_runtime_on_the_canvas() -> None:
    target = SimpleNamespace()
    services = object()

    attach_canvas_services(target, services)  # type: ignore[arg-type]

    assert target.services is services
