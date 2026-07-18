"""Compatibility import for the grouped canvas runtime service container."""

from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices

CanvasServices = CanvasRuntimeServices

__all__ = ["CanvasRuntimeServices", "CanvasServices"]
