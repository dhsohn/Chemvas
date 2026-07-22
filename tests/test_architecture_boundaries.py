from __future__ import annotations

"""Architecture boundary rules.

Every test here enforces a *rule* — a forbidden access pattern, a removed
surface that must stay removed, or a dependency contract — expressed as a
regex/AST check over production sources. Tests must NOT assert that a specific
implementation phrasing exists ("this exact call appears in this file"): that
freezes wording instead of protecting structure, and innocent refactors start
failing the suite. If a new rule cannot be written as a pattern ban or a
dependency contract, it probably belongs in a unit test, not here.
"""

import ast
import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

CANVAS_STATE_PROPERTIES = (
    "hover_items",
    "hover_atom_id",
    "hover_bond_id",
    "atom_items",
    "atom_dots",
    "atom_coords_3d",
    "bond_items",
    "last_smiles_input",
    "atom_symbol",
    "active_bond_style",
    "active_bond_order",
    "snap_angle_step",
    "mark_kind",
    "active_arrow_type",
    "active_bracket_type",
    "active_orbital_type",
    "orbital_phase_enabled",
    "arrow_line_width",
    "arrow_head_scale",
    "text_font_family",
    "text_font_size",
    "text_font_weight",
    "text_italic",
    "text_color",
    "text_alignment",
    "text_line_spacing",
    "note_box_enabled",
    "note_box_color",
    "note_box_alpha",
    "note_border_enabled",
    "note_border_color",
    "note_border_width",
    "note_padding",
    "selected_notes",
    "note_items",
    "mark_items",
    "ring_items",
    "arrow_items",
    "ts_bracket_items",
    "orbital_items",
    "selection_outlines",
)

REMOVED_CANVAS_VIEW_SETTING_PROPERTIES = (
    "atom_symbol",
    "active_bond_style",
    "active_bond_order",
    "snap_angle_step",
    "mark_kind",
    "active_arrow_type",
    "active_bracket_type",
    "active_orbital_type",
    "orbital_phase_enabled",
    "arrow_line_width",
    "arrow_head_scale",
    "text_font_family",
    "text_font_size",
    "text_font_weight",
    "text_italic",
    "text_color",
    "text_alignment",
    "text_line_spacing",
    "note_box_enabled",
    "note_box_color",
    "note_box_alpha",
    "note_border_enabled",
    "note_border_color",
    "note_border_width",
    "note_padding",
)

REMOVED_CANVAS_VIEW_HOVER_PROPERTIES = (
    "hover_items",
    "hover_atom_id",
    "hover_bond_id",
)

REMOVED_CANVAS_VIEW_SELECTION_PROPERTIES = ("selection_outlines",)

REMOVED_CANVAS_VIEW_SMILES_PROPERTIES = ("last_smiles_input",)

REMOVED_CANVAS_VIEW_ATOM_COORDS_PROPERTIES = ("atom_coords_3d",)

REMOVED_CANVAS_VIEW_ATOM_GRAPHICS_PROPERTIES = (
    "atom_items",
    "atom_dots",
)

REMOVED_CANVAS_VIEW_BOND_GRAPHICS_PROPERTIES = ("bond_items",)

REMOVED_CANVAS_VIEW_HIT_SELECTION_WRAPPERS = (
    "scene_pos_from_event",
    "item_at_scene_pos",
    "item_at_event",
    "find_atom_near",
    "bond_id_from_event",
    "toggle_item_selection",
    "preferred_structure_hit_at_scene_pos",
    "preferred_structure_item_at_scene_pos",
    "selection_hit_test",
    "select_structure_for_item",
    "_nearest_atom_hit",
    "_nearest_bond_hit",
    "_selection_targets_for_item",
    "_selection_rects_for_snapshot",
    "_grid_cell_size",
    "_cell_coords",
    "_ensure_spatial_index",
    "_rebuild_spatial_index",
)


def _app_python_files() -> list[Path]:
    return sorted(APP_ROOT.rglob("*.py"))


def _matching_lines(pattern: re.Pattern[str], paths: list[Path]) -> list[str]:
    matches: list[str] = []
    for path in paths:
        for line_no, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line):
                matches.append(
                    f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}: {line.strip()}"
                )
    return matches


def _canvas_view_state_property_assignments(
    property_names: tuple[str, ...],
) -> list[str]:
    properties = APP_ROOT / "chemvas" / "ui" / "canvas_view_state_properties.py"
    if not properties.exists():
        return []
    names_pattern = "|".join(re.escape(name) for name in property_names)
    pattern = re.compile(rf"^\s+(?:{names_pattern})\s*=")
    return _matching_lines(pattern, [properties])


def test_production_code_does_not_reach_into_canvas_private_members() -> None:
    pattern = re.compile(
        r"\b(?:canvas|self\.canvas)\._"
        r"|vars\(\s*canvas\s*\)\[\s*\"_[A-Za-z]"
        r"|getattr\(\s*canvas\s*,\s*\"_[A-Za-z]"
        r"|setattr\(\s*canvas\s*,\s*\"_[A-Za-z]"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_production_code_uses_canvas_state_accessors_instead_of_canvas_state_properties() -> (
    None
):
    property_names = "|".join(re.escape(name) for name in CANVAS_STATE_PROPERTIES)
    pattern = re.compile(rf"\b(?:canvas|self\.canvas)\.(?:{property_names})\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_canvas_view_keeps_hit_testing_and_selection_wrappers_removed() -> None:
    canvas_view = APP_ROOT / "chemvas" / "ui" / "canvas_view.py"
    method_names = "|".join(
        re.escape(name) for name in REMOVED_CANVAS_VIEW_HIT_SELECTION_WRAPPERS
    )
    pattern = re.compile(rf"^\s+def (?:{method_names})\b")

    assert _matching_lines(pattern, [canvas_view]) == []


def test_canvas_view_event_overrides_route_to_attached_service_ports() -> None:
    canvas_view = APP_ROOT / "chemvas" / "ui" / "canvas_view.py"
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|\bfrom ui\.canvas_service_access\b"
        r"|\bself\.services\."
        r"|getattr\(\s*self\s*,\s*\"services\""
        r"|\binput_controller_for_view\b"
        r"|\bpointer_controller_for_view\b"
    )

    assert _matching_lines(pattern, [canvas_view]) == []


def test_canvas_view_setting_state_properties_stay_removed() -> None:
    assert (
        _canvas_view_state_property_assignments(REMOVED_CANVAS_VIEW_SETTING_PROPERTIES)
        == []
    )


def test_canvas_view_hover_state_properties_stay_removed() -> None:
    assert (
        _canvas_view_state_property_assignments(REMOVED_CANVAS_VIEW_HOVER_PROPERTIES)
        == []
    )


def test_canvas_view_selection_state_properties_stay_removed() -> None:
    assert (
        _canvas_view_state_property_assignments(
            REMOVED_CANVAS_VIEW_SELECTION_PROPERTIES
        )
        == []
    )


def test_canvas_view_smiles_state_properties_stay_removed() -> None:
    assert (
        _canvas_view_state_property_assignments(REMOVED_CANVAS_VIEW_SMILES_PROPERTIES)
        == []
    )


def test_canvas_view_atom_coords_state_properties_stay_removed() -> None:
    assert (
        _canvas_view_state_property_assignments(
            REMOVED_CANVAS_VIEW_ATOM_COORDS_PROPERTIES
        )
        == []
    )


def test_canvas_view_atom_graphics_state_properties_stay_removed() -> None:
    assert (
        _canvas_view_state_property_assignments(
            REMOVED_CANVAS_VIEW_ATOM_GRAPHICS_PROPERTIES
        )
        == []
    )


def test_canvas_view_bond_graphics_state_properties_stay_removed() -> None:
    assert (
        _canvas_view_state_property_assignments(
            REMOVED_CANVAS_VIEW_BOND_GRAPHICS_PROPERTIES
        )
        == []
    )


def test_canvas_view_state_properties_mixin_removed_from_app_code() -> None:
    assert not (
        APP_ROOT / "chemvas" / "ui" / "canvas_view_state_properties.py"
    ).exists()

    pattern = re.compile(
        r"\b(?:CanvasViewStateProperties|canvas_view_state_properties)\b"
    )
    assert _matching_lines(pattern, _app_python_files()) == []


def test_scene_ops_controller_facade_removed_from_app_code() -> None:
    scene_ops_controller = APP_ROOT / "chemvas" / "ui" / "scene_ops_controller.py"
    pattern = re.compile(
        r"\bscene_ops_controller\b"
        r"|\bSceneOpsController\b"
        r"|from ui\.scene_ops_controller\b"
    )

    assert not scene_ops_controller.exists()
    assert _matching_lines(pattern, _app_python_files()) == []


def test_main_window_code_uses_canvas_service_accessor_instead_of_canvas_services_chain() -> (
    None
):
    paths = sorted((APP_ROOT / "chemvas" / "ui").glob("main_window*.py"))
    pattern = re.compile(r"\b(?:window|self\.window)\.canvas\.services\.")

    assert _matching_lines(pattern, paths) == []


def test_main_window_delegates_canvas_tab_setup_to_helper_module() -> None:
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text()
    setup_source = (
        APP_ROOT / "chemvas" / "ui" / "main_window_tab_setup.py"
    ).read_text()

    assert "class SheetTabBar" not in source
    assert "QTabBar" not in source
    assert "QTabWidget()" not in source
    assert "window._" not in setup_source


def test_main_window_bootstrap_uses_runtime_services_without_window_service_wrappers() -> (
    None
):
    bootstrap = APP_ROOT / "chemvas" / "bootstrap" / "main_window_runtime.py"
    source = bootstrap.read_text()
    removed_wrappers = (
        "window.add_canvas(",
        "window.update_action_availability()",
        "window.bind_active_canvas()",
        "window.on_canvas_tab_moved",
        "window.on_canvas_tab_changed",
        "window.close_canvas_tab",
    )

    assert "runtime.preview_3d.refresh_from_canvas(" not in source
    assert "window.services" not in source
    assert "window.preview_3d" not in source
    assert re.search(r"\bwindow\.canvas\b", source) is None
    for wrapper_call in removed_wrappers:
        assert wrapper_call not in source


def test_main_window_keeps_action_availability_surface_off_window() -> None:
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text()
    tree = ast.parse(source)
    main_window_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
    )
    method_names = {
        node.name
        for node in main_window_class.body
        if isinstance(node, ast.FunctionDef)
    }

    assert "update_action_availability" not in method_names
    assert "self.services.action_availability_service" not in source
    assert "has_atoms_for" not in source
    assert "can_undo = " not in source
    assert "can_redo = " not in source
    assert "can_export = " not in source


def test_main_window_keeps_removed_service_surfaces_off_window() -> None:
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text()
    tree = ast.parse(source)
    method_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    removed_service_surface = {
        "sync_tool_actions_from_canvas",
        "set_tool_with_status",
        "show_context_page",
        "set_bond_style",
        "set_arrow_type",
        "set_orbital_type",
        "set_orbital_phase",
        "set_arrow_preset",
        "set_text_color",
        "set_text_align",
        "set_note_box_color",
        "set_note_border_color",
        "set_text_preset",
        "set_bond_length",
        "setup_sheet",
        "activate_bond_style_tool",
        "populate_template_menu",
        "populate_arrow_menu",
        "populate_palette_menu",
        "activate_arrow_type_from_menu",
        "activate_arrow_preset_from_menu",
        "template_entries",
        "acs_color_palette",
        "apply_color_preset",
        "apply_ring_fill_preset",
        "show_error_message",
        "refresh_status_context",
        "update_zoom_label",
        "has_zoom_label",
        "status_context_texts",
        "zoom_status_tip",
        "ensure_add_sheet_tab",
        "keep_add_tab_last",
        "on_canvas_tab_moved",
        "can_delete_canvas_sheet",
        "show_canvas_tab_context_menu",
        "delete_canvas_sheet",
        "bind_active_canvas",
        "handle_selection_info",
        "refresh_active_canvas_ui",
        "on_canvas_tab_changed",
        "create_canvas",
        "add_canvas_sheet",
        "open_result_canvas_sheet",
        "new_canvas_sheet",
        "toggle_preview_panel",
        "workbook_document_service",
        "clear_canvas_sheets",
        "workbook_state",
        "restore_single_sheet_document",
        "restore_workbook_document",
        "save_document_state",
        "normalize_xyz_export_path",
        "save_canvas",
        "save_canvas_as",
        "export_xyz",
        "export_figure",
        "load_canvas",
        "show_status_message",
    }

    assert method_names.isdisjoint(removed_service_surface)
    assert not any(
        f"self.services.{service_name}" in source
        for service_name in (
            "context_page_state_service",
            "tool_state_service",
            "text_style_service",
            "tool_action_service",
            "tool_routing_service",
            "status_service",
            "canvas_tab_ui_service",
            "active_canvas_ui_service",
            "canvas_sheet_service",
            "panel_service",
            "workbook_document_service",
            "document_action_service",
        )
    )


