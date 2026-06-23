from __future__ import annotations

from dataclasses import dataclass

from ui.main_window_action_availability_service import (
    MainWindowActionAvailabilityService,
)
from ui.main_window_active_canvas_ui_service import MainWindowActiveCanvasUIService
from ui.main_window_app import open_new_window
from ui.main_window_canvas_document_service import MainWindowCanvasDocumentService
from ui.main_window_canvas_ports import (
    active_canvas_for_window,
    active_canvas_index_for_window,
    active_canvas_name_for_window,
    active_canvas_or_none_for_window,
    active_tool_name_for_window,
    all_canvases_for_window,
    bond_length_px_for_window,
    canvas_count_for_window,
    clear_context_bar_page_override_for_window,
    color_mutation_service_for_window,
    color_tool_for_window,
    context_bar_page_override_for_window,
    current_zoom_percent_for_window,
    document_session_service_for_window,
    geometry_controller_for_window,
    has_exportable_atoms_for_window,
    history_service_for_window,
    insert_controller_for_window,
    next_canvas_name_for_window,
    scene_transform_controller_for_window,
    selected_scene_items_for_window,
    set_context_bar_page_override_for_window,
    set_last_canvas_tab_index_for_window,
    style_controller_for_window,
    tab_reactions_suspended_for_window,
    tool_mode_controller_for_window,
    tool_settings_for_window,
)
from ui.main_window_canvas_tab_ui_service import MainWindowCanvasTabUIService
from ui.main_window_context_bar_pages import MainWindowContextBarPageBuilder
from ui.main_window_context_bar_service import MainWindowContextBarService
from ui.main_window_context_page_state_service import (
    MainWindowContextPageStateService,
)
from ui.main_window_document_action_service import MainWindowDocumentActionService
from ui.main_window_panel_service import MainWindowPanelService
from ui.main_window_panel_toolbar import MainWindowPanelToolbarCallbacks
from ui.main_window_preview_ports import preview_for_window
from ui.main_window_status_service import MainWindowStatusService
from ui.main_window_tab_ports import tab_references_for_window
from ui.main_window_text_style_service import MainWindowTextStyleService
from ui.main_window_tool_action_service import MainWindowToolActionService
from ui.main_window_tool_routing_service import MainWindowToolRoutingService
from ui.main_window_tool_state_service import MainWindowToolStateService
from ui.main_window_ui_assembly_service import MainWindowUIAssemblyService
from ui.main_window_ui_ports import (
    apply_preview_window_assembly_for_window,
    atom_input_for_window,
    export_xyz_button_for_window,
    icon_factory_for_window,
    preview_window_for_window,
    redo_button_for_window,
    set_atom_input_for_window,
    tool_action_for_window,
    tool_actions_for_window,
    undo_button_for_window,
)


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


