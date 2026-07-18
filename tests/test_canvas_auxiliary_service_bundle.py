from __future__ import annotations

from types import SimpleNamespace

import chemvas.ui.canvas_auxiliary_service_bundle as canvas_auxiliary_service_bundle
from chemvas.ui.canvas_auxiliary_service_bundle import (
    CanvasAuxiliaryServiceBundle,
    build_canvas_auxiliary_services,
)


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

    return StubService


def test_build_canvas_auxiliary_services_wires_explicit_collaborators(
    monkeypatch,
) -> None:
    for class_name in (
        "AtomLabelService",
        "BenzenePreviewService",
        "StructureInsertService",
    ):
        monkeypatch.setattr(
            canvas_auxiliary_service_bundle, class_name, _stub_service_class(class_name)
        )

    canvas = SimpleNamespace()
    move_controller = object()
    graph_service = object()
    history_service = object()
    hover_refresh = object()
    structure_build_service = object()
    note_controller = object()

    services = build_canvas_auxiliary_services(
        canvas,
        move_controller=move_controller,
        graph_service=graph_service,
        history_service=history_service,
        hover_refresh=hover_refresh,
        structure_build_service=structure_build_service,
        note_controller=note_controller,
    )

    assert isinstance(services, CanvasAuxiliaryServiceBundle)
    assert services.atom_label_service.kwargs == {
        "move_controller": move_controller,
        "graph_service": graph_service,
        "history_service": history_service,
        "hover_refresh": hover_refresh,
    }
    assert services.benzene_preview_service.kwargs == {
        "structure_build_service": structure_build_service
    }
    assert services.structure_insert_service.kwargs == {
        "note_controller": note_controller
    }
