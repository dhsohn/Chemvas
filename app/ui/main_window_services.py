from __future__ import annotations

from dataclasses import dataclass

from ui.main_window_action_availability_service import (
    MainWindowActionAvailabilityService,
)
from ui.main_window_active_canvas_ui_service import MainWindowActiveCanvasUIService
from ui.main_window_canvas_ports import (
    active_canvas_for_window,
    active_canvas_or_none_for_window,
    active_canvas_sheet_index_for_window,
    active_canvas_sheet_name_for_window,
    active_canvas_tab_index_for_window,
    active_tool_name_for_window,
    all_canvases_for_window,
    bond_length_px_for_window,
    canvas_sheet_count_for_window,
    clear_context_bar_page_override_for_window,
    color_mutation_service_for_window,
    color_tool_for_window,
    context_bar_page_override_for_window,
    current_file_path_for_window,
    current_zoom_percent_for_window,
    document_session_service_for_window,
    geometry_controller_for_window,
    has_exportable_atoms_for_window,
    history_service_for_window,
    insert_controller_for_window,
    next_canvas_sheet_name_for_window,
    repositioning_add_tab_for_window,
    reset_canvas_name_counter_for_window,
    save_active_canvas_to_file_for_window,
    scene_transform_controller_for_window,
    selected_scene_items_for_window,
    set_context_bar_page_override_for_window,
    set_current_file_path_for_window,
    set_last_canvas_tab_index_for_window,
    set_repositioning_add_tab_for_window,
    set_sheet_setup_for_window,
    set_tab_reactions_suspended_for_window,
    sheet_add_tab_for_window,
    sheet_orientation_for_window,
    sheet_size_for_window,
    style_controller_for_window,
    tab_reactions_suspended_for_window,
    tool_mode_controller_for_window,
    tool_settings_for_window,
)
from ui.main_window_canvas_sheet_service import MainWindowCanvasSheetService
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
    apply_panel_assembly_for_window,
    atom_input_for_window,
    export_xyz_button_for_window,
    icon_factory_for_window,
    panel_dock_for_window,
    preview_panel_button_for_window,
    redo_button_for_window,
    tool_action_for_window,
    tool_actions_for_window,
    undo_button_for_window,
)
from ui.main_window_workbook_document_service import MainWindowWorkbookDocumentService


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
    canvas_sheet_service: MainWindowCanvasSheetService
    active_canvas_ui_service: MainWindowActiveCanvasUIService
    workbook_document_service: MainWindowWorkbookDocumentService
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
        canvas_sheet_count_for_window=canvas_sheet_count_for_window,
        active_canvas_sheet_name_for_window=active_canvas_sheet_name_for_window,
        active_canvas_sheet_index_for_window=active_canvas_sheet_index_for_window,
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

    context_bar_service = MainWindowContextBarService(
        page_builder=MainWindowContextBarPageBuilder(
            insert_controller_for_window=insert_controller_for_window,
            tool_mode_controller_for_window=tool_mode_controller_for_window,
            tool_state_service=tool_state_service,
            activate_bond_style_for_window=activate_bond_style_for_window,
            set_bond_length_for_window=set_bond_length_for_window,
        ),
        active_tool_name_for_window=active_tool_name_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        context_bar_page_override_for_window=context_bar_page_override_for_window,
    )
    context_page_state_service = MainWindowContextPageStateService(
        tool_state_service=tool_state_service,
        status_service=status_service,
        context_bar_service=context_bar_service,
        clear_context_bar_page_override_for_window=clear_context_bar_page_override_for_window,
        set_context_bar_page_override_for_window=set_context_bar_page_override_for_window,
        tool_action_for_window=tool_action_for_window,
    )
    canvas_sheet_service: MainWindowCanvasSheetService

    def new_canvas_sheet_for_window(window):
        return canvas_sheet_service.new_canvas_sheet(window)

    active_canvas_ui_service = MainWindowActiveCanvasUIService(
        tool_mode_controller_for_window=tool_mode_controller_for_window,
        active_canvas_for_window=active_canvas_for_window,
        all_canvases_for_window=all_canvases_for_window,
        current_zoom_percent_for_window=current_zoom_percent_for_window,
        status_service=status_service,
        context_bar_service=context_bar_service,
        action_availability_service=action_availability_service,
        context_page_state_service=context_page_state_service,
        new_canvas_sheet_for_window=new_canvas_sheet_for_window,
        tab_refs_for_window=tab_references_for_window,
        preview_for_window=preview_for_window,
        atom_input_for_window=atom_input_for_window,
        sheet_add_tab_for_window=sheet_add_tab_for_window,
        tab_reactions_suspended_for_window=tab_reactions_suspended_for_window,
        set_last_canvas_tab_index_for_window=set_last_canvas_tab_index_for_window,
    )
    canvas_tab_ui_service = MainWindowCanvasTabUIService(
        active_canvas_ui=active_canvas_ui_service,
        tab_refs_for_window=tab_references_for_window,
        repositioning_add_tab_for_window=repositioning_add_tab_for_window,
        set_repositioning_add_tab_for_window=set_repositioning_add_tab_for_window,
        tab_reactions_suspended_for_window=tab_reactions_suspended_for_window,
        set_tab_reactions_suspended_for_window=set_tab_reactions_suspended_for_window,
        set_last_canvas_tab_index_for_window=set_last_canvas_tab_index_for_window,
    )
    canvas_sheet_service = MainWindowCanvasSheetService(
        tab_ui=canvas_tab_ui_service,
        active_canvas_ui=active_canvas_ui_service,
        tab_refs_for_window=tab_references_for_window,
        active_canvas_for_window=active_canvas_for_window,
        next_canvas_sheet_name_for_window=next_canvas_sheet_name_for_window,
    )
    workbook_document_service = MainWindowWorkbookDocumentService(
        active_canvas_ui=active_canvas_ui_service,
        canvas_sheet=canvas_sheet_service,
        save_active_canvas_to_file_for_window=save_active_canvas_to_file_for_window,
        tab_refs_for_window=tab_references_for_window,
        active_canvas_sheet_index_for_window=active_canvas_sheet_index_for_window,
        active_canvas_tab_index_for_window=active_canvas_tab_index_for_window,
        canvas_sheet_count_for_window=canvas_sheet_count_for_window,
        reset_canvas_name_counter_for_window=reset_canvas_name_counter_for_window,
        tab_reactions_suspended_for_window=tab_reactions_suspended_for_window,
        set_tab_reactions_suspended_for_window=set_tab_reactions_suspended_for_window,
        set_last_canvas_tab_index_for_window=set_last_canvas_tab_index_for_window,
    )
    document_action_service = MainWindowDocumentActionService(
        document_session_service_for_window=document_session_service_for_window,
        geometry_controller_for_window=geometry_controller_for_window,
        bond_length_px_for_window=bond_length_px_for_window,
        sheet_size_for_window=sheet_size_for_window,
        sheet_orientation_for_window=sheet_orientation_for_window,
        set_sheet_setup_for_window=set_sheet_setup_for_window,
        current_file_path_for_window=current_file_path_for_window,
        set_current_file_path_for_window=set_current_file_path_for_window,
        workbook_document_service=workbook_document_service,
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
        apply_panel_assembly_for_window=apply_panel_assembly_for_window,
        panel_dock_for_window=panel_dock_for_window,
        preview_panel_button_for_window=preview_panel_button_for_window,
    )
    panel_toolbar_callbacks = MainWindowPanelToolbarCallbacks(
        save_canvas=document_action_service.save_canvas,
        save_canvas_as=document_action_service.save_canvas_as,
        load_canvas=document_action_service.load_canvas,
        export_figure=document_action_service.export_figure,
        export_xyz=document_action_service.export_xyz,
        toggle_preview_panel=panel_service.toggle_preview_panel,
        setup_sheet=document_action_service.setup_sheet,
        populate_palette_menu=tool_routing_service.populate_palette_menu,
        apply_color_preset=tool_routing_service.apply_color_preset,
        apply_ring_fill_preset=tool_routing_service.apply_ring_fill_preset,
        set_bond_length=document_action_service.set_bond_length,
    )
    ui_assembly_service = MainWindowUIAssemblyService(
        scene_transform_controller_for_window=scene_transform_controller_for_window,
        insert_controller_for_window=insert_controller_for_window,
        tool_mode_controller_for_window=tool_mode_controller_for_window,
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
        canvas_sheet_service=canvas_sheet_service,
        active_canvas_ui_service=active_canvas_ui_service,
        workbook_document_service=workbook_document_service,
        ui_assembly_service=ui_assembly_service,
        context_bar_service=context_bar_service,
        status_service=status_service,
        panel_service=panel_service,
        history_service_for_window=history_service_for_window,
    )


__all__ = ["MainWindowServices", "build_main_window_services"]
