"""Assemble the per-window services.

Each service reads window state through ``chemvas.ui.window.main_window_ports``
directly; only cross-service collaborators and the two late-bound callbacks
(context-bar refresh, document chrome refresh) are injected here.
"""

from __future__ import annotations

from typing import Any

from chemvas.adapters.qt.renderer import Renderer
from chemvas.bootstrap.file_open import document_open_target
from chemvas.bootstrap.window_registry import open_new_window
from chemvas.ui.canvas.canvas_view import CanvasView
from chemvas.ui.window.main_window_action_availability_service import (
    MainWindowActionAvailabilityService,
)
from chemvas.ui.window.main_window_active_canvas_ui_service import (
    MainWindowActiveCanvasUIService,
)
from chemvas.ui.window.main_window_canvas_document_service import (
    MainWindowCanvasDocumentService,
)
from chemvas.ui.window.main_window_context_bar_pages import (
    MainWindowContextBarPageBuilder,
)
from chemvas.ui.window.main_window_context_bar_service import (
    MainWindowContextBarService,
)
from chemvas.ui.window.main_window_document_action_service import (
    MainWindowDocumentActionService,
)
from chemvas.ui.window.main_window_panel_service import MainWindowPanelService
from chemvas.ui.window.main_window_panel_toolbar import (
    MainWindowPanelToolbarCallbacks,
)
from chemvas.ui.window.main_window_ports import active_canvas_or_none_for_window
from chemvas.ui.window.main_window_service_types import MainWindowServices
from chemvas.ui.window.main_window_status_service import MainWindowStatusService
from chemvas.ui.window.main_window_text_style_service import (
    MainWindowTextStyleService,
)
from chemvas.ui.window.main_window_tool_action_service import (
    MainWindowToolActionService,
)
from chemvas.ui.window.main_window_tool_routing_service import (
    MainWindowToolRoutingService,
)
from chemvas.ui.window.main_window_tool_state_service import (
    MainWindowToolStateService,
)
from chemvas.ui.window.main_window_ui_assembly_service import (
    MainWindowUIAssemblyService,
)


def _frameless_canvas_view() -> CanvasView:
    # The tab widget draws the border around a canvas; the view itself is bare.
    canvas = CanvasView(renderer=Renderer())
    canvas.setFrameStyle(0)
    return canvas


def build_main_window_services() -> MainWindowServices:
    action_availability_service = MainWindowActionAvailabilityService()
    text_style_service = MainWindowTextStyleService()
    status_service = MainWindowStatusService()

    context_bar_service: MainWindowContextBarService
    tool_state_service = MainWindowToolStateService(
        status_service=status_service,
        refresh_context_bar_for_window=lambda window: (
            context_bar_service.refresh_window(window)
        ),
    )
    tool_routing_service = MainWindowToolRoutingService(
        tool_state_service=tool_state_service,
    )
    context_bar_service = MainWindowContextBarService(
        page_builder=MainWindowContextBarPageBuilder(
            tool_state_service=tool_state_service,
            tool_routing_service=tool_routing_service,
        ),
    )

    canvas_document_service: MainWindowCanvasDocumentService

    def refresh_document_chrome_for_window(
        window: Any, *, edited_note: object | None = None
    ) -> None:
        # Late-bound: canvas_document_service is assigned just below. Refreshes
        # the active tab's unsaved marker + the window-modified title after edits.
        panel = window.ui_references.calculation_panel
        if panel is not None:
            panel.document_changed()
        canvas = active_canvas_or_none_for_window(window)
        if canvas is not None:
            canvas_document_service.refresh_tab_title(
                window, canvas, edited_note=edited_note
            )

    active_canvas_ui_service = MainWindowActiveCanvasUIService(
        status_service=status_service,
        context_bar_service=context_bar_service,
        action_availability_service=action_availability_service,
        tool_state_service=tool_state_service,
        refresh_document_chrome_for_window=refresh_document_chrome_for_window,
    )
    canvas_document_service = MainWindowCanvasDocumentService(
        active_canvas_ui=active_canvas_ui_service,
        canvas_factory=_frameless_canvas_view,
        status_service=status_service,
    )
    document_action_service = MainWindowDocumentActionService()
    tool_action_service = MainWindowToolActionService(
        tool_state_service=tool_state_service,
    )
    panel_service = MainWindowPanelService(
        document_action_service=document_action_service,
    )
    panel_toolbar_callbacks = MainWindowPanelToolbarCallbacks(
        save_canvas=document_action_service.save_canvas,
        save_canvas_as=document_action_service.save_canvas_as,
        load_canvas=lambda window: document_action_service.load_canvas(
            window, target_provider=lambda: document_open_target(window)
        ),
        export_figure=document_action_service.export_figure,
        export_mol=lambda window: document_action_service.export_mol(
            window, selected_only=True
        ),
        open_preview_window=panel_service.open_preview_window,
        new_canvas=lambda window: open_new_window(window, inherit_settings=True),
        # Edit > Rotate... hands the canvas to the Select tool, whose options
        # bar carries the angle input; checking the button alone would leave
        # the canvas in the previous tool.
        show_rotate_options=lambda window: tool_state_service.set_tool_with_status(
            window, "select"
        ),
        set_note_font_family=text_style_service.set_note_font_family,
        open_recent_path=lambda window, path: (
            document_action_service.load_canvas_from_path(
                window, path, target_provider=lambda: document_open_target(window)
            )
        ),
    )
    ui_assembly_service = MainWindowUIAssemblyService(
        build_tool_actions_for_window=tool_action_service.build_tool_actions,
        panel_toolbar_callbacks=panel_toolbar_callbacks,
    )
    return MainWindowServices(
        action_availability_service=action_availability_service,
        document_action_service=document_action_service,
        tool_action_service=tool_action_service,
        tool_state_service=tool_state_service,
        tool_routing_service=tool_routing_service,
        text_style_service=text_style_service,
        canvas_document_service=canvas_document_service,
        active_canvas_ui_service=active_canvas_ui_service,
        ui_assembly_service=ui_assembly_service,
        context_bar_service=context_bar_service,
        status_service=status_service,
        panel_service=panel_service,
    )


__all__ = ["MainWindowServices", "build_main_window_services"]
