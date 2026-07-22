from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices


def canvas_services_for(canvas: Any) -> CanvasRuntimeServices:
    services = getattr(canvas, "services", None)
    if isinstance(services, CanvasRuntimeServices):
        return cast(CanvasRuntimeServices, services)
    msg = "Canonical canvas runtime services are not available"
    raise AttributeError(msg)


def optional_canvas_service_method(
    canvas: Any,
    service_getter: Callable[[Any], Any],
    method_name: str,
) -> Callable[..., Any] | None:
    try:
        service = service_getter(canvas)
    except AttributeError:
        return None
    method = getattr(service, method_name, None)
    return method if callable(method) else None


__all__ = [
    "canvas_services_for",
    "optional_canvas_service_method",
]