def build_main_window_services() -> MainWindowServices:
    action_availability_service = MainWindowActionAvailabilityService(
        history_service_for_window=history_service_for_window,
        has_exportable_atoms_for_window=has_exportable_atoms_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        undo_button_for_window=undo_button_for_window,
        redo_button_for_window=redo_button_for_window,
        export_xyz_button_for_window=export_xyz_button_for_window,
    )
    text_style_service = MainWindowTextStyleService(
        style_controller_for_window=style_controller_for_window,
    )
    status_service = MainWindowStatusService(
        active_tool_name_for_window=active_tool_name_for_window,
        current_zoom_percent_for_window=current_zoom_percent_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        canvas_count_for_window=canvas_count_for_window,
        active_canvas_name_for_window=active_canvas_name_for_window,
        active_canvas_index_for_window=active_canvas_index_for_window,
        context_bar_page_override_for_window=context_bar_page_override_for_window,
    )
    tool_state_service = MainWindowToolStateService(
        tool_mode_controller_for_window=tool_mode_controller_for_window,
        active_tool_name_for_window=active_tool_name_for_window,
        tool_settings_for_window=tool_settings_for_window,
        tool_actions_for_window=tool_actions_for_window,
        tool_action_for_window=tool_action_for_window,
        status_service=status_service,
    )
    context_page_state_service: MainWindowContextPageStateService
    document_action_service: MainWindowDocumentActionService

    def activate_bond_style_for_window(window, value: str) -> None:
        context_page_state_service.set_tool_with_status(
            window,
            "bond",
            reset_bond_style=False,
        )
        tool_state_service.set_bond_style(window, value)

    def set_bond_length_for_window(window) -> None:
        document_action_service.set_bond_length(window)

    tool_routing_service: MainWindowToolRoutingService

    def apply_color_preset_for_window(window, hex_value: str) -> None:
        tool_routing_service.apply_color_preset(window, hex_value)

    def apply_ring_fill_preset_for_window(window, hex_value: str) -> None:
        tool_routing_service.apply_ring_fill_preset(window, hex_value)

    context_bar_service = MainWindowContextBarService(
        page_builder=MainWindowContextBarPageBuilder(
            insert_controller_for_window=insert_controller_for_window,
            tool_mode_controller_for_window=tool_mode_controller_for_window,
            tool_state_service=tool_state_service,
            activate_bond_style_for_window=activate_bond_style_for_window,
            set_bond_length_for_window=set_bond_length_for_window,
            apply_color_preset_for_window=apply_color_preset_for_window,
            apply_ring_fill_preset_for_window=apply_ring_fill_preset_for_window,
        ),
        active_tool_name_for_window=active_tool_name_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        context_bar_page_override_for_window=context_bar_page_override_for_window,
        insert_controller_for_window=insert_controller_for_window,
        set_atom_input_for_window=set_atom_input_for_window,
    )
    context_page_state_service = MainWindowContextPageStateService(
        tool_state_service=tool_state_service,
        status_service=status_service,
        context_bar_service=context_bar_service,
        clear_context_bar_page_override_for_window=clear_context_bar_page_override_for_window,
        set_context_bar_page_override_for_window=set_context_bar_page_override_for_window,
        tool_action_for_window=tool_action_for_window,
    )
    active_canvas_ui_service = MainWindowActiveCanvasUIService(
        tool_mode_controller_for_window=tool_mode_controller_for_window,
        active_canvas_for_window=active_canvas_for_window,
        all_canvases_for_window=all_canvases_for_window,
        current_zoom_percent_for_window=current_zoom_percent_for_window,
        status_service=status_service,
        context_bar_service=context_bar_service,
        action_availability_service=action_availability_service,
        context_page_state_service=context_page_state_service,
        tab_refs_for_window=tab_references_for_window,
        preview_for_window=preview_for_window,
        atom_input_for_window=atom_input_for_window,
        tab_reactions_suspended_for_window=tab_reactions_suspended_for_window,
        set_last_canvas_tab_index_for_window=set_last_canvas_tab_index_for_window,
    )
    canvas_document_service = MainWindowCanvasDocumentService(
        active_canvas_ui=active_canvas_ui_service,
        tab_refs_for_window=tab_references_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        next_canvas_name_for_window=next_canvas_name_for_window,
        set_last_canvas_tab_index_for_window=set_last_canvas_tab_index_for_window,
    )
    document_action_service = MainWindowDocumentActionService(
        document_session_service_for_window=document_session_service_for_window,
        geometry_controller_for_window=geometry_controller_for_window,
        bond_length_px_for_window=bond_length_px_for_window,
        active_canvas_for_window=active_canvas_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        canvas_document_service=canvas_document_service,
    )
    canvas_tab_ui_service = MainWindowCanvasTabUIService(
        close_canvas_tab_for_window=document_action_service.close_canvas_tab,
    )
    tool_routing_service = MainWindowToolRoutingService(
        insert_controller_for_window=insert_controller_for_window,
        tool_mode_controller_for_window=tool_mode_controller_for_window,
        color_mutation_service_for_window=color_mutation_service_for_window,
        color_tool_for_window=color_tool_for_window,
        selected_scene_items_for_window=selected_scene_items_for_window,
        icon_factory_for_window=icon_factory_for_window,
        tool_state_service=tool_state_service,
        context_page_state_service=context_page_state_service,
    )
    tool_action_service = MainWindowToolActionService(
        tool_mode_controller_for_window=tool_mode_controller_for_window,
        tool_state_service=tool_state_service,
        context_page_state_service=context_page_state_service,
        icon_factory_for_window=icon_factory_for_window,
        status_service=status_service,
    )
    panel_service = MainWindowPanelService(
        preview_for_window=preview_for_window,
        active_canvas_for_window=active_canvas_for_window,
        export_xyz_for_window=document_action_service.export_xyz,
        apply_preview_window_assembly_for_window=apply_preview_window_assembly_for_window,
        preview_window_for_window=preview_window_for_window,
    )
    panel_toolbar_callbacks = MainWindowPanelToolbarCallbacks(
        save_canvas=document_action_service.save_canvas,
        save_canvas_as=document_action_service.save_canvas_as,
        load_canvas=lambda window: document_action_service.load_canvas(
            window, target_provider=lambda: open_new_window(window)
        ),
        export_figure=document_action_service.export_figure,
        export_mol=document_action_service.export_mol,
        open_preview_window=panel_service.open_preview_window,
        new_canvas=open_new_window,
    )
    ui_assembly_service = MainWindowUIAssemblyService(
        scene_transform_controller_for_window=scene_transform_controller_for_window,
        insert_controller_for_window=insert_controller_for_window,
        history_service_for_window=history_service_for_window,
        build_tool_actions_for_window=tool_action_service.build_tool_actions,
        panel_toolbar_callbacks=panel_toolbar_callbacks,
    )
    return MainWindowServices(
        action_availability_service=action_availability_service,
        document_action_service=document_action_service,
        tool_action_service=tool_action_service,
        tool_state_service=tool_state_service,
        context_page_state_service=context_page_state_service,
        tool_routing_service=tool_routing_service,
        text_style_service=text_style_service,
        canvas_tab_ui_service=canvas_tab_ui_service,
        canvas_document_service=canvas_document_service,
        active_canvas_ui_service=active_canvas_ui_service,
        ui_assembly_service=ui_assembly_service,
        context_bar_service=context_bar_service,
        status_service=status_service,
        panel_service=panel_service,
        history_service_for_window=history_service_for_window,
    )


__all__ = ["MainWindowServices", "build_main_window_services"]
