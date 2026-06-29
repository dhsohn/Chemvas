from __future__ import annotations

from ui.canvas_model_access import has_atoms_for
from ui.canvas_service_access import canvas_services_for
from ui.canvas_tool_settings_state import tool_settings_state_for
from ui.canvas_window_access import history_service_for_canvas
from ui.input_view_access import (
    fit_canvas_to_view_for,
    reset_zoom_for,
    set_zoom_for,
    zoom_factor_for,
    zoom_in_for,
    zoom_out_for,
)
from ui.renderer_style_access import bond_length_px_for
from ui.selection_collection_access import selected_scene_items_for
from ui.sheet_setup_access import (
    set_sheet_setup_for,
    sheet_orientation_for,
    sheet_size_for,
)


def active_canvas_for_window(window):
    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        return canvas
    raise RuntimeError("No active canvas.")


def active_canvas_or_none_for_window(window):
    return window.tab_references.active_canvas_or_none(window.runtime_state.last_canvas_tab_index)


def all_canvases_for_window(window):
    return window.tab_references.all_canvases()


def tab_reactions_suspended_for_window(window) -> bool:
    return bool(window.runtime_state.tab_reactions_suspended)


def set_tab_reactions_suspended_for_window(window, suspended: bool) -> None:
    window.runtime_state.tab_reactions_suspended = bool(suspended)


def set_last_canvas_tab_index_for_window(window, index: int) -> None:
    window.runtime_state.last_canvas_tab_index = index


def _active_canvas_services_for_window(window):
    return canvas_services_for(active_canvas_for_window(window))


def style_controller_for_window(window):
    return _active_canvas_services_for_window(window).style_controller


def tool_mode_controller_for_window(window):
    return _active_canvas_services_for_window(window).tool_mode_controller


def insert_controller_for_window(window):
    return _active_canvas_services_for_window(window).insert_controller


def color_mutation_service_for_window(window):
    return _active_canvas_services_for_window(window).canvas_color_mutation_service


def scene_transform_controller_for_window(window):
    return _active_canvas_services_for_window(window).scene_transform_controller


def document_session_service_for_window(window):
    return _active_canvas_services_for_window(window).canvas_document_session_service


def geometry_controller_for_window(window):
    return _active_canvas_services_for_window(window).geometry_controller


def history_service_for_window(window):
    return history_service_for_canvas(active_canvas_for_window(window))


def has_exportable_atoms_for_window(window) -> bool:
    canvas = active_canvas_or_none_for_window(window)
    return has_atoms_for(canvas) if canvas is not None else False


def active_tool_name_for_window(window):
    canvas = active_canvas_or_none_for_window(window)
    if canvas is None:
        return None
    active_tool = getattr(canvas_services_for(canvas).tools, "active", None)
    name = getattr(active_tool, "name", None)
    return str(name) if name else None


def current_zoom_percent_for_window(window) -> int:
    canvas = active_canvas_or_none_for_window(window)
    if canvas is None:
        return 100
    return max(1, int(round(zoom_factor_for(canvas) * 100)))


def zoom_in_for_window(window) -> int:
    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        zoom_in_for(canvas)
    return current_zoom_percent_for_window(window)


def zoom_out_for_window(window) -> int:
    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        zoom_out_for(canvas)
    return current_zoom_percent_for_window(window)


def reset_zoom_for_window(window) -> int:
    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        reset_zoom_for(canvas)
    return current_zoom_percent_for_window(window)


def fit_canvas_to_view_for_window(window) -> int:
    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        fit_canvas_to_view_for(canvas)
    return current_zoom_percent_for_window(window)


def set_zoom_percent_for_window(window, percent: float) -> int:
    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        set_zoom_for(canvas, percent / 100.0)
    return current_zoom_percent_for_window(window)


def canvas_count_for_window(window) -> int:
    return window.tab_references.canvas_count()


def active_canvas_name_for_window(window) -> str:
    return window.tab_references.active_canvas_name(active_canvas_or_none_for_window(window))


def active_canvas_index_for_window(window) -> int:
    return window.tab_references.active_canvas_index(active_canvas_or_none_for_window(window))


def context_bar_page_override_for_window(window) -> str | None:
    return window.runtime_state.context_bar_page_override


def clear_context_bar_page_override_for_window(window) -> None:
    window.runtime_state.clear_context_bar_page_override()


def set_context_bar_page_override_for_window(window, page_key: str | None) -> None:
    window.runtime_state.set_context_bar_page_override(page_key)


def bond_length_px_for_window(window) -> float:
    return bond_length_px_for(active_canvas_for_window(window))


def sheet_size_for_window(window) -> str:
    return sheet_size_for(active_canvas_for_window(window))


def sheet_orientation_for_window(window) -> str:
    return sheet_orientation_for(active_canvas_for_window(window))


def set_sheet_setup_for_window(window, size: str, orientation: str) -> None:
    set_sheet_setup_for(active_canvas_for_window(window), size, orientation)


def next_canvas_name_for_window(window, prefix: str = "Canvas") -> str:
    return window.runtime_state.next_canvas_name(prefix)


def tool_settings_for_window(window):
    return tool_settings_state_for(active_canvas_for_window(window))


def color_tool_for_window(window):
    return getattr(_active_canvas_services_for_window(window).tools, "tools", {}).get("color")


def selected_scene_items_for_window(window, *, excluded_kinds):
    return selected_scene_items_for(active_canvas_for_window(window), excluded_kinds=excluded_kinds)


__all__ = [
    "active_canvas_for_window",
    "active_canvas_or_none_for_window",
    "active_canvas_index_for_window",
    "active_canvas_name_for_window",
    "active_tool_name_for_window",
    "all_canvases_for_window",
    "bond_length_px_for_window",
    "canvas_count_for_window",
    "clear_context_bar_page_override_for_window",
    "color_mutation_service_for_window",
    "color_tool_for_window",
    "context_bar_page_override_for_window",
    "current_zoom_percent_for_window",
    "fit_canvas_to_view_for_window",
    "reset_zoom_for_window",
    "set_zoom_percent_for_window",
    "zoom_in_for_window",
    "zoom_out_for_window",
    "document_session_service_for_window",
    "geometry_controller_for_window",
    "has_exportable_atoms_for_window",
    "history_service_for_window",
    "insert_controller_for_window",
    "next_canvas_name_for_window",
    "scene_transform_controller_for_window",
    "selected_scene_items_for_window",
    "set_context_bar_page_override_for_window",
    "set_last_canvas_tab_index_for_window",
    "set_sheet_setup_for_window",
    "set_tab_reactions_suspended_for_window",
    "sheet_orientation_for_window",
    "sheet_size_for_window",
    "style_controller_for_window",
    "tab_reactions_suspended_for_window",
    "tool_mode_controller_for_window",
    "tool_settings_for_window",
]