def test_main_window_delegates_runtime_state_to_state_object() -> None:
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text()
    tree = ast.parse(source)

    private_state_attrs = {
        "_current_file_path",
        "_context_bar_page_override",
        "_canvas_name_counter",
        "_result_sheet_counter",
        "_last_canvas_tab_index",
        "_suspend_canvas_tab_reactions",
        "_repositioning_add_tab",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if not isinstance(node.value, ast.Name) or node.value.id != "self":
            continue
        assert node.attr not in private_state_attrs

    removed_state_forwarders = {
        "context_bar_page_override",
        "current_file_path",
        "last_canvas_tab_index",
        "next_canvas_sheet_name",
        "next_result_canvas_name",
        "repositioning_add_tab",
        "reset_canvas_name_counter",
        "tab_reactions_suspended",
    }
    method_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert method_names.isdisjoint(removed_state_forwarders)


def test_main_window_delegates_toolbar_ui_references_to_reference_object() -> None:
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text()
    tree = ast.parse(source)

    private_ui_attrs = {
        "_atom_input",
        "_load_action",
        "_export_xyz_button",
        "_preview_panel_button",
        "_undo_button",
        "_redo_button",
        "_preview_window",
        "_tool_actions",
        "_icon_factory",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if not isinstance(node.value, ast.Name) or node.value.id != "self":
            continue
        assert node.attr not in private_ui_attrs

    removed_ui_forwarders = {
        "atom_input",
        "preview_panel_button",
        "export_xyz_button",
        "undo_button",
        "redo_button",
        "preview_window",
        "tool_actions",
        "icon_factory",
    }
    main_window_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
    )
    method_names = {
        node.name
        for node in main_window_class.body
        if isinstance(node, ast.FunctionDef)
    }
    assert method_names.isdisjoint(removed_ui_forwarders)


def test_main_window_delegates_canvas_tab_references_to_reference_object() -> None:
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text()
    bootstrap_source = (
        APP_ROOT / "chemvas" / "bootstrap" / "main_window_runtime.py"
    ).read_text()
    tree = ast.parse(source)

    assert "window.canvas_tabs" not in bootstrap_source
    private_tab_attrs = {
        "_sheet_add_tab",
        "_sheet_tab_bar",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if not isinstance(node.value, ast.Name) or node.value.id != "self":
            continue
        assert node.attr not in private_tab_attrs

    removed_tab_forwarders = {
        "canvas",
        "active_canvas_or_none",
        "canvas_tab_entries",
        "all_canvases",
        "active_canvas_tab_index",
        "active_canvas_index",
        "canvas_count",
        "active_canvas_name",
    }
    method_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert method_names.isdisjoint(removed_tab_forwarders)
    assert "for index in range(self.canvas_tabs.count())" not in source
    assert "self.canvas_tabs.currentWidget()" not in source


def test_main_window_does_not_wrap_tool_action_construction() -> None:
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text()
    tree = ast.parse(source)
    method_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    assert "new_tool_action" not in method_names
    assert "build_tool_actions" not in method_names
    assert "QActionGroup" not in source


def test_main_window_context_page_state_service_uses_injected_services_and_public_window_surface() -> (
    None
):
    service = APP_ROOT / "chemvas" / "ui" / "main_window_context_page_state_service.py"
    main_window = APP_ROOT / "chemvas" / "shell" / "main_window.py"
    main_window_source = main_window.read_text()
    tree = ast.parse(main_window_source)
    pattern = re.compile(
        r"\bwindow\._"
        r"|\bwindow\.services\b"
        r"|\bwindow\.clear_context_bar_page_override\("
        r"|\bwindow\.set_context_bar_page_override\("
        r"|\bwindow\.tool_action_for_key\("
        r"|(?:tool_state_service|status_service|context_bar_service)=None"
    )

    method_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert {
        "clear_context_bar_page_override",
        "set_context_bar_page_override",
        "tool_action_for_key",
    }.isdisjoint(method_names)
    assert _matching_lines(pattern, [service]) == []


def test_main_window_ports_use_services_bundle_accessor_without_string_lookup() -> None:
    path = APP_ROOT / "chemvas" / "ui" / "main_window_ports.py"
    pattern = re.compile(
        r"\bcanvas_service_for\b|canvas_service_for\(|\bwindow\.canvas\b"
    )

    assert _matching_lines(pattern, [path]) == []


def test_main_window_ports_keep_window_accessors_consolidated() -> None:
    old_port_modules = (
        "main_window_canvas_ports.py",
        "main_window_service_ports.py",
        "main_window_preview_ports.py",
        "main_window_tab_ports.py",
        "main_window_ui_ports.py",
    )

    for module_name in old_port_modules:
        assert not (APP_ROOT / "chemvas" / "ui" / module_name).exists()
        assert module_name.removesuffix(".py") not in "\n".join(
            path.read_text() for path in _app_python_files()
        )


def test_canvas_view_ports_use_canvas_services_accessor_without_direct_services_lookup() -> (
    None
):
    path = APP_ROOT / "chemvas" / "ui" / "canvas_view_ports.py"
    forbidden = re.compile(
        r"getattr\(\s*canvas\s*,\s*\"services\"|\bcanvas\.services\b"
    )

    assert _matching_lines(forbidden, [path]) == []


def test_production_code_does_not_depend_on_main_window_canvas_facade_outside_main_window() -> (
    None
):
    pattern = re.compile(r"\bwindow\.canvas\b")
    paths = [path for path in _app_python_files() if path.name != "main_window.py"]

    assert _matching_lines(pattern, paths) == []


def test_production_code_does_not_depend_on_main_window_canvas_tabs_public_attr() -> (
    None
):
    pattern = re.compile(r"\bwindow\.canvas_tabs\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_production_code_uses_main_window_service_port_instead_of_public_services_attr() -> (
    None
):
    port = APP_ROOT / "chemvas" / "ui" / "main_window_ports.py"
    public_attr_pattern = re.compile(r"\bwindow\.services\b")
    private_attr_pattern = re.compile(r"\._services\b")
    storage_owner = APP_ROOT / "chemvas" / "shell" / "main_window.py"
    paths = [path for path in _app_python_files() if path not in {port, storage_owner}]

    assert _matching_lines(public_attr_pattern, _app_python_files()) == []
    assert _matching_lines(private_attr_pattern, paths) == []


def test_production_code_uses_main_window_preview_port_instead_of_public_preview_attr() -> (
    None
):
    port = APP_ROOT / "chemvas" / "ui" / "main_window_ports.py"
    public_attr_pattern = re.compile(r"\bwindow\.preview_3d\b")
    private_attr_pattern = re.compile(r"\._preview_3d\b")
    storage_owner = APP_ROOT / "chemvas" / "shell" / "main_window.py"
    paths = [path for path in _app_python_files() if path not in {port, storage_owner}]

    assert _matching_lines(public_attr_pattern, _app_python_files()) == []
    assert _matching_lines(private_attr_pattern, paths) == []


def test_production_code_uses_panel_reference_ports_instead_of_public_panel_attrs() -> (
    None
):
    pattern = re.compile(r"\bwindow\.panel_(?:splitter|dock)\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_main_window_services_delegates_canvas_port_lookup_to_ports_module() -> None:
    path = APP_ROOT / "chemvas" / "bootstrap" / "main_window_services.py"
    pattern = re.compile(
        r"\bcanvas_services_for\b"
        r"|\btool_settings_state_for\b"
        r"|\bhistory_service_for_canvas\b"
        r"|\bselected_scene_items_for\b"
    )

    assert _matching_lines(pattern, [path]) == []


def test_main_window_canvas_document_service_uses_injected_tab_collaborators() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_canvas_document_service.py"
    source = service.read_text()
    pattern = re.compile(
        r"\bwindow\.plus_tab_index\("
        r"|\bwindow\.canvas_tabs\b"
        r"|\bwindow\.active_canvas_or_none\("
        r"|\bwindow\.next_canvas_name\("
        r"|(?:tab_refs_for_window|active_canvas_or_none_for_window)=None"
    )

    assert "window.bind_active_canvas()" not in source
    assert _matching_lines(pattern, [service]) == []


def test_main_window_canvas_tab_ui_service_uses_injected_close_port() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_canvas_tab_ui_service.py"
    source = service.read_text()
    pattern = re.compile(
        r"\bwindow\.plus_tab_index\("
        r"|\bwindow\.recreate_sheet_add_tab\("
        r"|\bwindow\.set_sheet_add_tab_index\("
        r"|\bwindow\.move_sheet_tab\("
        r"|\bwindow\.sheet_tab_at\("
        r"|\bwindow\.sheet_tab_global_pos\("
        r"|\bwindow\.canvas_sheet_count\("
    )
    tree = ast.parse(source)
    service_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "MainWindowCanvasTabUIService"
    )
    init_method = next(
        node
        for node in service_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    init_arg_names = {arg.arg for arg in init_method.args.kwonlyargs}

    assert init_arg_names == {"close_canvas_tab_for_window"}
    assert "window.refresh_active_canvas_ui()" not in source
    assert "window.add_canvas_sheet_from_service()" not in source
    assert _matching_lines(pattern, [service]) == []


def test_main_window_text_style_service_uses_injected_style_controller_port() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_text_style_service.py"
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|\bwindow\.canvas\b"
        r"|style_controller=None"
    )

    assert _matching_lines(pattern, [service]) == []


def test_main_window_tool_state_service_uses_injected_tool_mode_port() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_tool_state_service.py"
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|\bwindow\.canvas\b"
        r"|\bwindow\.tool_actions\b"
        r"|\bwindow\.refresh_status_context\("
        r"|\bwindow\.show_status_message\("
        r"|tool_mode_controller=None"
        r"|status_service=None"
    )

    assert _matching_lines(pattern, [service]) == []


def test_main_window_tool_action_service_uses_injected_tool_mode_port() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_tool_action_service.py"
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|\bwindow\.canvas\b"
        r"|\bwindow\.icon_factory\b"
        r"|\bwindow\.set_tool_with_status\("
        r"|\bwindow\.set_bond_style\("
        r"|\bwindow\.show_context_page\("
        r"|\bwindow\.refresh_status_context\("
        r"|tool_mode_controller=None"
    )

    assert _matching_lines(pattern, [service]) == []


def test_main_window_tool_routing_service_uses_injected_canvas_ports() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_tool_routing_service.py"
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|\btool_for_name_for\b"
        r"|\bselected_scene_items_for\b"
        r"|\bwindow\.canvas\b"
        r"|\bwindow\.icon_factory\b"
        r"|\bwindow\.activate_arrow_type_from_menu\("
        r"|\bwindow\.activate_arrow_preset_from_menu\("
        r"|\bwindow\.set_tool_with_status\("
        r"|\bwindow\.set_arrow_type\("
        r"|\bwindow\.set_arrow_preset\("
        r"|(?:insert_controller|tool_mode_controller|color_mutation_service)=None"
    )

    assert _matching_lines(pattern, [service]) == []


def test_main_window_context_bar_pages_use_injected_canvas_ports() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "main_window_context_bar_page_factories.py",
        APP_ROOT / "chemvas" / "ui" / "main_window_context_bar_pages.py",
    ]
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|\bwindow\.canvas\b"
        r"|\bwindow\.icon_factory\b"
        r"|\bwindow\.activate_bond_style_tool\("
        r"|\bwindow\.set_bond_length\("
        r"|\bwindow\.set_arrow_type\("
        r"|\bwindow\.set_arrow_preset\("
        r"|(?:insert_controller|tool_mode_controller)=None"
    )

    assert _matching_lines(pattern, paths) == []


def test_main_window_status_and_context_bar_use_active_tool_port() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "main_window_status_service.py",
        APP_ROOT / "chemvas" / "ui" / "main_window_context_bar_service.py",
    ]
    pattern = re.compile(
        r"\bcanvas\.services\.tools\b"
        r"|\bwindow\.canvas\.services\b"
        r"|\bcanvas_services_for\b"
        r"|\bwindow\.current_zoom_percent\("
    )
    window_helper_pattern = re.compile(
        r"\bwindow\.active_canvas_or_none\("
        r"|\bwindow\.canvas_count\("
        r"|\bwindow\.active_canvas_name\("
        r"|\bwindow\.active_canvas_index\("
        r"|\bwindow\.context_bar_page_override\b"
    )

    assert _matching_lines(pattern, paths) == []
    assert _matching_lines(window_helper_pattern, paths) == []


def test_main_window_active_canvas_ui_service_uses_injected_collaborators() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_active_canvas_ui_service.py"
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|canvas_service_for\([^,\n]+,\s*\"tool_mode_controller\""
        r"|\bwindow\.canvas\b"
        r"|\bwindow\.sync_tool_actions_from_canvas\(\)"
        r"|selection_info_callback=window\.handle_selection_info"
        r"|tool_change_callback=window\.sync_tool_actions_from_canvas"
        r"|zoom_callback=window\.update_zoom_label"
        r"|history_change_callback=window\.update_action_availability"
        r"|error_callback=window\.show_error_message"
        r"|\bwindow\.canvas_tabs\b"
        r"|\bwindow\.preview_3d\b"
        r"|tool_mode_controller=None"
        r"|status_service=None"
        r"|context_bar_service=None"
        r"|action_availability_service=None"
        r"|context_page_state_service=None"
        r"|tab_refs_for_window=None"
        r"|preview_for_window=None"
    )

    assert _matching_lines(pattern, [service]) == []


def test_main_window_code_binds_preview_rdkit_through_preview_api() -> None:
    paths = sorted((APP_ROOT / "chemvas" / "ui").glob("main_window*.py"))
    pattern = re.compile(r"\bpreview_3d\._rdkit\b")

    assert _matching_lines(pattern, paths) == []


def test_preview_3d_does_not_reintroduce_renderer_delegate_wrappers() -> None:
    preview = APP_ROOT / "chemvas" / "ui" / "preview_3d.py"
    tree = ast.parse(preview.read_text())
    preview_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Preview3D"
    )
    removed_wrappers = {
        "_caption_font",
        "_draw_card_shadow",
        "_draw_empty_state",
        "_draw_footer",
        "_draw_info_chip",
        "_draw_interaction_hints",
        "_draw_header",
        "_draw_panel",
        "_draw_viewport",
        "_element_color",
        "_empty_state_text",
        "_footer_item_rects",
        "_footer_height",
        "_info_items",
        "_info_lines",
        "_layout_rects",
        "_metadata_summary",
        "_overlay_font",
        "_project_scene",
        "_status_badge",
    }
    method_names = {
        node.name for node in preview_class.body if isinstance(node, ast.FunctionDef)
    }

    assert method_names.isdisjoint(removed_wrappers)


def test_preview_3d_renderer_delegates_molecule_scene_drawing() -> None:
    renderer = APP_ROOT / "chemvas" / "ui" / "preview_3d_renderer.py"
    renderer_source = renderer.read_text()

    assert "def draw_projected_scene" not in renderer_source
    assert "def preview_element_color" not in renderer_source


def test_main_window_ui_assembly_service_uses_injected_canvas_service_ports() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_ui_assembly_service.py"
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|\bcanvas_runtime_service_for\b"
        r"|(?:scene_transform_controller|insert_controller|tool_mode_controller)=None"
    )

    assert _matching_lines(pattern, [service]) == []


def test_main_window_ui_assembly_moves_tool_actions_into_panel_toolbar() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_ui_assembly_service.py"
    service_source = service.read_text()

    assert not (APP_ROOT / "chemvas" / "ui" / "main_window_left_toolbar.py").exists()
    assert "from chemvas.ui.main_window_left_toolbar import" not in service_source
    assert "LeftToolBarArea" not in service_source
    assert "TOOLBAR_TOOL_GROUPS" not in service_source


def test_main_window_ui_assembly_delegates_panel_toolbar_to_module() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_ui_assembly_service.py"
    panel_toolbar = APP_ROOT / "chemvas" / "ui" / "main_window_panel_toolbar.py"
    service_source = service.read_text()
    panel_toolbar_source = panel_toolbar.read_text()
    pattern = re.compile(
        r"triggered\.connect\(window\."
        r"|callback=window\."
        r"|menu_builder=lambda menu: window\."
        r"|\bwindow\.icon_factory\b"
    )

    assert "topRoleToolbar" not in service_source
    assert "smiles_render_button" not in service_source
    assert "QKeySequence" not in service_source
    # The SMILES quick-insert field is built in the panel toolbar module (it lives
    # on the top toolbar), so smiles_render_button is expected there — only the
    # assembly service must stay free of it.
    assert "callbacks.set_bond_length(window)" not in panel_toolbar_source
    assert "window.set_bond_length" not in panel_toolbar_source
    assert _matching_lines(pattern, [panel_toolbar]) == []


def test_main_window_ui_assembly_delegates_toolbar_buttons_to_module() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_ui_assembly_service.py"
    service_source = service.read_text()

    assert "QPainter" not in service_source
    assert "QPolygonF" not in service_source
    assert "TOOLBAR_MENU_BUTTON_STYLE" not in service_source


def test_main_window_document_action_service_delegates_dialog_assembly_to_module() -> (
    None
):
    service = APP_ROOT / "chemvas" / "ui" / "main_window_document_action_service.py"
    service_source = service.read_text()

    assert "prompt_sheet_setup(" not in service_source
    assert "QDialog" not in service_source
    assert "QComboBox" not in service_source
    assert "QDoubleSpinBox" not in service_source
    assert "QFrame" not in service_source
    assert "ArrowButton" not in service_source


