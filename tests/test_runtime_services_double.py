"""Guard: the test double's SERVICE_PATHS table matches the real service graph.

``tests/runtime_services.py`` is the most widely used double in the suite; if
its (group, member) table drifts from the real ``CanvasRuntimeServices``
layout, dozens of test files pass against a graph the app no longer has.
"""

from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

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
from tests.runtime_services import SERVICE_PATHS, canvas_runtime_services

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


@pytest.mark.parametrize(
    "name", [field.name for field in fields(CanvasRuntimeServices)]
)
def test_canonical_fields_preserve_constructor_and_assignment_identity(
    name: str,
) -> None:
    original = object()
    replacement = object()
    services = canvas_runtime_services(**{name: original})

    assert getattr(services, name) is original
    setattr(services, name, replacement)
    assert getattr(services, name) is replacement


@pytest.mark.parametrize("name", SERVICE_PATHS)
def test_intentional_aliases_write_into_the_canonical_bundle(name: str) -> None:
    original = object()
    replacement = object()
    services = canvas_runtime_services(**{name: original})
    group_name, member_name = SERVICE_PATHS[name]
    group = getattr(services, group_name)

    assert getattr(services, name) is original
    assert getattr(group, member_name) is original
    setattr(services, name, replacement)
    assert getattr(services, name) is replacement
    assert getattr(group, member_name) is replacement


@pytest.mark.parametrize(
    "name", ["history_servcie", "status_service", "unknown_service"]
)
def test_constructor_rejects_unknown_service_names(name: str) -> None:
    with pytest.raises(TypeError, match=name):
        canvas_runtime_services(**{name: object()})


@pytest.mark.parametrize(
    "name", ["history_servcie", "status_service", "unknown_service"]
)
def test_assignment_rejects_unknown_service_names(name: str) -> None:
    services = canvas_runtime_services()

    with pytest.raises(AttributeError, match=name):
        setattr(services, name, object())
    assert not hasattr(services, name)


def test_constructor_checks_unknown_names_before_mutating_supplied_bundles() -> None:
    original = object()
    selection = SimpleNamespace(selection_controller=original)

    with pytest.raises(TypeError, match="history_servcie"):
        canvas_runtime_services(
            selection=selection,
            selection_controller=object(),
            history_servcie=object(),
        )
    assert selection.selection_controller is original


def test_alias_reuses_an_explicitly_supplied_bundle() -> None:
    selection = SimpleNamespace(selection_controller=object())
    controller = object()
    services = canvas_runtime_services(
        selection=selection, selection_controller=controller
    )

    assert services.selection is selection
    assert services.selection_controller is controller
    assert selection.selection_controller is controller


def test_partial_defaults_remain_independent_between_fixtures() -> None:
    first = canvas_runtime_services()
    second = canvas_runtime_services()

    for name in (*_BUNDLES, "hover"):
        assert isinstance(getattr(first, name), SimpleNamespace)
        assert getattr(first, name) is not getattr(second, name)
    for name in (
        "atom_label_service",
        "graph_service",
        "history_service",
        "tool_controller",
    ):
        assert getattr(first, name) is None
    first.selection_controller = object()
    with pytest.raises(AttributeError, match="selection_controller"):
        _ = second.selection_controller
