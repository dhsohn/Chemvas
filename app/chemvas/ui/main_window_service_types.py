"""Typed runtime service bundle shared by UI ports and bootstrap wiring."""

from __future__ import annotations

from dataclasses import dataclass

from chemvas.ui.main_window_action_availability_service import (
    MainWindowActionAvailabilityService,
)
from chemvas.ui.main_window_active_canvas_ui_service import (
    MainWindowActiveCanvasUIService,
)
from chemvas.ui.main_window_canvas_document_service import (
    MainWindowCanvasDocumentService,
)
from chemvas.ui.main_window_canvas_tab_ui_service import MainWindowCanvasTabUIService
from chemvas.ui.main_window_context_bar_service import MainWindowContextBarService
from chemvas.ui.main_window_context_page_state_service import (
    MainWindowContextPageStateService,
)
from chemvas.ui.main_window_document_action_service import (
    MainWindowDocumentActionService,
)
from chemvas.ui.main_window_panel_service import MainWindowPanelService
from chemvas.ui.main_window_status_service import MainWindowStatusService
from chemvas.ui.main_window_text_style_service import MainWindowTextStyleService
from chemvas.ui.main_window_tool_action_service import MainWindowToolActionService
from chemvas.ui.main_window_tool_routing_service import MainWindowToolRoutingService
from chemvas.ui.main_window_tool_state_service import MainWindowToolStateService
from chemvas.ui.main_window_ui_assembly_service import MainWindowUIAssemblyService


@dataclass(slots=True)
class MainWindowServices:
    action_availability_service: MainWindowActionAvailabilityService
    document_action_service: MainWindowDocumentActionService
    tool_action_service: MainWindowToolActionService
    tool_state_service: MainWindowToolStateService
    context_page_state_service: MainWindowContextPageStateService
    tool_routing_service: MainWindowToolRoutingService
    text_style_service: MainWindowTextStyleService
    canvas_tab_ui_service: MainWindowCanvasTabUIService
    canvas_document_service: MainWindowCanvasDocumentService
    active_canvas_ui_service: MainWindowActiveCanvasUIService
    ui_assembly_service: MainWindowUIAssemblyService
    context_bar_service: MainWindowContextBarService
    status_service: MainWindowStatusService
    panel_service: MainWindowPanelService
    history_service_for_window: object


__all__ = ["MainWindowServices"]