def test_main_window_keeps_dialog_defaults_inside_action_services() -> None:
    main_window = APP_ROOT / "chemvas" / "shell" / "main_window.py"
    main_window_source = main_window.read_text()

    for concrete_default in (
        "QColorDialog",
        "QFileDialog",
        "QMessageBox",
        "read_document",
        "resolve_save_path",
        "resolve_save_as_path",
        "resolve_load_path",
        "QTimer",
    ):
        assert concrete_default not in main_window_source


def test_main_window_panel_service_owns_preview_window_assembly() -> None:
    ui_assembly = APP_ROOT / "chemvas" / "ui" / "main_window_ui_assembly_service.py"
    panel_service = APP_ROOT / "chemvas" / "ui" / "main_window_panel_service.py"
    preview_window = APP_ROOT / "chemvas" / "ui" / "main_window_preview_window.py"
    ui_source = ui_assembly.read_text()
    panel_service_source = panel_service.read_text()
    preview_window_source = preview_window.read_text()

    assert "init_panels" not in ui_source
    assert "QDockWidget" not in ui_source
    assert "QSplitter" not in ui_source
    assert "icon_export_xyz" not in panel_service_source
    assert (
        re.search(r"\bwindow\.panel_(?:splitter|dock)\b", panel_service_source) is None
    )
    assert "preview_export_xyz_button" not in preview_window_source
    assert "QDockWidget" not in preview_window_source
    assert "QSplitter" not in preview_window_source


def test_main_window_action_availability_service_uses_injected_ports_and_public_buttons() -> (
    None
):
    service = APP_ROOT / "chemvas" / "ui" / "main_window_action_availability_service.py"
    pattern = re.compile(
        r"\bwindow\.canvas\b"
        r"|\bwindow\._"
        r"|\bwindow\.active_canvas_or_none\("
        r"|\bwindow\.undo_button\b"
        r"|\bwindow\.redo_button\b"
        r"|\bwindow\.export_xyz_button\b"
        r"|\bhas_atoms_for\b"
        r"|\bhistory_service_for_canvas\b"
        r"|(?:history_service|has_exportable_atoms)=None"
    )

    assert _matching_lines(pattern, [service]) == []


def test_main_window_document_action_service_uses_injected_canvas_service_ports() -> (
    None
):
    service = APP_ROOT / "chemvas" / "ui" / "main_window_document_action_service.py"
    services = APP_ROOT / "chemvas" / "bootstrap" / "main_window_services.py"
    source = service.read_text()
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|(?:document_session_service|geometry_controller)=None"
        r"|\bwindow\.canvas\b"
        r"|\bwindow\.save_canvas_as\("
        r"|\bwindow\.save_canvas_to_path\("
        r"|\bwindow\.default_save_dialog_path\("
        r"|\bwindow\.default_xyz_export_path\("
        r"|\bwindow\.current_file_path\b"
    )

    assert "sheet_size_for_window" not in source
    assert "sheet_orientation_for_window" not in source
    assert "set_sheet_setup_for_window" not in source
    assert "workbook_document_service" not in source
    assert "save_document_state" not in source
    assert "sheet_size_for_window=sheet_size_for_window" not in services.read_text()
    assert (
        "sheet_orientation_for_window=sheet_orientation_for_window"
        not in services.read_text()
    )
    assert (
        "set_sheet_setup_for_window=set_sheet_setup_for_window"
        not in services.read_text()
    )
    assert _matching_lines(pattern, [service]) == []


def test_canvas_controller_access_module_removed() -> None:
    assert not (APP_ROOT / "chemvas" / "ui" / "canvas_controller_access.py").exists()

    pattern = re.compile(r"\bcanvas_controller_access\b")
    assert _matching_lines(pattern, _app_python_files()) == []


def test_insert_controller_lookup_helper_removed_from_production_code() -> None:
    pattern = re.compile(r"\binsert_controller_for\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_geometry_controller_local_lookup_helper_removed_from_production_code() -> None:
    pattern = re.compile(
        r"\b(?:geometry_controller_for|canvas_geometry_controller_for)\b"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_legacy_chemdraw_shortcut_access_helper_removed_from_production_code() -> None:
    pattern = re.compile(r"\bhandle_chemdraw_shortcut_for\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_canvas_tool_access_module_removed_from_production_code() -> None:
    assert not (APP_ROOT / "chemvas" / "ui" / "canvas_tool_access.py").exists()

    pattern = re.compile(
        r"\bcanvas_tool_access\b"
        r"|\b(?:active_tool_for|active_tool_name_for|tool_for_name_for|set_active_tool_for)\b"
    )
    assert _matching_lines(pattern, _app_python_files()) == []


def test_handle_and_rotation_preview_lookup_helpers_removed_from_production_code() -> (
    None
):
    removed_helpers = (
        "canvas_handle_controller_for",
        "canvas_atom_mutation_service_for",
        "canvas_bond_mutation_service_for",
        "canvas_chemdraw_shortcut_service_for",
        "canvas_color_mutation_service_for",
        "canvas_document_session_service_for",
        "canvas_graph_service_for",
        "atom_bond_order_sum_for",
        "canvas_hit_testing_service_for",
        "canvas_ring_fill_scene_service_for",
        "canvas_rotation_preview_controller_for",
        "canvas_scene_reset_service_for",
        "canvas_scene_decoration_build_service_for",
        "canvas_tool_mode_controller_for",
        "benzene_preview_service_for",
        "bond_hover_preview_service_for",
        "curved_arrow_path_service_for",
        "canvas_mark_scene_service_for",
        "canvas_note_controller_for",
        "canvas_history_recording_service_for",
        "handle_mutation_service_for",
        "handle_overlay_service_for",
        "hover_interaction_service_for",
        "hover_scene_service_for",
        "mark_hover_preview_service_for",
        "main_window_workbook_document_service_for",
        "scene_decoration_service_for",
        "scene_ops_controller_for",
        "selection_rotation_controller_for",
        "canvas_style_controller_for",
        "structure_build_service_for",
        "structure_insert_service_for",
        "tool_controller_for",
    )
    pattern = re.compile(
        rf"\b(?:{'|'.join(re.escape(name) for name in removed_helpers)})\b"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_history_lookup_helper_removed_from_app_code() -> None:
    paths = _app_python_files()
    pattern = re.compile(r"\bhistory_service_for\b")

    assert _matching_lines(pattern, paths) == []


def test_history_collaborator_services_use_injected_history_port() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "atom_label_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_color_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_document_session_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_geometry_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_history_recording_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_input_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_note_controller.py",
        APP_ROOT / "chemvas" / "ui" / "insert_controller.py",
        APP_ROOT / "chemvas" / "ui" / "scene_decoration_service.py",
        APP_ROOT / "chemvas" / "ui" / "selection_rotation_controller.py",
        APP_ROOT / "chemvas" / "ui" / "tool_context.py",
    ]
    pattern = re.compile(
        r"\bcanvas_runtime_service_for\b"
        r"|\bhistory_service\s+or\s+"
        r"|\bself\.history\s+or\s+"
    )

    assert _matching_lines(pattern, paths) == []


def test_access_helpers_do_not_repeat_default_private_legacy_names_at_call_sites() -> (
    None
):
    pattern = re.compile(
        r"\b(?:canvas_service_for|canvas_context_for)\([^,\n]+,\s*"
        r"\"(?P<name>[A-Za-z0-9_]+)\",\s*\"_(?P=name)\""
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_production_context_factories_use_default_public_context_keys() -> None:
    matches: list[str] = []
    for path in _app_python_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id != "canvas_context_for"
            ):
                continue
            if any(keyword.arg == "legacy_attr" for keyword in node.keywords):
                matches.append(
                    f"{path.relative_to(APP_ROOT.parents[0])}:{node.lineno}: "
                    "canvas_context_for(..., legacy_attr=...)"
                )

    assert matches == []


def test_production_code_does_not_cache_contexts_as_private_fields() -> None:
    pattern = re.compile(
        r"\bvars\([^)]*\)\.get\(\s*\"_[A-Za-z0-9_]+_context\""
        r"|\bvars\([^)]*\)\[\s*\"_[A-Za-z0-9_]+_context\"\s*\]"
        r"|\"_[A-Za-z0-9_]+_context\"\s*\]\s*="
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_selection_flow_does_not_use_selection_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "selection_context.py"
    paths = [
        APP_ROOT / "chemvas" / "ui" / "selection_controller.py",
        APP_ROOT / "chemvas" / "ui" / "selection_access.py",
        APP_ROOT / "chemvas" / "ui" / "selection_service_access.py",
        APP_ROOT / "chemvas" / "ui" / "move_access.py",
        APP_ROOT / "chemvas" / "ui" / "selection_style_access.py",
        APP_ROOT / "chemvas" / "ui" / "note_selection_box.py",
    ]
    pattern = re.compile(
        r"\bSelectionContext\b"
        r"|\bselection_context_for\b"
        r"|self\.context\b"
        r"|\bselection_controller_for\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, paths) == []


def test_selection_collection_helpers_live_outside_selection_access_facade() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "selection_access.py"
    collection = APP_ROOT / "chemvas" / "ui" / "selection_collection_access.py"
    service_access = APP_ROOT / "chemvas" / "ui" / "selection_service_access.py"
    access_source = access.read_text()
    collection_source = collection.read_text()
    service_source = service_access.read_text()
    moved_defs = (
        "selected_ids_for",
        "selected_scene_items_for",
        "selection_items_for_copy_for",
        "selected_atom_ids_for_transform_for",
        "selection_status_count_for",
        "selection_snapshot_for",
    )
    service_defs = (
        "selection_service_from_canvas",
        "refresh_selection_outline_for",
        "selection_targets_for_item_for",
        "select_single_structure_item_for",
    )

    for helper in moved_defs:
        assert f"def {helper}" not in access_source
        assert f"def {helper}" in collection_source
    for helper in service_defs:
        assert f"def {helper}" not in access_source
        assert f"def {helper}" in service_source


def test_production_code_uses_selection_specific_access_modules_instead_of_compat_facade() -> (
    None
):
    compat_facade = APP_ROOT / "chemvas" / "ui" / "selection_access.py"
    import_pattern = re.compile(
        r"\bfrom ui\.selection_access import\b|\bimport ui\.selection_access\b"
    )
    app_paths = [path for path in _app_python_files() if path != compat_facade]

    assert _matching_lines(import_pattern, app_paths) == []


def test_access_helpers_use_canvas_service_accessor_instead_of_services_lookup() -> (
    None
):
    paths = [
        APP_ROOT / "chemvas" / "ui" / "input_view_access.py",
        APP_ROOT / "chemvas" / "ui" / "move_access.py",
        APP_ROOT / "chemvas" / "ui" / "selection_access.py",
        APP_ROOT / "chemvas" / "ui" / "selection_service_access.py",
        APP_ROOT / "chemvas" / "ui" / "history_canvas_access.py",
    ]
    pattern = re.compile(
        r"\bcanvas\.services\."
        r"|getattr\([^,\n]+,\s*\"services\""
    )

    assert _matching_lines(pattern, paths) == []


def test_simple_canvas_access_helpers_delegate_service_lookup_to_ports() -> None:
    access_paths = [
        APP_ROOT / "chemvas" / "ui" / "canvas_model_access.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_scene_reset_access.py",
        APP_ROOT / "chemvas" / "ui" / "insert_session_access.py",
        APP_ROOT / "chemvas" / "ui" / "note_item.py",
        APP_ROOT / "chemvas" / "ui" / "note_item_access.py",
        APP_ROOT / "chemvas" / "ui" / "selection_highlight_styler.py",
    ]
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, access_paths) == []


def test_canvas_service_ports_keep_simple_service_accessors_consolidated() -> None:
    old_port_modules = (
        "atom_label_ports.py",
        "benzene_preview_ports.py",
        "canvas_geometry_ports.py",
        "canvas_ring_fill_scene_ports.py",
        "canvas_scene_reset_ports.py",
        "canvas_window_ports.py",
        "handle_mutation_ports.py",
        "handle_overlay_ports.py",
        "history_canvas_ports.py",
        "history_recording_ports.py",
        "hover_ports.py",
        "insert_session_ports.py",
        "move_ports.py",
        "note_item_ports.py",
        "scene_decoration_ports.py",
        "scene_item_ports.py",
        "selection_highlight_ports.py",
        "selection_ports.py",
        "structure_build_ports.py",
        "structure_insert_ports.py",
        "structure_mutation_ports.py",
    )
    app_source = "\n".join(path.read_text() for path in _app_python_files())

    for module_name in old_port_modules:
        assert not (APP_ROOT / "chemvas" / "ui" / module_name).exists()
        assert module_name.removesuffix(".py") not in app_source


def test_note_committed_text_private_state_stays_inside_note_item() -> None:
    allowed_paths = {APP_ROOT / "chemvas" / "ui" / "note_item.py"}
    paths = [path for path in _app_python_files() if path not in allowed_paths]
    forbidden = re.compile(r"\._last_text\b")

    assert _matching_lines(forbidden, paths) == []


def test_history_canvas_access_delegates_service_lookup_to_history_ports() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "history_canvas_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_structure_mutation_access_delegates_service_lookup_to_structure_ports() -> (
    None
):
    access = APP_ROOT / "chemvas" / "ui" / "structure_mutation_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_ring_fill_scene_access_delegates_service_lookup_to_ring_fill_ports() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "canvas_ring_fill_scene_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_structure_build_access_delegates_service_lookup_to_structure_build_ports() -> (
    None
):
    access = APP_ROOT / "chemvas" / "ui" / "structure_build_access.py"
    commands = APP_ROOT / "chemvas" / "ui" / "structure_template_commands.py"
    command_source = commands.read_text()
    forbidden = re.compile(
        r"\bcanvas_services_for\b"
        r"|\bcanvas\.services\."
        r"|\b_REGULAR_RING_TEMPLATES\b"
        r"|\b_HETERO_RING_TEMPLATES\b"
        r"|\b_SERVICE_TEMPLATE_METHODS\b"
    )

    assert "service.add_regular_ring_template" not in command_source
    assert "service.add_phenyl" not in command_source
    assert _matching_lines(forbidden, [access]) == []


def test_structure_insert_access_delegates_service_lookup_to_structure_insert_ports() -> (
    None
):
    access = APP_ROOT / "chemvas" / "ui" / "structure_insert_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_scene_decoration_access_delegates_service_lookup_to_scene_decoration_ports() -> (
    None
):
    access = APP_ROOT / "chemvas" / "ui" / "scene_decoration_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_mark_item_access_delegates_service_lookup_to_scene_decoration_ports() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "mark_item_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_scene_decoration_build_access_delegates_service_lookup_to_scene_decoration_ports() -> (
    None
):
    access = APP_ROOT / "chemvas" / "ui" / "scene_decoration_build_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_handle_mutation_access_delegates_service_lookup_to_handle_mutation_ports() -> (
    None
):
    access = APP_ROOT / "chemvas" / "ui" / "handle_mutation_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_handle_overlay_access_delegates_service_lookup_to_handle_overlay_ports() -> (
    None
):
    access = APP_ROOT / "chemvas" / "ui" / "handle_overlay_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_history_recording_access_delegates_service_lookup_to_history_recording_ports() -> (
    None
):
    access = APP_ROOT / "chemvas" / "ui" / "history_recording_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_canvas_window_access_delegates_service_lookup_to_canvas_window_ports() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "canvas_window_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_move_access_delegates_service_lookup_to_move_ports() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "move_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_geometry_access_helpers_delegate_service_lookup_to_geometry_ports() -> None:
    access_paths = [
        APP_ROOT / "chemvas" / "ui" / "bond_graphics_access.py",
        APP_ROOT / "chemvas" / "ui" / "bond_label_geometry_access.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_geometry_access.py",
    ]
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, access_paths) == []


