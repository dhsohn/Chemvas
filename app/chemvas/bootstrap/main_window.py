"""Composition root for the concrete Chemvas main window runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from chemvas.bootstrap.main_window_runtime import (
    bootstrap_main_window,
    build_main_window_runtime,
)
from chemvas.bootstrap.window_registry import forget_window, next_document_name
from chemvas.shell.main_window import MainWindow

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


def build_main_window() -> MainWindow:
    return MainWindow(
        build_runtime=build_main_window_runtime,
        bootstrap_window=bootstrap_main_window,
        forget_window=forget_window,
    )


def initialize_main_window_document(window: MainWindow) -> None:
    """Apply bootstrap-only naming after a new window enters the registry."""
    from chemvas.ui.main_window_ports import (
        services_for_window,
        tab_references_for_window,
    )

    name = next_document_name()
    services = services_for_window(window)
    current_widget = tab_references_for_window(window).canvas_tabs.currentWidget()
    if current_widget is None:
        return
    canvas = cast("CanvasView", current_widget)
    services.canvas_document_service.set_display_name(canvas, name)
    services.canvas_document_service.refresh_tab_title(window, canvas)
    services.status_service.refresh_status_context(window)


__all__ = ["build_main_window", "initialize_main_window_document"]
