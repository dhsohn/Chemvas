from __future__ import annotations

from types import SimpleNamespace

import chemvas.ui.selection_service_bundle as selection_service_bundle
from chemvas.ui.selection_service_bundle import build_selection_services

SERVICE_CLASS_NAMES = (
    "CanvasHitTestingService",
    "SelectionController",
    "SelectionHitTestService",
    "SelectionNoteService",
    "SelectionOutlineService",
    "SelectionPreferenceService",
    "SelectionStructureService",
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_selection_services_injects_selection_collaborators(monkeypatch) -> None:
    for class_name in SERVICE_CLASS_NAMES:
        monkeypatch.setattr(
            selection_service_bundle, class_name, _stub_service_class(class_name)
        )
    graph_service = object()
    active_tool_name_provider = object()

    services = build_selection_services(
        SimpleNamespace(),
        graph_service=graph_service,
        active_tool_name_provider=active_tool_name_provider,
    )

    hit_testing_service = services.hit_testing_service
    selection_controller = services.selection_controller
    selection_structure_service = selection_controller.kwargs["structure_service"]
    selection_preference_service = selection_controller.kwargs["preference_service"]
    selection_hit_test_service = selection_controller.kwargs["hit_test_service"]

    assert hit_testing_service.service_name == "CanvasHitTestingService"
    assert selection_controller.service_name == "SelectionController"
    assert selection_controller.kwargs["hit_testing_service"] is hit_testing_service
    assert selection_structure_service.service_name == "SelectionStructureService"
    assert selection_structure_service.kwargs["graph_service"] is graph_service
    assert selection_preference_service.service_name == "SelectionPreferenceService"
    assert (
        selection_preference_service.kwargs["hit_testing_service"]
        is hit_testing_service
    )
    assert (
        selection_preference_service.kwargs["structure_service"]
        is selection_structure_service
    )
    assert (
        selection_controller.kwargs["outline_service"].service_name
        == "SelectionOutlineService"
    )
    assert (
        selection_controller.kwargs["outline_service"].kwargs["graph_service"]
        is graph_service
    )
    assert (
        selection_controller.kwargs["outline_service"].kwargs[
            "active_tool_name_provider"
        ]
        is active_tool_name_provider
    )
    assert (
        selection_controller.kwargs["note_service"].service_name
        == "SelectionNoteService"
    )
    assert selection_hit_test_service.service_name == "SelectionHitTestService"
    assert (
        selection_hit_test_service.kwargs["hit_testing_service"] is hit_testing_service
    )
    assert (
        selection_hit_test_service.kwargs["structure_service"]
        is selection_structure_service
    )
    assert selection_hit_test_service.kwargs["graph_service"] is graph_service


def test_build_selection_services_reuses_supplied_hit_testing_service(
    monkeypatch,
) -> None:
    for class_name in SERVICE_CLASS_NAMES:
        monkeypatch.setattr(
            selection_service_bundle, class_name, _stub_service_class(class_name)
        )
    supplied_hit_testing_service = object()
    graph_service = object()

    services = build_selection_services(
        SimpleNamespace(),
        graph_service=graph_service,
        hit_testing_service=supplied_hit_testing_service,
    )

    assert services.hit_testing_service is supplied_hit_testing_service
    assert (
        services.selection_controller.kwargs["hit_testing_service"]
        is supplied_hit_testing_service
    )
    assert (
        services.selection_controller.kwargs["preference_service"].kwargs[
            "hit_testing_service"
        ]
        is supplied_hit_testing_service
    )
    assert (
        services.selection_controller.kwargs["hit_test_service"].kwargs[
            "hit_testing_service"
        ]
        is supplied_hit_testing_service
    )