def test_selection_service_access_delegates_service_lookup_to_selection_ports() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "selection_service_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_export_render_service_dispatches_to_format_specific_renderers() -> None:
    service = APP_ROOT / "chemvas" / "features" / "export" / "service.py"
    forbidden_device_types = re.compile(
        r"\bQPainter\b|\bQSvgGenerator\b|\bQPdfWriter\b|\bQImage\b"
    )

    assert _matching_lines(forbidden_device_types, [service]) == []


def test_scene_item_access_delegates_service_lookup_to_scene_item_ports() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "scene_item_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_scene_item_access_delegates_scene_storage_to_scene_state() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "scene_item_access.py"
    forbidden = re.compile(r"\bcanvas\.scene\(")

    assert _matching_lines(forbidden, [access]) == []


def test_atom_label_access_delegates_service_lookup_to_atom_label_ports() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "atom_label_access.py"
    forbidden = re.compile(r"\bcanvas_services_for\b|\bcanvas\.services\.")

    assert _matching_lines(forbidden, [access]) == []


def test_required_canvas_service_lookup_helper_removed_from_production_code() -> None:
    pattern = re.compile(r"\bcanvas_service_for\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_service_fallbacks_use_canvas_service_accessor_instead_of_services_lookup() -> (
    None
):
    paths = [
        APP_ROOT / "chemvas" / "ui" / "atom_label_service.py",
        APP_ROOT / "chemvas" / "ui" / "selection_rotation_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_tool_mode_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_style_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_chemdraw_shortcut_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_document_session_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_input_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_pointer_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_atom_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_bond_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_color_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "insert_controller.py",
        APP_ROOT / "chemvas" / "ui" / "scene_item_controller.py",
        APP_ROOT / "chemvas" / "ui" / "selection_service_bundle.py",
        APP_ROOT / "chemvas" / "ui" / "selection_hit_test_service.py",
        APP_ROOT / "chemvas" / "ui" / "selection_outline_service.py",
        APP_ROOT / "chemvas" / "ui" / "selection_structure_service.py",
        APP_ROOT / "chemvas" / "ui" / "structure_bond_build_service.py",
        APP_ROOT / "chemvas" / "ui" / "structure_build_service.py",
        APP_ROOT / "chemvas" / "ui" / "structure_insert_service.py",
    ]
    pattern = re.compile(
        r"\b(?:self\.)?canvas\.services\."
        r"|getattr\([^,\n]+,\s*\"services\""
    )

    assert _matching_lines(pattern, paths) == []


def test_move_controller_collaborators_do_not_lookup_canvas_services() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "atom_label_service.py",
        APP_ROOT / "chemvas" / "ui" / "selection_rotation_controller.py",
    ]
    pattern = re.compile(
        r"\bdef _move_controller\b"
        r"|\b_move_controller\("
        r"|canvas_service_for\([^,\n]+,\s*\"move_controller\""
        r"|\bresolve_canvas_graph_service\b"
        r"|canvas_service_for\([^,\n]+,\s*\"canvas_graph_service\""
    )

    assert _matching_lines(pattern, paths) == []


def test_explicit_service_collaborators_do_not_lookup_canvas_services() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "canvas_style_controller.py",
        APP_ROOT / "chemvas" / "ui" / "structure_insert_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_tool_mode_controller.py",
    ]
    pattern = re.compile(
        r"\bdef _note_controller\b"
        r"|\b_note_controller\("
        r"|canvas_service_for\([^,\n]+,\s*\"(?:note_controller|selection_controller|insert_controller)\""
    )

    assert _matching_lines(pattern, paths) == []


def test_tool_mode_controller_does_not_lookup_legacy_hover_refresh_helpers() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_tool_mode_controller.py"
    pattern = re.compile(
        r"\bcanvas_hover_refresh\b"
        r"|\brefresh_hover_from_cursor_for\b"
    )

    assert _matching_lines(pattern, [controller]) == []


def test_tool_activation_uses_injected_ports() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "canvas_tool_mode_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_view.py",
    ]
    pattern = re.compile(
        r"\bcanvas_tool_access\b"
        r"|\bset_active_tool_for\b"
    )

    assert _matching_lines(pattern, paths) == []


def test_hover_refresh_consumers_do_not_lookup_legacy_refresh_helpers() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "canvas_input_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_pointer_controller.py",
        APP_ROOT / "chemvas" / "ui" / "atom_label_service.py",
        APP_ROOT / "chemvas" / "ui" / "input_view_access.py",
    ]
    pattern = re.compile(
        r"\bcanvas_hover_refresh\b"
        r"|\brefresh_hover_from_cursor_for\b"
        r"|\brefresh_hover_from_cursor_callback_for\b"
    )

    assert _matching_lines(pattern, paths) == []


def test_hover_controller_uses_injected_collaborators_without_service_lookup() -> None:
    module = APP_ROOT / "chemvas" / "ui" / "hover.py"
    pattern = re.compile(
        r"\b(?:canvas_services_for|canvas_service_for|optional_canvas_service_for)\b"
        r"|getattr\([^,\n]+,\s*\"services\""
        r"|\b(?:selection_controller|hit_testing_service|insert_controller|"
        r"scene_decoration_build_service|mark_scene_service|"
        r"active_tool_name_provider)\s*=\s*None"
    )

    assert _matching_lines(pattern, [module]) == []


def test_input_controller_uses_injected_chemdraw_shortcut_service() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_input_controller.py"
    pattern = re.compile(
        r"\bhandle_chemdraw_shortcut_for\b"
        r"|canvas_service_for\([^,\n]+,\s*\"chemdraw_shortcut_service\""
    )

    assert _matching_lines(pattern, [controller]) == []


def test_mutation_services_use_injected_graph_service() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "canvas_atom_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_bond_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_color_mutation_service.py",
    ]
    pattern = re.compile(
        r"\bresolve_canvas_graph_service\b"
        r"|canvas_service_for\([^,\n]+,\s*\"canvas_graph_service\""
        r"|graph_service=None"
    )

    assert _matching_lines(pattern, paths) == []


def test_graph_collaborator_services_require_explicit_graph_service() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "atom_label_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_document_session_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_color_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "insert_controller.py",
        APP_ROOT / "chemvas" / "ui" / "scene_item_controller.py",
        APP_ROOT / "chemvas" / "ui" / "selection_rotation_controller.py",
    ]
    pattern = re.compile(
        r"\bresolve_canvas_graph_service\b"
        r"|canvas_service_for\([^,\n]+,\s*\"canvas_graph_service\""
        r"|graph_service=None"
        r"|if self\.graph_service is None"
    )

    assert _matching_lines(pattern, paths) == []


def test_mark_and_handle_services_use_explicit_collaborators() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "canvas_chemdraw_shortcut_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_mark_scene_service.py",
        APP_ROOT / "chemvas" / "ui" / "handle_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_handle_controller.py",
    ]
    pattern = re.compile(
        r"\bdef _scene_decoration_service\b"
        r"|\b_scene_decoration_service\("
        r"|\bdef _curved_arrow_path_service\b"
        r"|\b_curved_arrow_path_service\("
        r"|\bdef _handle_overlay_service\b"
        r"|\bdef _handle_mutation_service\b"
        r"|\b_handle_overlay_service\("
        r"|\b_handle_mutation_service\("
        r"|canvas_service_for\([^,\n]+,\s*\"(?:canvas_mark_scene_service|scene_decoration_service|curved_arrow_path_service|handle_overlay_service|handle_mutation_service)\""
    )

    assert _matching_lines(pattern, paths) == []


def test_selection_controller_delegates_structure_selection_details() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "selection_controller.py"
    service = APP_ROOT / "chemvas" / "ui" / "selection_structure_service.py"
    controller_pattern = re.compile(r"\bring_items_for\b|\bclear_scene_selection_for\b")
    service_pattern = re.compile(
        r"\bclass SelectionStructureService\b|\bStructureSelectionResult\b"
    )

    assert service.exists()
    assert _matching_lines(controller_pattern, [controller]) == []
    assert _matching_lines(service_pattern, [service]) != []


def test_selection_controller_delegates_outline_rendering_details() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "selection_controller.py"
    service = APP_ROOT / "chemvas" / "ui" / "selection_outline_service.py"
    controller_pattern = re.compile(
        r"\bNoSelectPathItem\b|\bNoSelectEllipseItem\b"
        r"|\bring_center_for_bond_for\b|\btrim_line_for_labels_for\b"
        r"|\bselection_indicator_rect_for_atom_for\b|\bselection_bond_overlay_width_for\b"
        r"|\bbounding_box_center_for_atoms\b|\bactive_tool_name_for\b"
        r"|\bscene_selected_items_for\b"
    )
    service_pattern = re.compile(
        r"\bclass SelectionOutlineService\b|\bOBJECT_OVERLAY_KINDS\b"
    )

    assert service.exists()
    assert _matching_lines(controller_pattern, [controller]) == []
    assert _matching_lines(service_pattern, [service]) != []


def test_selection_controller_delegates_hit_test_details() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "selection_controller.py"
    service = APP_ROOT / "chemvas" / "ui" / "selection_hit_test_service.py"
    controller_pattern = re.compile(
        r"\bSelectionHitRequest\b|\bselection_hit_matches\b"
        r"|\bbounds_for_atoms_for\b|\bselection_snapshot_for\b"
        r"|\bselection_outlines_for\b"
    )
    service_pattern = re.compile(
        r"\bclass SelectionHitTestService\b|\bSelectionHitRequest\b"
    )

    assert service.exists()
    assert _matching_lines(controller_pattern, [controller]) == []
    assert _matching_lines(service_pattern, [service]) != []


def test_selection_controller_delegates_note_selection_details() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "selection_controller.py"
    service = APP_ROOT / "chemvas" / "ui" / "selection_note_service.py"
    controller_pattern = re.compile(
        r"\bselected_notes_for\b|\badd_selected_note_for\b|\bremove_selected_note_for\b"
        r"|\bclear_selected_notes_for\b|\bNoSelectRectItem\b|\btext_style_state_for\b"
        r"|\bselection_stroke_delta_for\b"
    )
    service_pattern = re.compile(r"\bclass SelectionNoteService\b|\bnote_select\b")

    assert service.exists()
    assert _matching_lines(controller_pattern, [controller]) == []
    assert _matching_lines(service_pattern, [service]) != []


def test_selection_controller_delegates_preference_details() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "selection_controller.py"
    service = APP_ROOT / "chemvas" / "ui" / "selection_preference_service.py"
    controller_pattern = re.compile(
        r"\batom_has_visible_label_for\b|\bvisible_atom_item_for\b"
        r"|\bchoose_preferred_structure_hit\b|\bnearest_ring_atom_id\b"
        r"|\batom_pick_radius_for\b|\bbond_pick_radius_for\b"
        r"|\bcanvas_hit_testing_service_for\b"
    )
    service_pattern = re.compile(
        r"\bclass SelectionPreferenceService\b|\bchoose_preferred_structure_hit\b"
    )

    assert service.exists()
    assert _matching_lines(controller_pattern, [controller]) == []
    assert _matching_lines(service_pattern, [service]) != []


def test_selection_controller_does_not_reintroduce_private_delegate_wrappers() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "selection_controller.py"
    tree = ast.parse(controller.read_text())
    private_methods: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "SelectionController":
            continue
        private_methods = [
            child.name
            for child in node.body
            if isinstance(child, ast.FunctionDef)
            and child.name.startswith("_")
            and not (child.name.startswith("__") and child.name.endswith("__"))
        ]
        break

    assert private_methods == []


def test_selection_controller_does_not_construct_collaborator_services() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "selection_controller.py"
    forbidden_collaborators = {
        "SelectionStructureService",
        "SelectionPreferenceService",
        "SelectionOutlineService",
        "SelectionNoteService",
        "SelectionHitTestService",
    }
    matches: list[str] = []
    tree = ast.parse(controller.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in forbidden_collaborators:
            matches.append(f"{node.func.id}(...):{node.lineno}")

    assert matches == []


def test_selection_controller_is_only_assembled_by_selection_service_bundle() -> None:
    pattern = re.compile(r"\bSelectionController\(")
    paths = [
        path
        for path in _app_python_files()
        if path.name != "selection_service_bundle.py"
    ]

    assert _matching_lines(pattern, paths) == []


def test_selection_lookup_services_require_explicit_collaborators() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "selection_preference_service.py",
        APP_ROOT / "chemvas" / "ui" / "selection_hit_test_service.py",
    ]
    pattern = re.compile(
        r"\bcanvas_hit_testing_service_for\b"
        r"|\bSelectionStructureService\("
        r"|\bdef _hit_testing_service\b"
        r"|\bdef _item_at_scene_pos\b"
    )

    assert _matching_lines(pattern, paths) == []


def test_tool_controller_assembles_tool_context_with_explicit_ports() -> None:
    source = (APP_ROOT / "chemvas" / "ui" / "tool_controller.py").read_text()

    assert "ToolContext(canvas)" not in source


def test_tool_service_bundle_injects_tool_context_ports() -> None:
    source = (APP_ROOT / "chemvas" / "ui" / "tool_service_bundle.py").read_text()

    assert "tool_mode_controller" not in source
    assert "ToolController(canvas)" not in source


def _canvas_services_entrypoint_source() -> str:
    return (APP_ROOT / "chemvas" / "ui" / "canvas_services.py").read_text()


def _canvas_service_composer_source() -> str:
    return (APP_ROOT / "chemvas" / "ui" / "canvas_service_composer.py").read_text()


def _service_assembly_paths() -> list[Path]:
    return [
        APP_ROOT / "chemvas" / "ui" / "canvas_services.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_service_composer.py",
    ]


def test_canvas_services_delegates_tool_service_assembly_to_bundle() -> None:
    source = _canvas_service_composer_source()

    assert "ToolController(" not in source


def test_canvas_services_delegates_handle_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:CanvasHandleController|CurvedArrowPathService|HandleMutationService|HandleOverlayService)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_runtime_services_exposes_direct_hover_controller_boundary() -> None:
    runtime_services = APP_ROOT / "chemvas" / "ui" / "canvas_runtime_services.py"
    tree = ast.parse(runtime_services.read_text())
    hover_annotation: str | None = None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "CanvasRuntimeServices":
            continue
        for child in node.body:
            if (
                isinstance(child, ast.AnnAssign)
                and isinstance(child.target, ast.Name)
                and child.target.id == "hover"
            ):
                hover_annotation = ast.unparse(child.annotation)
                break

    assert hover_annotation == "HoverController"


def test_hover_service_graph_does_not_reintroduce_legacy_role_stack() -> None:
    paths = [
        *_service_assembly_paths(),
        APP_ROOT / "chemvas" / "ui" / "canvas_runtime_services.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_input_service_bundle.py",
        APP_ROOT / "chemvas" / "ui" / "hover.py",
    ]
    pattern = re.compile(
        r"\b(?:HoverServices|HoverServiceBundle|BondHoverPreviewService|"
        r"HoverInteractionService|HoverSceneService|MarkHoverPreviewService)\b"
        r"|\b(?:bond_hover_preview_service|canvas_hover_refresh|"
        r"hover_interaction_service|hover_scene_service|hover_service_bundle|"
        r"mark_hover_preview_service)\b"
    )

    assert _matching_lines(pattern, paths) == []


