from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.ui.main_window_service_types import MainWindowServices
    from chemvas.ui.main_window_tab_references import MainWindowTabReferences
    from chemvas.ui.main_window_ui_references import MainWindowUiReferences
    from chemvas.ui.preview_3d import Preview3D


def services_for_window(window) -> MainWindowServices:
    return window._services


def preview_for_window(window) -> Preview3D:
    return window._preview_3d


def tab_references_for_window(window) -> MainWindowTabReferences:
    return window.tab_references


def ui_references_for_window(window) -> MainWindowUiReferences:
    return window.ui_references


def icon_factory_for_window(window):
    return ui_references_for_window(window).require_icon_factory()


def atom_input_for_window(window):
    return ui_references_for_window(window).atom_input


def set_atom_input_for_window(window, atom_input) -> None:
    ui_references_for_window(window).set_atom_input(atom_input)


def tool_actions_for_window(window):
    return ui_references_for_window(window).tool_actions


def tool_action_for_window(window, action_key: str):
    return ui_references_for_window(window).tool_action_for_key(action_key)


def preview_panel_button_for_window(window):
    return ui_references_for_window(window).preview_panel_button


def preview_window_for_window(window):
    return ui_references_for_window(window).preview_window


def apply_preview_window_assembly_for_window(window, assembly) -> None:
    ui_references_for_window(window).apply_preview_window_assembly(assembly)


def undo_button_for_window(window):
    return ui_references_for_window(window).undo_button


def redo_button_for_window(window):
    return ui_references_for_window(window).redo_button


def export_xyz_button_for_window(window):
    return ui_references_for_window(window).export_xyz_button


def active_canvas_for_window(window):
    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        return canvas
    raise RuntimeError("No active canvas.")


def active_canvas_or_none_for_window(window):
    return tab_references_for_window(window).active_canvas_or_none(
        window.runtime_state.last_canvas_tab_index
    )


def all_canvases_for_window(window):
    return tab_references_for_window(window).all_canvases()


def tab_reactions_suspended_for_window(window) -> bool:
    return bool(window.runtime_state.tab_reactions_suspended)


def set_tab_reactions_suspended_for_window(window, suspended: bool) -> None:
    window.runtime_state.tab_reactions_suspended = bool(suspended)


def set_last_canvas_tab_index_for_window(window, index: int) -> None:
    window.runtime_state.last_canvas_tab_index = index


def _active_canvas_services_for_window(window):
    from chemvas.ui.canvas_service_access import canvas_services_for

    return canvas_services_for(active_canvas_for_window(window))


def style_controller_for_window(window):
    return _active_canvas_services_for_window(window).scene_operations.style_controller


def tool_mode_controller_for_window(window):
    return _active_canvas_services_for_window(window).input.tool_mode_controller


def insert_controller_for_window(window):
    return _active_canvas_services_for_window(window).structure.insert_controller


def color_mutation_service_for_window(window):
    return _active_canvas_services_for_window(
        window
    ).scene_operations.canvas_color_mutation_service


def scene_transform_controller_for_window(window):
    return _active_canvas_services_for_window(
        window
    ).scene_operations.scene_transform_controller


def document_session_service_for_window(window):
    return _active_canvas_services_for_window(
        window
    ).document.canvas_document_session_service


def geometry_controller_for_window(window):
    return _active_canvas_services_for_window(window).scene_view.geometry_controller


def history_service_for_window(window):
    from chemvas.ui.canvas_window_access import history_service_for_canvas

    return history_service_for_canvas(active_canvas_for_window(window))


def has_exportable_atoms_for_window(window) -> bool:
    from chemvas.ui.canvas_model_access import has_atoms_for

    canvas = active_canvas_or_none_for_window(window)
    return has_atoms_for(canvas) if canvas is not None else False


def active_tool_name_for_window(window):
    from chemvas.ui.canvas_service_access import canvas_services_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is None:
        return None
    active_tool = getattr(canvas_services_for(canvas).tool_controller, "active", None)
    name = getattr(active_tool, "name", None)
    return str(name) if name else None


def current_zoom_percent_for_window(window) -> int:
    from chemvas.ui.input_view_access import zoom_factor_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is None:
        return 100
    return max(1, round(zoom_factor_for(canvas) * 100))


def zoom_in_for_window(window) -> int:
    from chemvas.ui.input_view_access import zoom_in_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        zoom_in_for(canvas)
    return current_zoom_percent_for_window(window)


def zoom_out_for_window(window) -> int:
    from chemvas.ui.input_view_access import zoom_out_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        zoom_out_for(canvas)
    return current_zoom_percent_for_window(window)


