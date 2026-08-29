from __future__ import annotations

from typing import Any, cast

from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices


def canvas_services_for(canvas: Any) -> CanvasRuntimeServices:
    services = getattr(canvas, "services", None)
    if isinstance(services, CanvasRuntimeServices):
        return cast("CanvasRuntimeServices", services)
    msg = "Canonical canvas runtime services are not available"
    raise AttributeError(msg)


__all__ = [
    "canvas_services_for",
]