def test_canvas_services_delegates_scene_decoration_service_assembly_to_bundle() -> (
    None
):
    direct_instantiation = re.compile(
        r"\b(?:CanvasMarkSceneService|CanvasSceneDecorationBuildService|SceneDecorationService)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_services_delegates_scene_operation_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:CanvasColorMutationService|CanvasStyleController|SceneClipboardController|"
        r"SceneDeleteController|SceneTransformController)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_scene_ops_controller_stays_out_of_production_service_graph() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "canvas_service_types.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_service_composer.py",
        APP_ROOT / "chemvas" / "ui" / "scene_operation_service_bundle.py",
    ]
    pattern = re.compile(r"\bscene_ops_controller\b|\bSceneOpsController\b")

    assert _matching_lines(pattern, paths) == []


def test_canvas_services_delegates_document_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:CanvasDocumentSessionService|CanvasHistoryRecordingService|CanvasSceneResetService)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_services_delegates_scene_view_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:CanvasGeometryController|CanvasRingFillSceneService|CanvasRotationPreviewController|"
        r"SceneItemController|SelectionHighlightStyler)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_services_delegates_interaction_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:CanvasMoveController|CanvasNoteController|SelectionRotationController)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_services_delegates_auxiliary_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:AtomLabelService|StructureInsertService)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_template_preview_does_not_reintroduce_separate_benzene_runtime() -> None:
    pattern = re.compile(
        r"\bbenzene_preview_items\b"
        r"|\bbenzene_preview_service(?:_for(?:_access)?)?\b"
        r"|\bBenzenePreviewService\b"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_canvas_services_delegates_structure_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:CanvasAtomMutationService|CanvasBondMutationService|InsertController|StructureBuildService)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_services_delegates_input_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:CanvasChemdrawShortcutService|CanvasInputController|CanvasPointerController|CanvasToolModeController)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_services_delegates_graph_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(r"\bCanvasGraphService\(")

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_services_uses_active_tool_reference_port() -> None:
    entrypoint = _canvas_services_entrypoint_source()
    source = _canvas_service_composer_source()

    assert "ActiveToolReference" not in entrypoint
    assert "tool_controller_holder" not in source


def test_canvas_services_does_not_construct_services_or_controllers_directly() -> None:
    direct_instantiation = re.compile(
        r"\b[A-Z][A-Za-z0-9_]*(?:Service|Controller|Styler)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_tool_implementations_use_tool_context_for_canvas_ports() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "edit_tools.py",
        APP_ROOT / "chemvas" / "ui" / "perspective_tool.py",
        APP_ROOT / "chemvas" / "ui" / "select_tool.py",
        APP_ROOT / "chemvas" / "ui" / "text_tool.py",
    ]
    pattern = re.compile(
        r"\bcanvas_service_for\b"
        r"|\bselected_scene_items_for\b"
        r"|\bself\.canvas\.setDragMode\b"
        r"|canvas_service_for\([^,\n]+,\s*\"(?:canvas_color_mutation_service|tool_mode_controller)\""
    )

    assert _matching_lines(pattern, paths) == []


def test_canvas_services_delegates_selection_service_assembly_to_bundle() -> None:
    source = _canvas_service_composer_source()

    assert "SelectionStructureService" not in source
    assert "SelectionPreferenceService" not in source
    assert "SelectionOutlineService" not in source
    assert "SelectionNoteService" not in source
    assert "SelectionHitTestService" not in source
    assert "SelectionController(canvas)" not in source


def _legacy_canvas_service_names() -> frozenset[str]:
    runtime_services = APP_ROOT / "chemvas" / "ui" / "canvas_runtime_services.py"
    tree = ast.parse(runtime_services.read_text())
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "_LEGACY_SERVICE_PATHS" or node.value is None:
            continue
        return frozenset(ast.literal_eval(node.value))
    raise AssertionError("legacy canvas service map not found")


def test_production_canvas_service_consumers_use_grouped_runtime_api() -> None:
    legacy_names = _legacy_canvas_service_names()
    runtime_services = APP_ROOT / "chemvas" / "ui" / "canvas_runtime_services.py"
    violations: list[str] = []

    for path in sorted((APP_ROOT / "chemvas").rglob("*.py")):
        if path == runtime_services:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in legacy_names:
                owner = node.value
                flat_services_name = (
                    isinstance(owner, ast.Name) and owner.id == "services"
                )
                flat_services_attribute = (
                    isinstance(owner, ast.Attribute) and owner.attr == "services"
                )
                direct_lookup = (
                    isinstance(owner, ast.Call)
                    and isinstance(owner.func, ast.Name)
                    and owner.func.id
                    in {
                        "active_canvas_services_for",
                        "build_canvas_services",
                        "canvas_services_for",
                    }
                )
                if flat_services_name or flat_services_attribute or direct_lookup:
                    violations.append(f"{path}:{node.lineno}: {node.attr}")
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
                continue
            owner, attribute_name = node.args[:2]
            if not (
                isinstance(owner, ast.Name)
                and owner.id == "services"
                and isinstance(attribute_name, ast.Constant)
                and attribute_name.value in legacy_names
            ):
                continue
            violations.append(f"{path}:{node.lineno}: getattr({attribute_name.value})")

    assert violations == []


def test_selection_service_bundle_assembles_selection_controller_collaborators_explicitly() -> (
    None
):
    source = (APP_ROOT / "chemvas" / "ui" / "selection_service_bundle.py").read_text()

    assert "resolve_canvas_graph_service" not in source


def test_selection_graph_services_use_injected_graph_service() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "selection_hit_test_service.py",
        APP_ROOT / "chemvas" / "ui" / "selection_outline_service.py",
        APP_ROOT / "chemvas" / "ui" / "selection_structure_service.py",
    ]
    pattern = re.compile(
        r"\bresolve_canvas_graph_service\b"
        r"|canvas_service_for\([^,\n]+,\s*\"canvas_graph_service\""
        r"|graph_service=None"
    )

    assert _matching_lines(pattern, paths) == []


def test_graph_service_fallback_resolution_is_centralized() -> None:
    allowed_path = APP_ROOT / "chemvas" / "ui" / "canvas_graph_service.py"
    pattern = re.compile(
        r"\bdef _canvas_graph_service\b"
        r"|\bdef _canvas_graph_service_for\b"
        r"|CanvasGraphService\(\s*canvas\s*\)"
    )
    paths = [path for path in _app_python_files() if path != allowed_path]

    assert _matching_lines(pattern, paths) == []


