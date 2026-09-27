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


def graph_service_for(view):
    from chemvas.ui.canvas.canvas_graph_service import CanvasGraphService

    return CanvasGraphService(
        lambda: view.model,
        renderer=getattr(view, "renderer", None),
        graph_state=view.runtime_state.graph_state,
    )


def shortcut_service_for(view, **collaborators):
    from chemvas.features.hover import HoverState
    from chemvas.ui.canvas.canvas_chemdraw_shortcut_service import (
        CanvasChemdrawShortcutService,
    )
    from chemvas.ui.canvas.canvas_window_access import notify_error_for

    services = getattr(view, "services", None)
    runtime = getattr(view, "runtime_state", None)
    return CanvasChemdrawShortcutService(
        lambda: view.model,
        hover_state=getattr(runtime, "hover_preview_state", HoverState()),
        atom_label_service=getattr(services, "atom_label_service", None),
        structure_build_service=getattr(services, "structure_build_service", None),
        notify_error=lambda message: notify_error_for(view, message),
        **collaborators,
    )
