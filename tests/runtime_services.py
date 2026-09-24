from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace
from typing import Any

from chemvas.ui.canvas.canvas_runtime_services import CanvasRuntimeServices

_SERVICE_NAMES = frozenset(field.name for field in fields(CanvasRuntimeServices))

# Focused tests usually stub only a few runtimes; these two are read as
# objects with attributes by canvas setup and selection callbacks, so they
# default to an empty namespace instead of ``None``.
_NAMESPACE_DEFAULTS = frozenset({"hover", "selection"})


class CanvasRuntimeServicesDouble(CanvasRuntimeServices):
    """Partial canonical service graph for focused UI tests.

    Unknown service names are rejected at construction and assignment so a
    typo cannot silently become an attribute the production graph lacks.
    """

    __slots__ = ()

    def __init__(self, **services: Any) -> None:
        unknown = services.keys() - _SERVICE_NAMES
        if unknown:
            raise TypeError(
                f"Unknown canvas runtime services: {', '.join(sorted(unknown))}"
            )
        values: dict[str, Any] = {
            name: (SimpleNamespace() if name in _NAMESPACE_DEFAULTS else None)
            for name in _SERVICE_NAMES
        }
        values.update(services)
        super().__init__(**values)

    def __setattr__(self, name: str, value: Any) -> None:
        if name not in _SERVICE_NAMES:
            raise AttributeError(name)
        super().__setattr__(name, value)


def canvas_runtime_services(**services: Any) -> CanvasRuntimeServicesDouble:
    return CanvasRuntimeServicesDouble(**services)


__all__ = [
    "CanvasRuntimeServicesDouble",
    "canvas_runtime_services",
]