def test_selection_highlight_styler_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "selection_highlight_context.py"
    styler = APP_ROOT / "chemvas" / "ui" / "selection_highlight_styler.py"
    pattern = re.compile(
        r"\bSelectionHighlightContext\b|\bselection_highlight_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [styler]) == []


def test_curved_arrow_path_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "curved_arrow_path_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "curved_arrow_path_service.py"
    pattern = re.compile(
        r"\bCurvedArrowPathContext\b|\bcurved_arrow_path_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_ring_fill_scene_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_ring_fill_scene_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "canvas_ring_fill_scene_service.py"
    pattern = re.compile(
        r"\bCanvasRingFillSceneContext\b|\bcanvas_ring_fill_scene_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_scene_decoration_build_service_does_not_use_context_facade() -> None:
    removed_context = (
        APP_ROOT / "chemvas" / "ui" / "canvas_scene_decoration_build_context.py"
    )
    service = APP_ROOT / "chemvas" / "ui" / "canvas_scene_decoration_build_service.py"
    pattern = re.compile(
        r"\bCanvasSceneDecorationBuildContext\b|\bcanvas_scene_decoration_build_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_scene_reset_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_scene_reset_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "canvas_scene_reset_service.py"
    pattern = re.compile(
        r"\bCanvasSceneResetContext\b"
        r"|\bcanvas_scene_reset_context_for\b"
        r"|self\.context\b"
        r"|\bcanvas_hit_testing_service_for\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_canvas_note_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_note_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_note_controller.py"
    pattern = re.compile(
        r"\bCanvasNoteContext\b"
        r"|\bcanvas_note_context_for\b"
        r"|self\.context\b"
        r"|\bselection_controller_for\b"
        r"|\bnote_controller_for\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [controller]) == []


def test_canvas_color_mutation_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_color_mutation_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "canvas_color_mutation_service.py"
    pattern = re.compile(
        r"\bCanvasColorMutationContext\b"
        r"|\bcanvas_color_mutation_context_for\b"
        r"|self\.context\b"
        r"|\bresolve_canvas_graph_service\b"
        r"|canvas_service_for\([^,\n]+,\s*\"canvas_graph_service\""
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_scene_decoration_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "scene_decoration_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "scene_decoration_service.py"
    pattern = re.compile(
        r"\bSceneDecorationContext\b|\bscene_decoration_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_canvas_mark_scene_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_mark_scene_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "canvas_mark_scene_service.py"
    pattern = re.compile(
        r"\bCanvasMarkSceneContext\b|\bcanvas_mark_scene_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_canvas_document_session_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_document_session_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "canvas_document_session_service.py"
    pattern = re.compile(
        r"\bCanvasDocumentSessionContext\b"
        r"|\bcanvas_document_session_context_for\b"
        r"|self\.context\b"
        r"|\bcanvas_hit_testing_service_for\b"
        r"|\bresolve_canvas_graph_service\b"
        r"|canvas_service_for\([^,\n]+,\s*\"structure_build_service\""
        r"|\bdef _structure_build_service\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_handle_mutation_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "handle_mutation_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "handle_mutation_service.py"
    pattern = re.compile(
        r"\bHandleMutationContext\b|\bhandle_mutation_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_canvas_move_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_move_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_move_controller.py"
    pattern = re.compile(
        r"\bCanvasMoveContext\b"
        r"|\bcanvas_move_context_for\b"
        r"|self\.context\b"
        r"|\bcanvas_hit_testing_service_for\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [controller]) == []


def test_canvas_geometry_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_geometry_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_geometry_controller.py"
    pattern = re.compile(
        r"\bCanvasGeometryContext\b"
        r"|\bcanvas_geometry_context_for\b"
        r"|self\.context\b"
        r"|\bcanvas_hit_testing_service_for\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [controller]) == []


def test_canvas_model_access_does_not_use_hit_testing_registry() -> None:
    module = APP_ROOT / "chemvas" / "ui" / "canvas_model_access.py"
    pattern = re.compile(r"\bcanvas_hit_testing_service_for\b")

    assert _matching_lines(pattern, [module]) == []


def test_canvas_model_access_delegates_model_storage_to_model_state() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "canvas_model_access.py"
    forbidden = re.compile(r"\bcanvas\.model\b")

    assert _matching_lines(forbidden, [access]) == []


def test_canvas_view_uses_model_state_for_model_creation() -> None:
    view = APP_ROOT / "chemvas" / "ui" / "canvas_view.py"
    source = view.read_text()

    assert "MoleculeModel" not in source


def test_rdkit_adapter_access_delegates_storage_to_rdkit_state() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "rdkit_adapter_access.py"
    forbidden = re.compile(r"\bcanvas\.rdkit\b")

    assert _matching_lines(forbidden, [access]) == []


def test_rdkit_async_jobs_store_running_jobs_in_state_module() -> None:
    source = (APP_ROOT / "chemvas" / "ui" / "rdkit_async_jobs.py").read_text()

    assert "_rdkit_export_jobs" not in source


def test_canvas_view_uses_rdkit_state_for_adapter_creation() -> None:
    view = APP_ROOT / "chemvas" / "ui" / "canvas_view.py"
    source = view.read_text()

    assert "RDKitAdapter" not in source


def test_bond_renderer_access_delegates_storage_to_bond_renderer_state() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "bond_renderer_access.py"
    forbidden = re.compile(r"\bcanvas\.bond_renderer\b")

    assert _matching_lines(forbidden, [access]) == []


def test_canvas_view_uses_bond_renderer_state_for_bond_renderer_creation() -> None:
    view = APP_ROOT / "chemvas" / "ui" / "canvas_view.py"
    source = view.read_text()

    assert "BondRenderer" not in source


def test_canvas_view_delegates_initialization_to_setup_module() -> None:
    view = APP_ROOT / "chemvas" / "ui" / "canvas_view.py"
    forbidden = re.compile(
        r"\bbuild_canvas_services\b"
        r"|\battach_canvas_runtime_state\b"
        r"|\battach_canvas_services\b"
        r"|\bset_sheet_setup_state_for\b"
        r"|\bmodel_for\b"
        r"|\brenderer_for\b"
        r"|\brdkit_adapter_for\b"
        r"|\bbond_renderer_for\b"
    )

    assert _matching_lines(forbidden, [view]) == []


def test_canvas_view_delegates_background_painting_to_painter_module() -> None:
    view = APP_ROOT / "chemvas" / "ui" / "canvas_view.py"
    forbidden = re.compile(r"\bQColor\b|\bQPen\b|\bsheet_rect_for\b")

    assert _matching_lines(forbidden, [view]) == []


def test_canvas_hit_testing_service_uses_injected_view_position_port() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "canvas_hit_testing_service.py"
    forbidden = re.compile(r"\bself\.canvas\.mapToScene\b|\bcanvas\.mapToScene\b")

    assert _matching_lines(forbidden, [service]) == []


def test_history_canvas_access_does_not_use_hit_testing_registry() -> None:
    module = APP_ROOT / "chemvas" / "ui" / "history_canvas_access.py"
    pattern = re.compile(r"\bcanvas_hit_testing_service_for\b")

    assert _matching_lines(pattern, [module]) == []


def test_history_canvas_access_uses_mark_registry_accessor() -> None:
    module = APP_ROOT / "chemvas" / "ui" / "history_canvas_access.py"
    forbidden = re.compile(
        r"\bcanvas\.mark_registry\b|\bhasattr\(\s*canvas\s*,\s*\"mark_registry\""
    )

    assert _matching_lines(forbidden, [module]) == []


def test_sheet_setup_access_delegates_sheet_values_to_sheet_setup_state() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "sheet_setup_access.py"
    forbidden = re.compile(
        r"\bcanvas\.sheet_size\b"
        r"|\bcanvas\.sheet_orientation\b"
        r"|\bcanvas\.setSceneRect\b"
        r"|\bcanvas\.viewport\("
    )

    assert _matching_lines(forbidden, [access]) == []


def test_structure_build_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "structure_build_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "structure_build_service.py"
    pattern = re.compile(
        r"\bStructureBuildContext\b|\bstructure_build_context_for\b|self\.context\b|self\.geometry\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_structure_build_service_delegates_bond_building() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "structure_build_service.py"
    pattern = re.compile(
        r"\bstyle_for_existing_bond_overlay\b"
        r"|\bcanvas_hit_testing_service_for\b"
        r"|\brecord_bond_update_for\b"
        r"|\bbond_state_dict\b"
        r"|\bmove_controller_for\b"
        r"|\bresolve_canvas_graph_service\b"
        r"|graph_service=None"
    )

    assert _matching_lines(pattern, [service]) == []


def test_structure_bond_build_service_uses_injected_hit_testing_service() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "structure_bond_build_service.py"
    pattern = re.compile(
        r"\bcanvas_hit_testing_service_for\b"
        r"|\bmove_controller_for\b"
        r"|\bdef find_atom_near\b"
        r"|\bresolve_canvas_graph_service\b"
        r"|graph_service=None"
    )

    assert _matching_lines(pattern, [service]) == []


def test_structure_build_service_delegates_benzene_building() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "structure_build_service.py"
    pattern = re.compile(
        r"\bplan_benzene_ring_points\b"
        r"|\bcompute_free_benzene_ring_points\b"
        r"|\balternating_ring_bond_specs\b"
        r"|\battach_scene_item\b"
    )

    assert _matching_lines(pattern, [service]) == []


def test_structure_build_service_delegates_template_building_without_wrapper_methods() -> (
    None
):
    service = APP_ROOT / "chemvas" / "ui" / "structure_build_service.py"
    tree = ast.parse(service.read_text())
    removed_wrappers = {
        "add_regular_ring_template",
        "add_hetero_ring_template",
        "add_fused_benzenes",
        "add_crown_ether",
        "add_cyclohexane_chair",
        "add_cyclohexane_boat",
        "add_indole",
        "add_quinoline",
        "add_isoquinoline",
        "add_benzimidazole",
        "add_phenyl",
        "add_benzyl",
        "add_vinyl",
        "add_allyl",
        "add_carboxyl",
        "add_nitro",
        "add_sulfonyl",
        "add_carbonyl",
        "add_tbu",
        "add_ipr",
        "add_me",
        "add_et",
        "add_peptide_2",
    }

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "StructureBuildService":
            method_names = {
                item.name for item in node.body if isinstance(item, ast.FunctionDef)
            }
            assert method_names.isdisjoint(removed_wrappers)
            break
    else:
        raise AssertionError("StructureBuildService class not found")


def test_structure_growth_build_service_uses_explicit_actions_instead_of_owner_facade() -> (
    None
):
    service = APP_ROOT / "chemvas" / "ui" / "structure_build_service.py"
    growth = APP_ROOT / "chemvas" / "ui" / "structure_growth_build_service.py"
    forbidden = re.compile(r"\bself\.owner\b|\bStructureGrowthBuildService\(self\)")

    assert _matching_lines(forbidden, [service, growth]) == []


def test_structure_insert_flow_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "structure_insert_context.py"
    paths = [
        APP_ROOT / "chemvas" / "ui" / "structure_insert_access.py",
        APP_ROOT / "chemvas" / "ui" / "structure_build_committer.py",
        APP_ROOT / "chemvas" / "ui" / "insert_commit_service.py",
        APP_ROOT / "chemvas" / "ui" / "structure_insert_service.py",
    ]
    pattern = re.compile(
        r"\bStructureInsertContext\b"
        r"|\bstructure_insert_context_for\b"
        r"|self\.context\b"
        r"|canvas_service_for\([^,\n]+,\s*\"canvas_graph_service\""
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, paths) == []


def test_insert_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "insert_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "insert_controller.py"
    pattern = re.compile(
        r"\bInsertContext\b"
        r"|\binsert_context_for\b"
        r"|self\.context\b"
        r"|\bcanvas_hit_testing_service_for\b"
        r"|\bresolve_canvas_graph_service\b"
        r"|canvas_service_for\([^,\n]+,\s*\"structure_build_service\""
        r"|\bdef _structure_build_service\b"
        r"|return InsertController\("
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [controller]) == []


def test_main_window_canvas_document_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "main_window_workbook_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "main_window_canvas_document_service.py"
    source = service.read_text()
    pattern = re.compile(
        r"\bMainWindowWorkbookContext\b"
        r"|\bmain_window_workbook_context_for\b"
        r"|self\.context\b"
        r"|\bwindow\.add_canvas\("
        r"|\bwindow\.canvas_tabs\b"
        r"|\bwindow\.canvas_tab_entries\("
        r"|\bwindow\.reset_canvas_name_counter\("
        r"|\bwindow\.active_canvas_tab_index\("
        r"|\bwindow\.canvas_count\("
    )

    assert not removed_context.exists()
    assert "window.refresh_active_canvas_ui()" not in source
    assert re.search(r"\bwindow\.canvas\b", source) is None
    assert _matching_lines(pattern, [service]) == []


def test_main_window_document_and_icon_services_do_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "main_window_context.py"
    paths = [
        APP_ROOT / "chemvas" / "ui" / "main_window_document_action_service.py",
        APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py",
    ]
    pattern = re.compile(
        r"\bMainWindowContext\b|\bmain_window_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, paths) == []


def test_main_window_icon_factory_delegates_canvas_style_access_to_port() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    port = APP_ROOT / "chemvas" / "ui" / "main_window_icon_canvas_style.py"
    factory_source = factory.read_text()
    port_source = port.read_text()

    assert "window.canvas" not in factory_source
    assert "self.window" not in factory_source
    assert "renderer_style_access" not in factory_source
    assert "ring_double_segments_for" not in factory_source
    assert "from chemvas.domain.document import Atom" not in factory_source
    assert "self._window.canvas" not in port_source


def test_main_window_icon_factory_delegates_hidpi_icon_rendering_to_pixmap_factory() -> (
    None
):
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text()

    assert "QPixmap" not in factory_source
    assert "QPainter" not in factory_source
    assert "QApplication" not in factory_source
    assert "devicePixelRatio()" not in factory_source


def test_main_window_icon_factory_delegates_pure_geometry_to_helper() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text()

    assert "from chemvas.ui.main_window_icon_geometry import" not in factory_source
    assert "def benzene_icon_polygon" not in factory_source
    assert "def template_preview_ring_sides" not in factory_source
    assert "def chair_icon_points" not in factory_source


def test_main_window_icon_factory_delegates_bond_drawing_to_renderer() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text()

    for icon_name in (
        "bond",
        "bond_double",
        "bond_triple",
        "wedge",
        "hash",
        "benzene",
        "bond_bold",
        "bond_dotted",
        "bond_length",
    ):
        assert f'self.make_design_icon("{icon_name}")' in factory_source
    assert "bold_bond_pen()" not in factory_source
    assert "hash_spacing_px()" not in factory_source
    assert "dotted_bond_pen()" not in factory_source


def test_main_window_icon_factory_delegates_arrow_drawing_to_renderer() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text()

    # Arrow previews/presets/controls now render through the shared SVG design
    # icon set rather than the per-shape QPainter renderer.
    assert "def draw_arrow_head" not in factory_source
    assert "quadTo(15, 6, 24, 15)" not in factory_source


def test_main_window_icon_factory_delegates_template_drawing_to_renderer() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text()

    # Template ring previews now resolve to shared SVG design icons by label.
    assert "template_preview_ring_polygon" not in factory_source
    assert "template_preview_ring_sides" not in factory_source
    assert "chair_icon_points" not in factory_source


def test_main_window_icon_factory_delegates_utility_drawing_to_renderer() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    utility_icons = APP_ROOT / "chemvas" / "ui" / "main_window_utility_icon_renderer.py"
    factory_source = factory.read_text()
    utility_icons_source = utility_icons.read_text()

    for icon_name in (
        "undo",
        "redo",
        "save",
        "open",
        "panel_right",
        "canvas",
        "sheet",
        "info",
    ):
        assert f'self.make_design_icon("{icon_name}")' in factory_source
    for icon_name in (
        "undo",
        "redo",
        "save",
        "open",
        "preview_panel",
        "add_canvas",
        "setup_sheet",
        "info",
    ):
        assert f"def draw_{icon_name}" in utility_icons_source

    assert "drawRect(7, 8, 10, 12)" not in factory_source
    assert "drawLine(QPointF(15.0, 5.0), QPointF(15.0, 17.5))" not in factory_source
    assert "drawEllipse(7, 7, 16, 16)" not in factory_source


def test_main_window_icon_factory_delegates_tool_drawing_to_renderer() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text()

    for icon_name in (
        "atom",
        "flip_h",
        "flip_v",
        "bracket",
        "orbital",
        "color",
        "perspective",
        "circled_plus",
        "circled_minus",
        "atom_orbit",
        "plus",
        "minus",
        "radical",
        "ring_fill",
    ):
        assert f'self.make_design_icon("{icon_name}")' in factory_source
    assert factory_source.count('self.make_design_icon("move")') >= 2
    # Orbital and bracket previews now resolve to shared SVG design icons.

    assert "QPainterPath" not in factory_source
    assert "QFont" not in factory_source
    assert "math." not in factory_source
    assert "drawText(QRectF(10.0, 8.0, 12.0, 8.0)" not in factory_source
    assert "drawLine(15, 7, 15, 23)" not in factory_source


def test_main_window_canvas_tab_services_do_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "main_window_canvas_tab_context.py"
    paths = [
        APP_ROOT / "chemvas" / "ui" / "main_window_canvas_document_service.py",
        APP_ROOT / "chemvas" / "ui" / "main_window_canvas_tab_ui_service.py",
        APP_ROOT / "chemvas" / "ui" / "main_window_active_canvas_ui_service.py",
    ]
    pattern = re.compile(
        r"\bMainWindowCanvasTabContext\b|\bmain_window_canvas_tab_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, paths) == []


def test_scene_item_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "scene_item_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "scene_item_controller.py"
    pattern = re.compile(
        r"\bSceneItemContext\b"
        r"|\bscene_item_context_for\b"
        r"|self\.context\b"
        r"|\bresolve_canvas_graph_service\b"
        r"|canvas_service_for\([^,\n]+,\s*\"canvas_graph_service\""
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [controller]) == []


def test_scene_item_controller_delegates_lifecycle_registry_work_to_service() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "scene_item_controller.py"
    lifecycle_service = APP_ROOT / "chemvas" / "ui" / "scene_item_lifecycle_service.py"
    controller_source = controller.read_text()
    lifecycle_source = lifecycle_service.read_text()

    for forbidden in (
        "append_scene_item_for",
        "remove_scene_item_from_collection_for",
        "remove_mark_item_for",
        "remove_attached_item_from_canvas_scene",
        "_add_item_with_attach_ports",
        "handle_target_for",
    ):
        assert forbidden not in controller_source
        assert forbidden in lifecycle_source


def test_scene_ops_controller_context_facade_removed() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "scene_ops_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "scene_ops_controller.py"
    pattern = re.compile(
        r"\bSceneOpsContext\b"
        r"|\bscene_ops_context_for\b"
        r"|\bSceneOpsController\b"
    )

    assert not removed_context.exists()
    assert not controller.exists()
    assert _matching_lines(pattern, _app_python_files()) == []


def test_clipboard_details_live_in_scene_clipboard_controller() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "scene_ops_controller.py"

    assert not controller.exists()


def test_scene_clipboard_controller_delegates_copy_paste_workflows_to_services() -> (
    None
):
    controller = APP_ROOT / "chemvas" / "ui" / "scene_clipboard_controller.py"
    controller_source = controller.read_text()

    for forbidden in (
        "build_clipboard_copy_plan",
        "build_clipboard_paste_plan",
        "build_clipboard_mime_data",
        "visible_canvas_items_to_hide_for_copy",
        "apply_paste_payload",
        "record_additions_for",
        "clipboard_copy_cache_values",
        "translated_scene_item_state",
    ):
        assert forbidden not in controller_source


def test_delete_details_live_in_scene_delete_controller() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "scene_ops_controller.py"

    assert not controller.exists()


def test_transform_details_live_in_scene_transform_controller() -> None:
    controller = APP_ROOT / "chemvas" / "ui" / "scene_ops_controller.py"

    assert not controller.exists()


def test_scene_transform_logic_is_compat_reexport_only() -> None:
    compat = APP_ROOT / "chemvas" / "ui" / "scene_transform_logic.py"
    app_paths = [path for path in _app_python_files() if path != compat]
    import_pattern = re.compile(
        r"\bfrom ui\.scene_transform_logic import\b|\bimport ui\.scene_transform_logic\b"
    )
    source = compat.read_text()

    assert "def flip_scene_item_state" not in source
    assert "class TransformSelectionGroups" not in source
    assert _matching_lines(import_pattern, app_paths) == []


def test_canvas_handle_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_handle_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_handle_controller.py"
    pattern = re.compile(
        r"\bCanvasHandleContext\b|\bcanvas_handle_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [controller]) == []


def test_rotation_preview_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_rotation_preview_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_rotation_preview_controller.py"
    pattern = re.compile(
        r"\bCanvasRotationPreviewContext\b|\bcanvas_rotation_preview_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [controller]) == []


def test_handle_overlay_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "handle_overlay_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "handle_overlay_service.py"
    pattern = re.compile(
        r"\bHandleOverlayContext\b|\bhandle_overlay_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_selection_rotation_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "selection_rotation_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "selection_rotation_controller.py"
    access = APP_ROOT / "chemvas" / "ui" / "selection_rotation_access.py"
    pattern = re.compile(
        r"\bSelectionRotationContext\b"
        r"|\bselection_rotation_context_for\b"
        r"|self\.context\b"
        r"|\bmove_controller_for\b"
        r"|canvas_service_for\([^,\n]+,\s*\"canvas_graph_service\""
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [controller, access]) == []


def test_selection_rotation_planarity_owns_planar_graph_helpers() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "selection_rotation_access.py"
    access_source = access.read_text()

    assert "edge_has_reachable_alternative_path" not in access_source


def test_canvas_atom_mutation_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_atom_mutation_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "canvas_atom_mutation_service.py"
    pattern = re.compile(
        r"\bCanvasAtomMutationContext\b"
        r"|\bcanvas_atom_mutation_context_for\b"
        r"|self\.context\b"
        r"|\bcanvas_hit_testing_service_for\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_canvas_bond_mutation_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_bond_mutation_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "canvas_bond_mutation_service.py"
    pattern = re.compile(
        r"\bCanvasBondMutationContext\b"
        r"|\bcanvas_bond_mutation_context_for\b"
        r"|self\.context\b"
        r"|\bcanvas_hit_testing_service_for\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_bond_renderer_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "bond_render_context.py"
    renderer = APP_ROOT / "chemvas" / "ui" / "bond_renderer.py"
    pattern = re.compile(
        r"\bBondRenderContext\b|\bbond_render_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [renderer]) == []


def test_bond_line_geometry_delegates_special_glyph_geometry() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "bond_line_geometry_service.py"
    forbidden = re.compile(
        r"\baddEllipse\b|\bQPolygonF\(\[|\bt_positions\b|\bt_sizes\b"
    )

    assert _matching_lines(forbidden, [service]) == []


def test_canvas_input_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_input_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_input_controller.py"
    pattern = re.compile(
        r"\bCanvasInputContext\b|\bcanvas_input_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [controller]) == []


def test_canvas_pointer_flow_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_pointer_context.py"
    pointer_controller = APP_ROOT / "chemvas" / "ui" / "canvas_pointer_controller.py"
    pointer_context_pattern = re.compile(
        r"\bCanvasPointerContext\b|\bcanvas_pointer_context_for\b|self\.context\b"
    )
    perspective_controller = (
        APP_ROOT / "chemvas" / "ui" / "perspective_tool_controller.py"
    )
    removed_context_pattern = re.compile(
        r"\bCanvasPointerContext\b|\bcanvas_pointer_context_for\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pointer_context_pattern, [pointer_controller]) == []
    assert _matching_lines(removed_context_pattern, [perspective_controller]) == []


def test_canvas_pointer_controller_uses_injected_ports() -> None:
    pointer_controller = APP_ROOT / "chemvas" / "ui" / "canvas_pointer_controller.py"
    pattern = re.compile(
        r"\bcanvas_hit_testing_service_for\b"
        r"|\binsert_controller_for\b"
        r"|\bhover_interaction_service_for\b"
        r"|\bactive_tool_for\b"
        r"|\bdef _hit_testing_service\b"
        r"|\bdef _insert_controller\b"
        r"|\bdef _hover_interaction_service\b"
        r"|\bdef _active_tool\b"
    )

    assert _matching_lines(pattern, [pointer_controller]) == []


def test_input_pointer_and_shortcut_controllers_use_explicit_service_ports() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "canvas_input_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_pointer_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_chemdraw_shortcut_service.py",
    ]
    pattern = re.compile(
        r"\bdef _canvas_service_or_none\b"
        r"|\b_canvas_service_or_none\("
        r"|scene_ops_controller"
        r"|tool_mode_controller=None"
        r"|\bCanvasToolModeController\b"
    )

    assert _matching_lines(pattern, paths) == []


def test_perspective_tool_controller_requires_injected_tool_context() -> None:
    source = (
        APP_ROOT / "chemvas" / "ui" / "perspective_tool_controller.py"
    ).read_text()

    assert "ToolContext(" not in source
    assert "hit_testing_service=" not in source
    assert "selection_controller=" not in source
    assert "context or" not in source


def test_canvas_hit_testing_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_hit_testing_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "canvas_hit_testing_service.py"
    pattern = re.compile(
        r"\bCanvasHitTestingContext\b|\bcanvas_hit_testing_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_canvas_chemdraw_shortcut_service_does_not_use_context_facade() -> None:
    removed_context = (
        APP_ROOT / "chemvas" / "ui" / "canvas_chemdraw_shortcut_context.py"
    )
    service = APP_ROOT / "chemvas" / "ui" / "canvas_chemdraw_shortcut_service.py"
    pattern = re.compile(
        r"\bCanvasChemDrawShortcutContext\b|\bcanvas_chemdraw_shortcut_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_canvas_history_recording_flow_does_not_use_context_facade() -> None:
    removed_context = (
        APP_ROOT / "chemvas" / "ui" / "canvas_history_recording_context.py"
    )
    paths = [
        APP_ROOT / "chemvas" / "ui" / "canvas_history_recording_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_document_state.py",
        APP_ROOT / "chemvas" / "ui" / "insert_smiles_transaction.py",
    ]
    pattern = re.compile(
        r"\bCanvasHistoryRecordingContext\b|\bcanvas_history_recording_context_for\b|self\.context\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, paths) == []


def test_atom_label_service_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "atom_label_context.py"
    service = APP_ROOT / "chemvas" / "ui" / "atom_label_service.py"
    pattern = re.compile(
        r"\bAtomLabelContext\b"
        r"|\batom_label_context_for\b"
        r"|self\.context\b"
        r"|\bmove_controller_for\b"
    )

    assert not removed_context.exists()
    assert _matching_lines(pattern, [service]) == []


def test_production_code_does_not_use_canvas_instance_attrs_helper() -> None:
    pattern = re.compile(r"\bcanvas_instance_attrs\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_canvas_service_access_does_not_use_dynamic_private_attr_fallbacks() -> None:
    service_access = APP_ROOT / "chemvas" / "ui" / "canvas_service_access.py"
    pattern = re.compile(
        r"\b(?:getattr|setattr)\(\s*canvas\s*,\s*_legacy_attr_for"
        r"|canvas_instance_attrs\(\s*canvas\s*\)\[[^\]]*_legacy_attr_for"
    )

    assert _matching_lines(pattern, [service_access]) == []


def test_graph_service_accessor_does_not_attach_missing_services() -> None:
    graph_service = APP_ROOT / "chemvas" / "ui" / "canvas_graph_service.py"
    pattern = re.compile(r"\bcanvas\.services\s*=|\bservices\.canvas_graph_service\s*=")

    assert _matching_lines(pattern, [graph_service]) == []


def test_production_code_does_not_use_legacy_graph_canvas_private_wrappers() -> None:
    pattern = re.compile(
        r"\._(?:bond_id_between|bond_exists|expand_connected_atoms|connected_components|component_without_bond)\b"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_history_service_accessor_does_not_create_or_bridge_missing_services() -> None:
    history_service = APP_ROOT / "chemvas" / "ui" / "canvas_history_service.py"
    pattern = re.compile(
        r"\bCanvasHistoryCommandSink\b|\bpush_command\b|\breturn CanvasHistoryService\("
    )

    assert _matching_lines(pattern, [history_service]) == []


def test_history_service_accessor_does_not_accept_direct_canvas_aliases() -> None:
    history_service = APP_ROOT / "chemvas" / "ui" / "canvas_history_service.py"
    pattern = re.compile(r"\bgetattr\(\s*canvas\s*,\s*\"history_service\"")

    assert _matching_lines(pattern, [history_service]) == []


def test_generic_canvas_context_cache_is_removed() -> None:
    removed_cache = APP_ROOT / "chemvas" / "ui" / "canvas_context_cache.py"
    pattern = re.compile(
        r"\bcanvas_context_cache_for\b|\bcanvas_context_for\b|\bcontext_cache_for\b|\bruntime_context_for\b"
    )

    assert not removed_cache.exists()
    assert _matching_lines(pattern, _app_python_files()) == []


def test_canvas_runtime_state_attach_does_not_mirror_runtime_services_to_canvas() -> (
    None
):
    runtime_state = APP_ROOT / "chemvas" / "ui" / "canvas_runtime_state.py"
    pattern = re.compile(r"\bcanvas\.(?:history_service|contexts)\s*=")

    assert _matching_lines(pattern, [runtime_state]) == []


def test_optional_canvas_service_lookup_helper_removed_from_production_code() -> None:
    pattern = re.compile(r"\boptional_canvas_service_for\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_runtime_service_lookup_helpers_removed_from_production_code() -> None:
    pattern = re.compile(
        r"\b(?:optional_canvas_runtime_service_for|canvas_runtime_service_for)\b"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_production_code_does_not_store_service_collaborators_as_private_fields() -> (
    None
):
    pattern = re.compile(
        r"(^|[,( ]|\.)_[A-Za-z0-9_]+_(?:service|controller|styler)\s*="
        r"|\._[A-Za-z0-9_]+_(?:service|controller|styler)\s*="
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_production_code_does_not_fallback_to_removed_canvas_method_aliases() -> None:
    removed_aliases = (
        "add_mark_for_atom",
        "apply_color_to_item",
        "clear_handles",
        "emit_selection_info",
        "refresh_hover_from_cursor",
        "refresh_selection_outline",
        "restore_selection_from_ids",
        "select_note",
    )
    alias_names = "|".join(re.escape(name) for name in removed_aliases)
    pattern = re.compile(
        rf"\bgetattr\(\s*(?:canvas|self\.canvas)\s*,\s*\"(?:{alias_names})\""
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_production_code_does_not_fallback_to_canvas_state_collection_aliases() -> None:
    removed_aliases = ("selected_notes",)
    alias_names = "|".join(re.escape(name) for name in removed_aliases)
    pattern = re.compile(
        rf"\bgetattr\(\s*(?:canvas|self\.canvas)\s*,\s*\"(?:{alias_names})\""
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_production_code_uses_tools_service_instead_of_canvas_tools_alias() -> None:
    pattern = re.compile(
        r"\b(?:canvas|self\.canvas)\.tools\b"
        r"|\bgetattr\(\s*(?:canvas|self\.canvas)\s*,\s*\"tools\""
        r"|\bcanvas\.tools\s*="
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_production_code_uses_atom_graphics_accessors_instead_of_canvas_alias_fallbacks() -> (
    None
):
    pattern = re.compile(
        r"\bgetattr\(\s*(?:canvas|self\.canvas)\s*,\s*\"(?:atom_items|atom_dots)\""
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_hover_state_accessor_stays_a_thin_runtime_state_leaf() -> None:
    hover_state = APP_ROOT / "chemvas" / "ui" / "canvas_hover_state.py"
    tree = ast.parse(hover_state.read_text())
    classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    functions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    pattern = re.compile(
        r"\b(?:ensure_canvas_state|canvas_state_mirror|sync_canvas_attr_map)\b"
        r"|\b(?:getattr|setattr)\(\s*canvas\b"
        r"|\b(?:CanvasHoverState|HoverPreviewState|HOVER_STATE_ATTR_MAP)\b"
        r"|\b(?:append|extend|set)_hover_(?:item|items|atom_id|bond_id)_for\b"
    )

    assert classes == []
    assert functions == ["hover_state_for"]
    assert _matching_lines(pattern, [hover_state]) == []


def test_renderer_style_access_requires_explicit_renderer_collaborator() -> None:
    renderer_style_access = APP_ROOT / "chemvas" / "ui" / "renderer_style_access.py"
    pattern = re.compile(
        r"\bgetattr\(\s*canvas\s*,\s*\"renderer\"|\bcanvas\.renderer\b"
    )

    assert _matching_lines(pattern, [renderer_style_access]) == []


def test_tool_settings_state_accessor_does_not_read_legacy_canvas_attrs() -> None:
    tool_settings_state = APP_ROOT / "chemvas" / "ui" / "canvas_tool_settings_state.py"
    pattern = re.compile(
        r"\bcanvas_state_mirror\b|\brefresh_state_from_canvas_attrs\b|\bsync_canvas_attrs\b|\bsync_canvas_attr\b"
    )

    assert _matching_lines(pattern, [tool_settings_state]) == []


def test_smiles_input_state_accessor_does_not_read_legacy_canvas_attrs() -> None:
    smiles_input_state = APP_ROOT / "chemvas" / "ui" / "canvas_smiles_input_state.py"
    pattern = re.compile(
        r"\bcanvas_state_mirror\b|\brefresh_state_from_canvas_attrs\b|\bsync_canvas_attrs\b|\bsync_canvas_attr\b"
    )

    assert _matching_lines(pattern, [smiles_input_state]) == []


def test_text_style_state_accessor_does_not_read_legacy_canvas_attrs() -> None:
    text_style_state = APP_ROOT / "chemvas" / "ui" / "canvas_text_style_state.py"
    pattern = re.compile(
        r"\bcanvas_state_mirror\b|\brefresh_state_from_canvas_attrs\b|\bsync_canvas_attrs\b|\bsync_canvas_attr\b"
    )

    assert _matching_lines(pattern, [text_style_state]) == []


def test_atom_coords_state_accessor_does_not_read_legacy_canvas_attrs() -> None:
    atom_coords_access = APP_ROOT / "chemvas" / "ui" / "atom_coords_access.py"
    pattern = re.compile(
        r"\bcanvas_state_mirror\b|\brefresh_state_from_canvas_attrs\b|\bsync_canvas_attrs\b|\bsync_canvas_attr\b"
    )

    assert _matching_lines(pattern, [atom_coords_access]) == []


def test_atom_graphics_state_accessor_does_not_read_legacy_canvas_attrs() -> None:
    atom_graphics_state = APP_ROOT / "chemvas" / "ui" / "canvas_atom_graphics_state.py"
    pattern = re.compile(
        r"\bcanvas_state_mirror\b|\brefresh_state_from_canvas_attrs\b|\bsync_canvas_attrs\b|\bsync_canvas_attr\b"
    )

    assert _matching_lines(pattern, [atom_graphics_state]) == []


def test_bond_graphics_state_accessor_does_not_read_legacy_canvas_attrs() -> None:
    bond_graphics_state = APP_ROOT / "chemvas" / "ui" / "canvas_bond_graphics_state.py"
    pattern = re.compile(
        r"\bcanvas_state_mirror\b|\brefresh_state_from_canvas_attrs\b|\bsync_canvas_attrs\b|\bsync_canvas_attr\b"
    )

    assert _matching_lines(pattern, [bond_graphics_state]) == []


def test_scene_items_state_accessor_does_not_read_legacy_canvas_attrs() -> None:
    scene_items_state = APP_ROOT / "chemvas" / "ui" / "canvas_scene_items_state.py"
    pattern = re.compile(
        r"\bcanvas_state_mirror\b|\brefresh_state_from_canvas_attrs\b|\bsync_canvas_attrs\b|\bsync_canvas_attr\b"
    )

    assert _matching_lines(pattern, [scene_items_state]) == []


def test_selection_outline_state_accessor_does_not_read_legacy_canvas_attrs() -> None:
    selection_outline_state = APP_ROOT / "chemvas" / "ui" / "selection_outline_state.py"
    pattern = re.compile(
        r"\bcanvas_state_mirror\b|\brefresh_state_from_canvas_attr_map\b|\bsync_canvas_attr\b"
    )

    assert _matching_lines(pattern, [selection_outline_state]) == []


def test_mark_registry_accessor_does_not_read_legacy_canvas_marks_attr() -> None:
    mark_registry = APP_ROOT / "chemvas" / "ui" / "canvas_mark_registry.py"
    pattern = re.compile(
        r"\bCanvasMarkRegistryAdapter\b|\b_marks_by_atom\b|\bMARKS_BY_ATOM_ATTR\b"
    )

    assert _matching_lines(pattern, [mark_registry]) == []


def test_canvas_state_lookup_does_not_read_legacy_private_state_attrs() -> None:
    state_lookup = APP_ROOT / "chemvas" / "ui" / "canvas_state_lookup.py"
    pattern = re.compile(
        r"\blegacy_name\b|f\"_\{name\}\"|getattr\(\s*canvas\s*,\s*[^)]*legacy"
    )

    assert _matching_lines(pattern, [state_lookup]) == []


def test_canvas_state_lookup_does_not_promote_legacy_private_state_to_public_attrs() -> (
    None
):
    state_lookup = APP_ROOT / "chemvas" / "ui" / "canvas_state_lookup.py"
    pattern = re.compile(r"\bsetattr\(\s*canvas\s*,\s*public_name\s*,")

    assert _matching_lines(pattern, [state_lookup]) == []


def test_canvas_state_lookup_prefers_runtime_state_over_public_state_aliases() -> None:
    state_lookup = APP_ROOT / "chemvas" / "ui" / "canvas_state_lookup.py"
    tree = ast.parse(state_lookup.read_text())
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "canvas_state_object"
    )
    getattr_lines: list[tuple[str, int]] = []

    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
            continue
        if len(node.args) < 2:
            continue
        target, attr = node.args[:2]
        if isinstance(target, ast.Name) and target.id == "canvas":
            if isinstance(attr, ast.Constant) and attr.value == "runtime_state":
                getattr_lines.append(("runtime_state", node.lineno))
            elif isinstance(attr, ast.Name) and attr.id == "public_name":
                getattr_lines.append(("public_name", node.lineno))

    runtime_line = next(line for name, line in getattr_lines if name == "runtime_state")
    public_line = next(line for name, line in getattr_lines if name == "public_name")
    assert runtime_line < public_line


def test_state_accessors_do_not_refresh_existing_state_from_canvas_attrs() -> None:
    pattern = re.compile(
        r"if state is not None:\s*"
        r"(?:\n\s*)+refresh_state_from_canvas_(?:attrs|attr_map)\("
    )
    matches = [
        str(path.relative_to(APP_ROOT.parents[0]))
        for path in _app_python_files()
        if pattern.search(path.read_text())
    ]

    assert matches == []


def test_tool_context_is_not_reintroduced_with_canvas_state_attr_fallbacks() -> None:
    tool_context = APP_ROOT / "chemvas" / "ui" / "tool_context.py"
    assert tool_context.exists()

    state_attr_names = (
        "hover_atom_id",
        "hover_bond_id",
        "active_bond_style",
        "active_bond_order",
        "snap_angle_step",
        "active_arrow_type",
        "active_bracket_type",
    )
    attr_names = "|".join(re.escape(name) for name in state_attr_names)
    pattern = re.compile(
        rf"getattr\(\s*self\.canvas\s*,\s*\"(?:__dict__|{attr_names})\""
        rf"|self\.canvas\.(?:{attr_names})\b"
    )

    assert _matching_lines(pattern, [tool_context]) == []


def test_tool_context_requires_explicit_ports_without_service_lookup() -> None:
    tool_context = APP_ROOT / "chemvas" / "ui" / "tool_context.py"
    source = tool_context.read_text()
    pattern = re.compile(
        r"\bcanvas_hit_testing_service_for\b"
        r"|\bselection_controller_for\b"
        r"|\bnote_controller_for\b"
        r"|\bhandle_controller_for\b"
        r"|\bdef hit_testing_service\b"
        r"|\bdef selection_controller\b"
        r"|\bdef note_controller\b"
        r"|\bdef handle_controller\b"
        r"|\bhit_testing_port\b"
        r"|\bselection_port\b"
        r"|\bnote_port\b"
        r"|\bhandle_port\b"
        r"|\b_call_port_then_canvas\b"
        r"|\b_callable_attr\(\s*self\.canvas\s*,"
        r"|\bself\.canvas\.(?:scene_pos_from_event|mapToScene|item_at_event|selection_hit_test|get_atom_symbol)"
        r"|\bself\.canvas\.scene\("
    )

    for port_name in (
        "hit_testing_service",
        "selection_controller",
        "note_controller",
        "handle_controller",
    ):
        assert port_name in source
    assert _matching_lines(pattern, [tool_context]) == []


def test_tool_context_factory_is_not_app_surface() -> None:
    assert not (APP_ROOT / "chemvas" / "ui" / "tool_context_factory.py").exists()


def test_tool_base_does_not_read_canvas_services_directly() -> None:
    tool_base = APP_ROOT / "chemvas" / "ui" / "tool_base.py"
    pattern = re.compile(
        r"\bgetattr\(\s*canvas\s*,\s*\"services\""
        r"|\bcanvas\.services\b"
        r"|\bToolContext\("
        r"|\btool_context_for_canvas\b"
    )

    assert _matching_lines(pattern, [tool_base]) == []


def test_tool_modules_use_tool_context_for_hit_testing_and_selection_ports() -> None:
    paths = [
        APP_ROOT / "chemvas" / "ui" / "benzene_tool.py",
        APP_ROOT / "chemvas" / "ui" / "bond_tool.py",
        APP_ROOT / "chemvas" / "ui" / "text_tool.py",
        APP_ROOT / "chemvas" / "ui" / "preview_tools.py",
        APP_ROOT / "chemvas" / "ui" / "interaction_tools.py",
        APP_ROOT / "chemvas" / "ui" / "edit_tools.py",
        APP_ROOT / "chemvas" / "ui" / "move_tool.py",
        APP_ROOT / "chemvas" / "ui" / "perspective_tool.py",
        APP_ROOT / "chemvas" / "ui" / "rotate_tool.py",
        APP_ROOT / "chemvas" / "ui" / "select_tool.py",
        APP_ROOT / "chemvas" / "ui" / "selection_drag_tool.py",
        APP_ROOT / "chemvas" / "ui" / "tool_controller.py",
    ]
    forbidden_direct_lookup = re.compile(
        r"\bcanvas_hit_testing_service_for\b"
        r"|\bselection_controller_for\b"
        r"|canvas_service_for\([^,\n]+,\s*\"canvas_graph_service\""
        r"|canvas_service_for\([^,\n]+,\s*\"style_controller\""
    )
    tool_context = APP_ROOT / "chemvas" / "ui" / "tool_context.py"
    context_usage = re.compile(r"\bself\.context\b|\bToolContext\b")

    assert _matching_lines(forbidden_direct_lookup, paths) == []
    assert _matching_lines(context_usage, [tool_context] + paths) != []


def test_perspective_tool_controller_does_not_reintroduce_context_delegate_wrappers() -> (
    None
):
    controller = APP_ROOT / "chemvas" / "ui" / "perspective_tool_controller.py"
    forbidden_methods = {
        "_scene_pos_from_event",
        "_item_at_event",
        "_preferred_structure_item_at_scene_pos",
        "_selection_hit_test",
        "_select_structure_for_item",
    }
    tree = ast.parse(controller.read_text())
    private_methods: set[str] = set()
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.ClassDef)
            or node.name != "PerspectiveToolController"
        ):
            continue
        private_methods = {
            child.name for child in node.body if isinstance(child, ast.FunctionDef)
        }
        break

    assert private_methods.isdisjoint(forbidden_methods)


def test_tools_module_is_reexport_only() -> None:
    source = (APP_ROOT / "chemvas" / "ui" / "tools.py").read_text()
    class_names = re.findall(
        r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\b", source, flags=re.MULTILINE
    )

    assert class_names == []


def test_production_code_imports_concrete_tool_modules_not_tools_reexport() -> None:
    pattern = re.compile(r"\bfrom ui\.tools import\b|\bimport ui\.tools\b")
    paths = [
        path
        for path in _app_python_files()
        if path != APP_ROOT / "chemvas" / "ui" / "tools.py"
    ]

    assert _matching_lines(pattern, paths) == []


def test_graph_algorithms_are_canvas_free() -> None:
    graph_modules = [
        APP_ROOT / "chemvas" / "ui" / "graph_algorithms.py",
        APP_ROOT / "chemvas" / "ui" / "graph_index_operations.py",
        APP_ROOT / "chemvas" / "ui" / "graph_rotation_policy.py",
    ]
    pattern = re.compile(r"\bcanvas\b|\bfrom ui\.|\bimport ui\.")

    assert _matching_lines(pattern, graph_modules) == []


def test_rotation_preview_context_does_not_mirror_legacy_private_group_state() -> None:
    rotation_preview_context = (
        APP_ROOT / "chemvas" / "ui" / "canvas_rotation_preview_state.py"
    )
    pattern = re.compile(r"\b_rotation_group\b|\b_rotation_preview_context\b")

    assert _matching_lines(pattern, [rotation_preview_context]) == []


def test_production_window_helpers_do_not_reach_into_window_private_members() -> None:
    allowed_paths = {
        APP_ROOT / "chemvas" / "ui" / "main_window_ports.py",
    }
    main_window_files = sorted(
        path
        for path in APP_ROOT.glob("ui/main_window*.py")
        if path not in allowed_paths
    )
    pattern = re.compile(
        r"\b(?:window|self\.window)\._"
        r"|vars\(\s*window\s*\)\[\s*\"_[A-Za-z]"
        r"|getattr\(\s*window\s*,\s*\"_[A-Za-z]"
        r"|setattr\(\s*window\s*,\s*\"_[A-Za-z]"
    )

    assert _matching_lines(pattern, main_window_files) == []


# --- Dependency contracts ------------------------------------------------


def _static_app_import_graph() -> dict[str, set[str]]:
    module_paths: dict[str, Path] = {}
    for path in _app_python_files():
        relative = path.relative_to(APP_ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        module_paths[".".join(parts)] = path

    graph = {module: set() for module in module_paths}
    for module, path in module_paths.items():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package = (
                        module
                        if path.name == "__init__.py"
                        else module.rpartition(".")[0]
                    )
                    package_parts = package.split(".") if package else []
                    keep_count = max(0, len(package_parts) - node.level + 1)
                    imported_parts = package_parts[:keep_count]
                    if node.module:
                        imported_parts.extend(node.module.split("."))
                    imported_from = ".".join(imported_parts)
                else:
                    imported_from = node.module or ""
                candidates.append(imported_from)
                candidates.extend(
                    f"{imported_from}.{alias.name}"
                    for alias in node.names
                    if imported_from
                )
            graph[module].update(
                candidate
                for candidate in candidates
                if candidate in module_paths and candidate != module
            )
    return graph


def _static_top_level_app_import_graph() -> dict[str, set[str]]:
    """Return eager module dependencies, excluding lazy/type-only imports.

    The broader graph above intentionally includes imports nested under
    ``TYPE_CHECKING`` and inside functions.  Those relationships are useful for
    local dependency contracts, while this graph protects import-time startup
    from real cycles during the package migration.
    """
    module_paths: dict[str, Path] = {}
    for path in _app_python_files():
        relative = path.relative_to(APP_ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        module_paths[".".join(parts)] = path

    def eager_imports(statements: list[ast.stmt]) -> list[ast.Import | ast.ImportFrom]:
        imports: list[ast.Import | ast.ImportFrom] = []
        for statement in statements:
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                imports.append(statement)
                continue
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(statement, ast.If) and (
                (
                    isinstance(statement.test, ast.Name)
                    and statement.test.id == "TYPE_CHECKING"
                )
                or (
                    isinstance(statement.test, ast.Attribute)
                    and isinstance(statement.test.value, ast.Name)
                    and statement.test.value.id == "typing"
                    and statement.test.attr == "TYPE_CHECKING"
                )
            ):
                imports.extend(eager_imports(statement.orelse))
                continue
            child_statements = [
                child
                for child in ast.iter_child_nodes(statement)
                if isinstance(child, ast.stmt)
            ]
            imports.extend(eager_imports(child_statements))
        return imports

    graph = {module: set() for module in module_paths}
    for module, path in module_paths.items():
        tree = ast.parse(path.read_text())
        for node in eager_imports(tree.body):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package = (
                        module
                        if path.name == "__init__.py"
                        else module.rpartition(".")[0]
                    )
                    package_parts = package.split(".") if package else []
                    keep_count = max(0, len(package_parts) - node.level + 1)
                    imported_parts = package_parts[:keep_count]
                    if node.module:
                        imported_parts.extend(node.module.split("."))
                    candidates.append(".".join(imported_parts))
                else:
                    candidates.append(node.module or "")
            graph[module].update(
                candidate
                for candidate in candidates
                if candidate in module_paths and candidate != module
            )
    return graph


def _strongly_connected_components(
    graph: dict[str, set[str]],
) -> list[set[str]]:
    next_index = 0
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []

    def visit(module: str) -> None:
        nonlocal next_index
        indices[module] = next_index
        low_links[module] = next_index
        next_index += 1
        stack.append(module)
        on_stack.add(module)

        for dependency in graph[module]:
            if dependency not in indices:
                visit(dependency)
                low_links[module] = min(
                    low_links[module],
                    low_links[dependency],
                )
            elif dependency in on_stack:
                low_links[module] = min(
                    low_links[module],
                    indices[dependency],
                )

        if low_links[module] != indices[module]:
            return
        component: set[str] = set()
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.add(member)
            if member == module:
                break
        components.append(component)

    for module in graph:
        if module not in indices:
            visit(module)
    return components


def test_history_transaction_dependency_cluster_stays_acyclic() -> None:
    graph = _static_app_import_graph()
    protected_modules = {
        "chemvas.ui.canvas_delete_transaction",
        "chemvas.ui.history_atom_position_restore",
        "chemvas.ui.history_canvas_access",
        "chemvas.ui.history_commands",
        "chemvas.domain.transactions.history_authority",
        "chemvas.domain.transactions.recovery",
    }
    assert protected_modules <= set(graph)
    cyclic_components = [
        sorted(component)
        for component in _strongly_connected_components(graph)
        if len(component) > 1 and component & protected_modules
    ]

    assert cyclic_components == []


def test_eager_production_import_graph_stays_acyclic() -> None:
    graph = _static_top_level_app_import_graph()
    cyclic_components = [
        sorted(component)
        for component in _strongly_connected_components(graph)
        if len(component) > 1
    ]

    assert cyclic_components == []


def test_history_stack_snapshot_does_not_depend_on_history_commands() -> None:
    graph = _static_app_import_graph()

    assert (
        "chemvas.ui.history_commands"
        not in graph["chemvas.domain.transactions.history_authority"]
    )


def test_core_does_not_import_ui_statically() -> None:
    """core stays importable without Qt: any ui dependency must be lazy."""
    violations: list[str] = []
    for path in sorted((APP_ROOT / "chemvas" / "core").rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "chemvas.ui" or name.startswith("chemvas.ui."):
                    violations.append(f"{path.name}:{node.lineno}: {name}")

    assert violations == []


def test_core_qt_dependency_is_confined_to_renderer_during_migration() -> None:
    """Record the single known core/Qt boundary violation until it is moved."""
    qt_modules: set[str] = set()
    for path in sorted((APP_ROOT / "chemvas" / "core").rglob("*.py")):
        tree = ast.parse(path.read_text())
        if any(
            (
                isinstance(node, ast.Import)
                and any(alias.name.startswith("PyQt6") for alias in node.names)
            )
            or (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("PyQt6")
            )
            for node in ast.walk(tree)
        ):
            qt_modules.add(path.relative_to(APP_ROOT).as_posix())

    assert qt_modules <= {"chemvas/core/renderer.py"}


def test_chemvas_is_the_only_production_top_level_package() -> None:
    packages = {
        path.name
        for path in APP_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }

    assert packages == {"chemvas"}


def _canvas_runtime_state_field_names() -> set[str]:
    tree = ast.parse(
        (APP_ROOT / "chemvas" / "ui" / "canvas_runtime_state.py").read_text()
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CanvasRuntimeState":
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError("CanvasRuntimeState class not found")


# States deliberately stored as direct canvas attributes (not runtime fields).
DIRECT_CANVAS_STATE_ATTRS = frozenset(("model", "renderer", "bond_renderer", "rdkit"))


def test_state_accessor_names_match_runtime_state_container() -> None:
    """Every ensure_canvas_state name must be a CanvasRuntimeState field.

    A mismatched name would make the accessor attach a shadow state directly
    on the canvas while the container holds the real one, silently splitting
    the state in two. ``runtime_field=False`` accessors must instead use one
    of the documented direct-attribute names.
    """
    field_names = _canvas_runtime_state_field_names() - {"STRICT_STATE_CONTAINER"}
    call_pattern = re.compile(
        r"ensure_canvas_state\(\s*canvas,\s*\"(?P<name>\w+)\"(?P<rest>[^\n]*)"
    )
    violations: list[str] = []
    for path in sorted((APP_ROOT / "chemvas" / "ui").glob("*.py")):
        for match in call_pattern.finditer(path.read_text()):
            name = match.group("name")
            direct = "runtime_field=False" in match.group("rest")
            if direct and name not in DIRECT_CANVAS_STATE_ATTRS:
                violations.append(f"{path.name}: direct attr {name!r} not documented")
            if not direct and name not in field_names:
                violations.append(
                    f"{path.name}: {name!r} is not a CanvasRuntimeState field"
                )

    assert violations == []
