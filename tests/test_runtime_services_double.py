"""Guard: the test double accepts exactly the real ``CanvasRuntimeServices`` fields.

``tests/runtime_services.py`` is the most widely used double in the suite; if
it accepted names the real container lacks, dozens of test files would pass
against a service graph the app no longer has.
"""

from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

from chemvas.ui.canvas.canvas_runtime_services import CanvasRuntimeServices
from tests.runtime_services import canvas_runtime_services


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


def test_partial_defaults_remain_independent_between_fixtures() -> None:
    first = canvas_runtime_services()
    second = canvas_runtime_services()

    for name in ("hover", "selection"):
        assert isinstance(getattr(first, name), SimpleNamespace)
        assert getattr(first, name) is not getattr(second, name)
    for name in (
        "atom_label_service",
        "graph_service",
        "history_service",
        "tool_controller",
        "input_controller",
    ):
        assert getattr(first, name) is None
    first.selection = object()
    assert isinstance(second.selection, SimpleNamespace)
