from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ui.main_window_icon_factory import MainWindowIconFactory
from ui.main_window_services import MainWindowServices, build_main_window_services
from ui.main_window_state import MainWindowState
from ui.main_window_tab_references import MainWindowTabReferences
from ui.main_window_tab_setup import build_canvas_tab_assembly
from ui.main_window_ui_references import MainWindowUiReferences
from ui.preview_3d import Preview3D


@dataclass(slots=True)
class MainWindowBootstrapRuntime:
    state: MainWindowState
    ui_refs: MainWindowUiReferences
    tab_refs: MainWindowTabReferences
    services: MainWindowServices
    preview_3d: Preview3D
    icon_factory: Callable[[object], MainWindowIconFactory]


def build_main_window_runtime(
    window,
    *,
    build_tabs=build_canvas_tab_assembly,
    build_services=build_main_window_services,
    preview_factory=Preview3D,
    icon_factory=MainWindowIconFactory,
) -> MainWindowBootstrapRuntime:
    window.setWindowTitle("Chemvas")
    window.resize(1100, 760)

    state = MainWindowState()
    ui_refs = MainWindowUiReferences()
    services = build_services()

    def on_canvas_tab_moved(from_index: int, to_index: int) -> None:
        services.canvas_tab_ui_service.on_canvas_tab_moved(window, from_index, to_index)

    def on_canvas_tab_changed(index: int) -> None:
        services.active_canvas_ui_service.on_canvas_tab_changed(window, index)

    def on_canvas_tab_close_requested(index: int) -> None:
        services.canvas_tab_ui_service.close_canvas_tab(window, index)

    tab_assembly = build_tabs(
        window,
        on_canvas_tab_moved=on_canvas_tab_moved,
        on_canvas_tab_changed=on_canvas_tab_changed,
        on_canvas_tab_close_requested=on_canvas_tab_close_requested,
    )
    tab_refs = MainWindowTabReferences.from_assembly(tab_assembly)
    preview_3d = preview_factory()
    window.setCentralWidget(tab_refs.canvas_tabs)
    return MainWindowBootstrapRuntime(
        state=state,
        ui_refs=ui_refs,
        tab_refs=tab_refs,
        services=services,
        preview_3d=preview_3d,
        icon_factory=icon_factory,
    )


def bootstrap_main_window(window, runtime: MainWindowBootstrapRuntime) -> None:
    runtime.services.canvas_document_service.add_canvas(
        window,
        name=runtime.state.next_canvas_name(),
        select=True,
    )
    runtime.ui_refs.icon_factory = runtime.icon_factory(window)
    toolbar_assembly = runtime.services.ui_assembly_service.init_toolbars(window)
    runtime.ui_refs.apply_toolbar_assembly(toolbar_assembly)
    runtime.services.action_availability_service.update_action_availability(window)
    runtime.services.context_bar_service.init_context_bar(window)
    runtime.services.panel_service.init_panels(window)
    runtime.services.ui_assembly_service.apply_theme(window)
    runtime.services.active_canvas_ui_service.bind_active_canvas(window)
    runtime.services.status_service.init_status_bar(window)
    runtime.services.context_bar_service.refresh_window(window)


__all__ = ["MainWindowBootstrapRuntime", "bootstrap_main_window", "build_main_window_runtime"]
