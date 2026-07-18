from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from chemvas.ui.canvas_runtime_services import (
    _LEGACY_SERVICE_PATHS,
    CanvasRuntimeServices,
)

_CANONICAL_SERVICE_GROUPS = frozenset(
    group_name for group_name, _member_name in _LEGACY_SERVICE_PATHS.values()
)


class _LegacyServiceGroup:
    """Nested view over a flat, lightweight legacy test-double container."""

    __slots__ = ("_group_name", "_target")

    def __init__(self, target: Any, group_name: str) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_group_name", group_name)

    def __getattr__(self, name: str) -> Any:
        path = _LEGACY_SERVICE_PATHS.get(name)
        if path is None or path[0] != self._group_name:
            raise AttributeError(name)
        return getattr(self._target, path[1])

    def __setattr__(self, name: str, value: Any) -> None:
        path = _LEGACY_SERVICE_PATHS.get(name)
        if path is None or path[0] != self._group_name:
            raise AttributeError(name)
        setattr(self._target, path[1], value)


class _LegacyCanvasRuntimeServices:
    """Compatibility adapter used only for non-canonical duck-typed fixtures."""

    __slots__ = ("_target",)

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)

    def __getattr__(self, name: str) -> Any:
        if name in _CANONICAL_SERVICE_GROUPS:
            existing = getattr(self._target, name, None)
            if existing is not None:
                return existing
            return _LegacyServiceGroup(self._target, name)
        return getattr(self._target, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._target, name, value)


def canvas_services_for(canvas: Any) -> CanvasRuntimeServices:
    services = getattr(canvas, "services", None)
    if isinstance(services, CanvasRuntimeServices):
        return cast(CanvasRuntimeServices, services)
    if services is not None:
        return cast(CanvasRuntimeServices, _LegacyCanvasRuntimeServices(services))
    msg = "Canvas services are not available"
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
