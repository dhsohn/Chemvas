from __future__ import annotations


def canvas_services_for(canvas):
    services = getattr(canvas, "services", None)
    if services is not None:
        return services
    msg = "Canvas services are not available"
    raise AttributeError(msg)


__all__ = [
    "canvas_services_for",
]