def reset_zoom_for_window(window) -> int:
    from chemvas.ui.input_view_access import reset_zoom_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        reset_zoom_for(canvas)
    return current_zoom_percent_for_window(window)


def fit_canvas_to_view_for_window(window) -> int:
    from chemvas.ui.input_view_access import fit_canvas_to_view_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        fit_canvas_to_view_for(canvas)
    return current_zoom_percent_for_window(window)


def set_zoom_percent_for_window(window, percent: float) -> int:
    from chemvas.ui.input_view_access import set_zoom_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        set_zoom_for(canvas, percent / 100.0)
    return current_zoom_percent_for_window(window)


def canvas_count_for_window(window) -> int:
    return tab_references_for_window(window).canvas_count()


def active_canvas_name_for_window(window) -> str:
    return tab_references_for_window(window).active_canvas_name(
        active_canvas_or_none_for_window(window)
    )


def active_canvas_index_for_window(window) -> int:
    return tab_references_for_window(window).active_canvas_index(
        active_canvas_or_none_for_window(window)
    )


def context_bar_page_override_for_window(window) -> str | None:
    return window.runtime_state.context_bar_page_override


def clear_context_bar_page_override_for_window(window) -> None:
    window.runtime_state.clear_context_bar_page_override()


def set_context_bar_page_override_for_window(window, page_key: str | None) -> None:
    window.runtime_state.set_context_bar_page_override(page_key)


def bond_length_px_for_window(window) -> float:
    from chemvas.ui.renderer_style_access import bond_length_px_for

    return bond_length_px_for(active_canvas_for_window(window))


def sheet_size_for_window(window) -> str:
    from chemvas.ui.sheet_setup_access import sheet_size_for

    return sheet_size_for(active_canvas_for_window(window))


def sheet_orientation_for_window(window) -> str:
    from chemvas.ui.sheet_setup_access import sheet_orientation_for

    return sheet_orientation_for(active_canvas_for_window(window))


def set_sheet_setup_for_window(window, size: str, orientation: str) -> None:
    from chemvas.ui.sheet_setup_access import set_sheet_setup_for

    set_sheet_setup_for(active_canvas_for_window(window), size, orientation)


def next_canvas_name_for_window(window, prefix: str = "Canvas") -> str:
    return window.runtime_state.next_canvas_name(prefix)


def tool_settings_for_window(window):
    from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for

    return tool_settings_state_for(active_canvas_for_window(window))


def color_tool_for_window(window):
    return getattr(
        _active_canvas_services_for_window(window).tool_controller, "tools", {}
    ).get("color")


def selected_scene_items_for_window(window, *, excluded_kinds):
    from chemvas.ui.selection_collection_access import selected_scene_items_for

    return selected_scene_items_for(
        active_canvas_for_window(window), excluded_kinds=excluded_kinds
    )


__all__ = [
    "active_canvas_for_window",
    "active_canvas_index_for_window",
    "active_canvas_name_for_window",
    "active_canvas_or_none_for_window",
    "active_tool_name_for_window",
    "all_canvases_for_window",
    "apply_preview_window_assembly_for_window",
    "atom_input_for_window",
    "bond_length_px_for_window",
    "canvas_count_for_window",
    "clear_context_bar_page_override_for_window",
    "color_mutation_service_for_window",
    "color_tool_for_window",
    "context_bar_page_override_for_window",
    "current_zoom_percent_for_window",
    "document_session_service_for_window",
    "export_xyz_button_for_window",
    "fit_canvas_to_view_for_window",
    "geometry_controller_for_window",
    "has_exportable_atoms_for_window",
    "history_service_for_window",
    "icon_factory_for_window",
    "insert_controller_for_window",
    "next_canvas_name_for_window",
    "preview_for_window",
    "preview_panel_button_for_window",
    "preview_window_for_window",
    "redo_button_for_window",
    "reset_zoom_for_window",
    "scene_transform_controller_for_window",
    "selected_scene_items_for_window",
    "services_for_window",
    "set_atom_input_for_window",
    "set_context_bar_page_override_for_window",
    "set_last_canvas_tab_index_for_window",
    "set_sheet_setup_for_window",
    "set_tab_reactions_suspended_for_window",
    "set_zoom_percent_for_window",
    "sheet_orientation_for_window",
    "sheet_size_for_window",
    "style_controller_for_window",
    "tab_reactions_suspended_for_window",
    "tab_references_for_window",
    "tool_action_for_window",
    "tool_actions_for_window",
    "tool_mode_controller_for_window",
    "tool_settings_for_window",
    "ui_references_for_window",
    "undo_button_for_window",
    "zoom_in_for_window",
    "zoom_out_for_window",
]
