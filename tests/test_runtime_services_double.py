"""Guard: the test double's SERVICE_PATHS table matches the real service graph.

``tests/runtime_services.py`` is the most widely used double in the suite; if
its (group, member) table drifts from the real ``CanvasRuntimeServices``
layout, dozens of test files pass against a graph the app no longer has.
"""

from __future__ import annotations

from dataclasses import fields

from chemvas.ui.canvas_document_service_bundle import CanvasDocumentServiceBundle
from chemvas.ui.canvas_input_service_bundle import CanvasInputServiceBundle
from chemvas.ui.canvas_interaction_service_bundle import CanvasInteractionServiceBundle
from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices
from chemvas.ui.canvas_scene_view_service_bundle import CanvasSceneViewServiceBundle
from chemvas.ui.handle_service_bundle import HandleServiceBundle
from chemvas.ui.scene_decoration_service_bundle import SceneDecorationServiceBundle
from chemvas.ui.scene_operation_service_bundle import SceneOperationServiceBundle
from chemvas.ui.selection_service_bundle import SelectionServiceBundle
from chemvas.ui.structure_service_bundle import StructureServiceBundle
from tests.runtime_services import SERVICE_PATHS

_BUNDLES = {
    "document": CanvasDocumentServiceBundle,
    "input": CanvasInputServiceBundle,
    "interaction": CanvasInteractionServiceBundle,
    "scene_view": CanvasSceneViewServiceBundle,
    "handles": HandleServiceBundle,
    "scene_decoration": SceneDecorationServiceBundle,
    "scene_operations": SceneOperationServiceBundle,
    "selection": SelectionServiceBundle,
    "structure": StructureServiceBundle,
}


def test_service_paths_resolve_on_the_real_service_graph() -> None:
    runtime_groups = {field.name for field in fields(CanvasRuntimeServices)}
    for name, (group, member) in SERVICE_PATHS.items():
        assert group in runtime_groups, f"{name}: unknown runtime group {group!r}"
        bundle = _BUNDLES.get(group)
        assert bundle is not None, f"{name}: group {group!r} has no bundle mapping"
        members = {field.name for field in fields(bundle)}
        assert member in members, (
            f"{name}: SERVICE_PATHS points at {group}.{member}, but "
            f"{bundle.__name__} has no such field"
        )
