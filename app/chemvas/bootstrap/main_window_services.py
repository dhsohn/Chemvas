from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from chemvas.bootstrap.window_registry import open_new_window
from chemvas.ui.canvas_service_ports import note_controller_for_access
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
from chemvas.ui.main_window_context_bar_pages import MainWindowContextBarPageBuilder
from chemvas.ui.main_window_context_bar_service import MainWindowContextBarService
from chemvas.ui.main_window_context_page_state_service import (
    MainWindowContextPageStateService,
)
from chemvas.ui.main_window_document_action_service import (
    MainWindowDocumentActionService,
)
from chemvas.ui.main_window_panel_service import MainWindowPanelService
from chemvas.ui.main_window_panel_toolbar import MainWindowPanelToolbarCallbacks
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    active_canvas_index_for_window,
    active_canvas_name_for_window,
    active_canvas_or_none_for_window,
    active_tool_name_for_window,
    all_canvases_for_window,
    apply_preview_window_assembly_for_window,
    atom_input_for_window,
    bond_length_px_for_window,
    canvas_count_for_window,
    clear_context_bar_page_override_for_window,
    color_mutation_service_for_window,
    color_tool_for_window,
    context_bar_page_override_for_window,
    current_zoom_percent_for_window,
    document_session_service_for_window,
    export_xyz_button_for_window,
    fit_canvas_to_view_for_window,
    geometry_controller_for_window,
    has_exportable_atoms_for_window,
    history_service_for_window,
    icon_factory_for_window,
    insert_controller_for_window,
    next_canvas_name_for_window,
    preview_for_window,
    preview_window_for_window,
    redo_button_for_window,
    reset_zoom_for_window,
    scene_transform_controller_for_window,
    selected_scene_items_for_window,
    set_atom_input_for_window,
    set_context_bar_page_override_for_window,
    set_last_canvas_tab_index_for_window,
    set_zoom_percent_for_window,
    style_controller_for_window,
    tab_reactions_suspended_for_window,
    tab_references_for_window,
    tool_action_for_window,
    tool_actions_for_window,
    tool_mode_controller_for_window,
    tool_settings_for_window,
    undo_button_for_window,
    zoom_in_for_window,
    zoom_out_for_window,
)
from chemvas.ui.main_window_service_types import MainWindowServices
from chemvas.ui.main_window_status_service import MainWindowStatusService
from chemvas.ui.main_window_text_style_service import MainWindowTextStyleService
from chemvas.ui.main_window_tool_action_service import MainWindowToolActionService
from chemvas.ui.main_window_tool_routing_service import MainWindowToolRoutingService
from chemvas.ui.main_window_tool_state_service import MainWindowToolStateService
from chemvas.ui.main_window_ui_assembly_service import MainWindowUIAssemblyService


def build_main_window_services() -> MainWindowServices:
    # The port module still fronts legacy Qt objects. Keep that dynamic seam at
    # the composition root instead of allowing ``Any`` to leak into the typed
    # feature and shell packages.
    resolve_geometry_controller: Callable[[Any], Any] = geometry_controller_for_window
    resolve_scene_transform_controller: Callable[[Any], Any] = (
        scene_transform_controller_for_window
    )
    active_canvas_or_none = cast(
        Callable[[Any], Any | None], active_canvas_or_none_for_window
    )
    note_controller_for = cast(Callable[[Any], Any], note_controller_for_access)

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
        zoom_in_for_window=zoom_in_for_window,
        zoom_out_for_window=zoom_out_for_window,
        reset_zoom_for_window=reset_zoom_for_window,
        fit_canvas_to_view_for_window=fit_canvas_to_view_for_window,
        set_zoom_percent_for_window=set_zoom_percent_for_window,
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

    def activate_bond_style_for_window(window: Any, value: str) -> None:
        context_page_state_service.set_tool_with_status(
            window,
            "bond",
            reset_bond_style=False,
        )
        tool_state_service.set_bond_style(window, value)

    def set_bond_length_value_for_window(window: Any, value: Any) -> None:
        controller = resolve_geometry_controller(window)
        controller.set_bond_length(float(value))

    tool_routing_service: MainWindowToolRoutingService

    def apply_color_preset_for_window(window: Any, hex_value: str) -> None:
        tool_routing_service.apply_color_preset(window, hex_value)

    def apply_ring_fill_preset_for_window(window: Any, hex_value: str) -> None:
        tool_routing_service.apply_ring_fill_preset(window, hex_value)

    def rotate_selection_for_window(window: Any, angle_degrees: float) -> None:
        controller = resolve_scene_transform_controller(window)
        controller.rotate_selected_items(angle_degrees)

    def note_controller_for_window(window: Any) -> Any | None:
        canvas = active_canvas_or_none(window)
        if canvas is None:
            return None
        return note_controller_for(canvas)

    def set_note_font_family_for_window(window: Any, family: str) -> None:
        controller = note_controller_for_window(window)
        if controller is not None:
            controller.set_text_font_family(family)

    context_bar_service = MainWindowContextBarService(
        page_builder=MainWindowContextBarPageBuilder(
            insert_controller_for_window=insert_controller_for_window,
            tool_mode_controller_for_window=tool_mode_controller_for_window,
            tool_state_service=tool_state_service,
            activate_bond_style_for_window=activate_bond_style_for_window,
            set_bond_length_value_for_window=set_bond_length_value_for_window,
            bond_length_px_for_window=bond_length_px_for_window,
            apply_color_preset_for_window=apply_color_preset_for_window,
            apply_ring_fill_preset_for_window=apply_ring_fill_preset_for_window,
            rotate_selection_for_window=rotate_selection_for_window,
            note_controller_for_window=note_controller_for_window,
        ),
        active_tool_name_for_window=active_tool_name_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        context_bar_page_override_for_window=context_bar_page_override_for_window,
        set_atom_input_for_window=set_atom_input_for_window,
        bond_length_px_for_window=bond_length_px_for_window,
    )
    context_page_state_service = MainWindowContextPageStateService(
        tool_state_service=tool_state_service,
        status_service=status_service,
        context_bar_service=context_bar_service,
        clear_context_bar_page_override_for_window=clear_context_bar_page_override_for_window,
        set_context_bar_page_override_for_window=set_context_bar_page_override_for_window,
        tool_action_for_window=tool_action_for_window,
    )
    canvas_document_service: MainWindowCanvasDocumentService

    def refresh_document_chrome_for_window(window: Any) -> None:
        # Late-bound: canvas_document_service is assigned just below. Refreshes
        # the active tab's unsaved marker + the window-modified title after edits.
        canvas = active_canvas_or_none(window)
        if canvas is not None:
            canvas_document_service.refresh_tab_title(window, canvas)

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
        refresh_document_chrome_for_window=refresh_document_chrome_for_window,
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
        export_mol=lambda window: document_action_service.export_mol(
            window, selected_only=True
        ),
        open_preview_window=panel_service.open_preview_window,
        new_canvas=open_new_window,
        show_rotate_options=lambda window: context_page_state_service.show_context_page(
            window, "rotate"
        ),
        set_note_font_family=set_note_font_family_for_window,
        open_recent_path=lambda window, path: (
            document_action_service.load_canvas_from_path(
                window, path, target_provider=lambda: open_new_window(window)
            )
        ),
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
