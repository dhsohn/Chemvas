"""Typed runtime service bundle shared by UI ports and bootstrap wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.ui.window.main_window_action_availability_service import (
        MainWindowActionAvailabilityService,
    )
    from chemvas.ui.window.main_window_active_canvas_ui_service import (
        MainWindowActiveCanvasUIService,
    )
    from chemvas.ui.window.main_window_canvas_document_service import (
        MainWindowCanvasDocumentService,
    )
    from chemvas.ui.window.main_window_context_bar_service import (
        MainWindowContextBarService,
    )
    from chemvas.ui.window.main_window_document_action_service import (
        MainWindowDocumentActionService,
    )
    from chemvas.ui.window.main_window_panel_service import MainWindowPanelService
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


@dataclass(slots=True, kw_only=True)
class MainWindowServices:
    action_availability_service: MainWindowActionAvailabilityService
    document_action_service: MainWindowDocumentActionService
    tool_action_service: MainWindowToolActionService
    tool_state_service: MainWindowToolStateService
    tool_routing_service: MainWindowToolRoutingService
    text_style_service: MainWindowTextStyleService
    canvas_document_service: MainWindowCanvasDocumentService
    active_canvas_ui_service: MainWindowActiveCanvasUIService
    ui_assembly_service: MainWindowUIAssemblyService
    context_bar_service: MainWindowContextBarService
    status_service: MainWindowStatusService
    panel_service: MainWindowPanelService
    history_service_for_window: object


__all__ = ["MainWindowServices"]
