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

LEGACY_CANVAS_SERVICE_NAMES = frozenset(
    {
        "selection_controller",
        "scene_item_controller",
        "scene_clipboard_controller",
        "scene_delete_controller",
        "scene_transform_controller",
        "insert_controller",
        "input_controller",
        "handle_controller",
        "handle_overlay_service",
        "handle_mutation_service",
        "curved_arrow_path_service",
        "selection_highlight_styler",
        "move_controller",
        "note_controller",
        "pointer_controller",
        "geometry_controller",
        "canvas_atom_mutation_service",
        "canvas_bond_mutation_service",
        "chemdraw_shortcut_service",
        "hit_testing_service",
        "canvas_color_mutation_service",
        "canvas_document_session_service",
        "canvas_graph_service",
        "canvas_history_recording_service",
        "canvas_mark_scene_service",
        "canvas_ring_fill_scene_service",
        "canvas_scene_reset_service",
        "structure_build_service",
        "scene_decoration_build_service",
        "scene_decoration_service",
        "selection_rotation_controller",
        "style_controller",
        "tool_mode_controller",
        "tools",
    }
)

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
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                matches.append(
                    f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}: {line.strip()}"
                )
    return matches


def _is_canvas_reference(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "canvas") or (
        isinstance(node, ast.Attribute) and node.attr == "canvas"
    )


def _direct_canvas_collaborator_violations(source: str) -> list[tuple[int, str]]:
    collaborator_names = {"renderer", "rdkit", "bond_renderer"}
    builtin_lookup_names = {"delattr", "getattr", "hasattr", "setattr"}

    def lookup_name_for(call: ast.Call) -> str | None:
        if isinstance(call.func, ast.Name):
            if call.func.id in builtin_lookup_names | {"_capture_optional_attribute"}:
                return call.func.id
            return None
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "builtins"
            and call.func.attr in builtin_lookup_names
        ):
            return call.func.attr
        return None

    def argument_for(
        call: ast.Call,
        position: int,
        keyword_name: str,
    ) -> ast.expr | None:
        if len(call.args) > position:
            return call.args[position]
        return next(
            (keyword.value for keyword in call.keywords if keyword.arg == keyword_name),
            None,
        )

    violations: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in collaborator_names
            and _is_canvas_reference(node.value)
        ):
            violations.append((node.lineno, node.attr))
            continue
        if not isinstance(node, ast.Call) or lookup_name_for(node) is None:
            continue
        target = argument_for(node, 0, "target")
        attribute_name = argument_for(node, 1, "name")
        if not (
            target is not None
            and _is_canvas_reference(target)
            and isinstance(attribute_name, ast.Constant)
            and attribute_name.value in collaborator_names
        ):
            continue
        violations.append((node.lineno, str(attribute_name.value)))
    return violations


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
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text(
        encoding="utf-8"
    )
    setup_source = (APP_ROOT / "chemvas" / "ui" / "main_window_tab_setup.py").read_text(
        encoding="utf-8"
    )

    assert "class SheetTabBar" not in source
    assert "QTabBar" not in source
    assert "QTabWidget()" not in source
    assert "window._" not in setup_source


def test_main_window_bootstrap_uses_runtime_services_without_window_service_wrappers() -> (
    None
):
    bootstrap = APP_ROOT / "chemvas" / "bootstrap" / "main_window_runtime.py"
    source = bootstrap.read_text(encoding="utf-8")
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
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text(
        encoding="utf-8"
    )
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
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text(
        encoding="utf-8"
    )
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
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text(
        encoding="utf-8"
    )
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
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text(
        encoding="utf-8"
    )
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
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text(
        encoding="utf-8"
    )
    bootstrap_source = (
        APP_ROOT / "chemvas" / "bootstrap" / "main_window_runtime.py"
    ).read_text(encoding="utf-8")
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
    source = (APP_ROOT / "chemvas" / "shell" / "main_window.py").read_text(
        encoding="utf-8"
    )
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
    main_window_source = main_window.read_text(encoding="utf-8")
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
            path.read_text(encoding="utf-8") for path in _app_python_files()
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
    source = service.read_text(encoding="utf-8")
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
    source = service.read_text(encoding="utf-8")
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
    tree = ast.parse(preview.read_text(encoding="utf-8"))
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
    renderer_source = renderer.read_text(encoding="utf-8")

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
    service_source = service.read_text(encoding="utf-8")

    assert not (APP_ROOT / "chemvas" / "ui" / "main_window_left_toolbar.py").exists()
    assert "from chemvas.ui.main_window_left_toolbar import" not in service_source
    assert "LeftToolBarArea" not in service_source
    assert "TOOLBAR_TOOL_GROUPS" not in service_source


def test_main_window_ui_assembly_delegates_panel_toolbar_to_module() -> None:
    service = APP_ROOT / "chemvas" / "ui" / "main_window_ui_assembly_service.py"
    panel_toolbar = APP_ROOT / "chemvas" / "ui" / "main_window_panel_toolbar.py"
    service_source = service.read_text(encoding="utf-8")
    panel_toolbar_source = panel_toolbar.read_text(encoding="utf-8")
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
    service_source = service.read_text(encoding="utf-8")

    assert "QPainter" not in service_source
    assert "QPolygonF" not in service_source
    assert "TOOLBAR_MENU_BUTTON_STYLE" not in service_source


def test_main_window_document_action_service_delegates_dialog_assembly_to_module() -> (
    None
):
    service = APP_ROOT / "chemvas" / "ui" / "main_window_document_action_service.py"
    service_source = service.read_text(encoding="utf-8")

    assert "prompt_sheet_setup(" not in service_source
    assert "QDialog" not in service_source
    assert "QComboBox" not in service_source
    assert "QDoubleSpinBox" not in service_source
    assert "QFrame" not in service_source
    assert "ArrowButton" not in service_source


def test_main_window_keeps_dialog_defaults_inside_action_services() -> None:
    main_window = APP_ROOT / "chemvas" / "shell" / "main_window.py"
    main_window_source = main_window.read_text(encoding="utf-8")

    for concrete_default in (
        "QColorDialog",
        "QFileDialog",
        "QMessageBox",
        "read_document",
        "resolve_save_path",
        "resolve_save_as_path",
        "resolve_load_path",
    ):
        assert concrete_default not in main_window_source


def test_main_window_panel_service_owns_preview_window_assembly() -> None:
    ui_assembly = APP_ROOT / "chemvas" / "ui" / "main_window_ui_assembly_service.py"
    panel_service = APP_ROOT / "chemvas" / "ui" / "main_window_panel_service.py"
    preview_window = APP_ROOT / "chemvas" / "ui" / "main_window_preview_window.py"
    ui_source = ui_assembly.read_text(encoding="utf-8")
    panel_service_source = panel_service.read_text(encoding="utf-8")
    preview_window_source = preview_window.read_text(encoding="utf-8")

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
    source = service.read_text(encoding="utf-8")
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
    assert "sheet_size_for_window=sheet_size_for_window" not in services.read_text(
        encoding="utf-8"
    )
    assert (
        "sheet_orientation_for_window=sheet_orientation_for_window"
        not in services.read_text(encoding="utf-8")
    )
    assert (
        "set_sheet_setup_for_window=set_sheet_setup_for_window"
        not in services.read_text(encoding="utf-8")
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
        tree = ast.parse(path.read_text(encoding="utf-8"))
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


def test_selection_collection_helpers_live_in_canonical_modules() -> None:
    collection = APP_ROOT / "chemvas" / "ui" / "selection_collection_access.py"
    service_access = APP_ROOT / "chemvas" / "ui" / "selection_service_access.py"
    collection_source = collection.read_text(encoding="utf-8")
    service_source = service_access.read_text(encoding="utf-8")
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
        assert f"def {helper}" in collection_source
    for helper in service_defs:
        assert f"def {helper}" in service_source


def test_production_code_uses_selection_specific_access_modules_instead_of_compat_facade() -> (
    None
):
    compat_facade = APP_ROOT / "chemvas" / "ui" / "selection_access.py"
    import_pattern = re.compile(
        r"\bfrom ui\.selection_access import\b|\bimport ui\.selection_access\b"
    )
    assert not compat_facade.exists()
    assert _matching_lines(import_pattern, _app_python_files()) == []


def test_production_canvas_service_container_lookup_is_canonical() -> None:
    allowed_attribute_receivers = {
        APP_ROOT / "chemvas" / "bootstrap" / "main_window_runtime.py": "runtime",
        APP_ROOT / "chemvas" / "shell" / "main_window.py": "runtime",
        APP_ROOT / "chemvas" / "ui" / "canvas_services.py": "canvas",
    }
    canonical_getattr_path = APP_ROOT / "chemvas" / "ui" / "canvas_service_access.py"
    violations: list[str] = []

    for path in _app_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "services":
                allowed_receiver = allowed_attribute_receivers.get(path)
                if not (
                    isinstance(node.value, ast.Name)
                    and node.value.id == allowed_receiver
                ):
                    violations.append(f"{path}:{node.lineno}: direct .services access")
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "services"
            ):
                continue
            if path != canonical_getattr_path:
                violations.append(f"{path}:{node.lineno}: getattr(..., 'services')")

    assert violations == []


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
    app_source = "\n".join(
        path.read_text(encoding="utf-8") for path in _app_python_files()
    )

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
    forbidden = re.compile(
        r"\bcanvas_services_for\b"
        r"|\bcanvas\.services\."
        r"|\b_REGULAR_RING_TEMPLATES\b"
        r"|\b_HETERO_RING_TEMPLATES\b"
        r"|\b_SERVICE_TEMPLATE_METHODS\b"
    )

    assert "add_structure_template_for" not in access.read_text(encoding="utf-8")
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
    tree = ast.parse(controller.read_text(encoding="utf-8"))
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
    tree = ast.parse(controller.read_text(encoding="utf-8"))
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
    source = (APP_ROOT / "chemvas" / "ui" / "tool_controller.py").read_text(
        encoding="utf-8"
    )

    assert "ToolContext(canvas)" not in source


def _canvas_services_entrypoint_source() -> str:
    return (APP_ROOT / "chemvas" / "ui" / "canvas_services.py").read_text(
        encoding="utf-8"
    )


def _service_assembly_paths() -> list[Path]:
    return [
        APP_ROOT / "chemvas" / "ui" / "canvas_services.py",
    ]


def test_canvas_services_delegates_tool_controller_assembly_to_factory() -> None:
    assembly_source = _canvas_services_entrypoint_source()
    factory_source = (
        APP_ROOT / "chemvas" / "ui" / "tool_controller_factory.py"
    ).read_text(encoding="utf-8")

    assert "ToolController(" not in assembly_source
    assert "tool_mode_controller" not in factory_source
    assert "ToolController(canvas)" not in factory_source


def test_canvas_services_delegates_handle_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:CanvasHandleController|CurvedArrowPathService|HandleMutationService|HandleOverlayService)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_runtime_services_exposes_single_runtimes_directly() -> None:
    runtime_services = APP_ROOT / "chemvas" / "ui" / "canvas_runtime_services.py"
    tree = ast.parse(runtime_services.read_text(encoding="utf-8"))
    annotations: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "CanvasRuntimeServices":
            continue
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                annotations[child.target.id] = ast.unparse(child.annotation)

    assert annotations["hover"] == "HoverController"
    assert annotations["graph_service"] == "Any"
    assert annotations["tool_controller"] == "Any"
    assert "graph" not in annotations
    assert "tooling" not in annotations


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
        *_service_assembly_paths(),
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
        r"\b(?:CanvasGeometryController|CanvasRingFillSceneService|"
        r"SceneItemController|SelectionHighlightStyler)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_canvas_services_delegates_interaction_service_assembly_to_bundle() -> None:
    direct_instantiation = re.compile(
        r"\b(?:CanvasMoveController|CanvasNoteController|SelectionRotationController)\("
    )

    assert _matching_lines(direct_instantiation, _service_assembly_paths()) == []


def test_atom_label_service_is_a_direct_runtime_without_auxiliary_bundle() -> None:
    runtime_services = APP_ROOT / "chemvas" / "ui" / "canvas_runtime_services.py"
    source = runtime_services.read_text(encoding="utf-8")

    assert "atom_label_service:" in source
    assert "AuxiliaryServices" not in source
    assert not (
        APP_ROOT / "chemvas" / "ui" / "canvas_auxiliary_service_bundle.py"
    ).exists()


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


def test_canvas_services_uses_active_tool_reference_port() -> None:
    entrypoint = _canvas_services_entrypoint_source()

    assert "tool_controller_holder" not in entrypoint


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
    source = _canvas_services_entrypoint_source()

    assert "SelectionStructureService" not in source
    assert "SelectionPreferenceService" not in source
    assert "SelectionOutlineService" not in source
    assert "SelectionNoteService" not in source
    assert "SelectionHitTestService" not in source
    assert "SelectionController(canvas)" not in source


def test_production_canvas_service_consumers_use_grouped_runtime_api() -> None:
    legacy_names = LEGACY_CANVAS_SERVICE_NAMES
    runtime_services = APP_ROOT / "chemvas" / "ui" / "canvas_runtime_services.py"
    violations: list[str] = []

    for path in sorted((APP_ROOT / "chemvas").rglob("*.py")):
        if path == runtime_services:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
                        "_active_canvas_services_for_window",
                        "build_canvas_services",
                        "canvas_services_for",
                    }
                )
                if flat_services_name or flat_services_attribute or direct_lookup:
                    violations.append(f"{path}:{node.lineno}: {node.attr}")
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            if not isinstance(node.func, ast.Name) or node.func.id not in {
                "getattr",
                "_optional_live_attribute",
            }:
                continue
            owner, attribute_name = node.args[:2]
            if not (
                isinstance(owner, ast.Name)
                and owner.id == "services"
                and isinstance(attribute_name, ast.Constant)
                and attribute_name.value in legacy_names
            ):
                continue
            violations.append(
                f"{path}:{node.lineno}: {node.func.id}({attribute_name.value})"
            )

    assert violations == []


def test_selection_service_bundle_assembles_selection_controller_collaborators_explicitly() -> (
    None
):
    source = (APP_ROOT / "chemvas" / "ui" / "selection_service_bundle.py").read_text(
        encoding="utf-8"
    )

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
    source = view.read_text(encoding="utf-8")

    assert "MoleculeModel" not in source


def test_direct_canvas_collaborators_stay_behind_setup_and_access_modules() -> None:
    allowed_paths = {
        APP_ROOT / "chemvas" / "ui" / "canvas_view_setup.py",
        APP_ROOT / "chemvas" / "ui" / "renderer_style_access.py",
        APP_ROOT / "chemvas" / "ui" / "rdkit_adapter_access.py",
        APP_ROOT / "chemvas" / "ui" / "bond_renderer_access.py",
    }
    violations: list[str] = []
    for path in _app_python_files():
        if path in allowed_paths:
            continue
        source = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}: {name}"
            for line_no, name in _direct_canvas_collaborator_violations(source)
        )
    lazy_creation = re.compile(
        r"\b(?:set_renderer_for|set_rdkit_adapter_for|set_bond_renderer_for|"
        r"new_rdkit_adapter)\b"
    )

    assert violations == []
    assert _matching_lines(lazy_creation, _app_python_files()) == []


def test_direct_canvas_collaborator_guard_rejects_dynamic_lookup_mutations() -> None:
    mutations = (
        'value = getattr(canvas, "rdkit", None)',
        "value = getattr(self.canvas, 'bond_renderer', None)",
        'value = builtins.getattr(canvas, "renderer", None)',
        'value = _capture_optional_attribute(canvas, "renderer")',
        'value = _capture_optional_attribute(canvas, name="renderer")',
        (
            "value = _capture_optional_attribute("
            "target=self.canvas, name='bond_renderer')"
        ),
        'value = hasattr(canvas, "rdkit")',
        'setattr(canvas, "renderer", value)',
        'builtins.setattr(self.canvas, "bond_renderer", value)',
        'delattr(canvas, "rdkit")',
        "value = canvas.renderer",
    )

    for source in mutations:
        assert _direct_canvas_collaborator_violations(source), source


def test_direct_canvas_collaborator_guard_ignores_unrelated_methods() -> None:
    controls = (
        'value = reporter.getattr(canvas, "renderer")',
        'value = reporter.hasattr(canvas, "rdkit")',
        'reporter.setattr(canvas, "bond_renderer", value)',
        'reporter.delattr(canvas, "renderer")',
        'value = reporter._capture_optional_attribute(canvas, "renderer")',
    )

    for source in controls:
        assert _direct_canvas_collaborator_violations(source) == [], source


def test_rdkit_async_jobs_store_running_jobs_in_state_module() -> None:
    source = (APP_ROOT / "chemvas" / "ui" / "rdkit_async_jobs.py").read_text(
        encoding="utf-8"
    )

    assert "_rdkit_export_jobs" not in source


def test_canvas_view_delegates_rdkit_adapter_creation_to_setup() -> None:
    view = APP_ROOT / "chemvas" / "ui" / "canvas_view.py"
    source = view.read_text(encoding="utf-8")

    assert "RDKitAdapter" not in source


def test_canvas_view_delegates_bond_renderer_creation_to_setup() -> None:
    view = APP_ROOT / "chemvas" / "ui" / "canvas_view.py"
    source = view.read_text(encoding="utf-8")

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


def test_core_history_does_not_fall_back_to_self_releasing_snapshots() -> None:
    module = APP_ROOT / "chemvas" / "core" / "history.py"
    forbidden = re.compile(
        r"\bsnapshot\.release\b"
        r"|\bgetattr\(\s*snapshot\s*,\s*[\"']release[\"']"
    )

    assert _matching_lines(forbidden, [module]) == []


def test_document_session_history_rollback_does_not_rebind_stacks() -> None:
    module = APP_ROOT / "chemvas" / "ui" / "canvas_document_session_service.py"
    forbidden = re.compile(r"\bsnapshot\.state\.(?:history|redo_stack)\s*=")

    assert _matching_lines(forbidden, [module]) == []


def test_document_session_does_not_snapshot_legacy_sheet_fields() -> None:
    module = APP_ROOT / "chemvas" / "ui" / "canvas_document_session_service.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    forbidden = {"sheet_size", "sheet_orientation"}
    constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert constants.isdisjoint(forbidden)


def test_sheet_setup_access_delegates_sheet_values_to_sheet_setup_state() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "sheet_setup_access.py"
    forbidden = re.compile(
        r"\bcanvas\.sheet_size\b"
        r"|\bcanvas\.sheet_orientation\b"
        r"|\bcanvas\.setSceneRect\b"
        r"|\bcanvas\.viewport\("
    )

    assert _matching_lines(forbidden, [access]) == []


def test_sheet_setup_values_exist_only_in_the_runtime_state() -> None:
    forbidden_names = {"sheet_size", "sheet_orientation"}
    violations: list[str] = []

    for path in _app_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                violations.append(f"{path}:{node.lineno}: .{node.attr}")
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "setattr"}
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in forbidden_names
            ):
                continue
            violations.append(f"{path}:{node.lineno}: {node.args[1].value!r}")

    assert violations == []


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


def test_dead_structure_template_catalog_modules_are_removed() -> None:
    removed_modules = {
        "structure_fragment_build_service.py",
        "structure_template_build_service.py",
        "structure_template_commands.py",
    }
    app_source = "\n".join(
        path.read_text(encoding="utf-8") for path in _app_python_files()
    )

    for module_name in removed_modules:
        assert not (APP_ROOT / "chemvas" / "ui" / module_name).exists()
        assert module_name.removesuffix(".py") not in app_source


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
    source = service.read_text(encoding="utf-8")
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


def test_main_window_icon_factory_reads_no_canvas_style() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text(encoding="utf-8")

    # Every icon now comes from the shared SVG design set, so the factory has no
    # canvas-derived pen or spacing to read. The port that used to fetch them is
    # gone with its last caller instead of staying as a second style source.
    assert not (
        APP_ROOT / "chemvas" / "ui" / "main_window_icon_canvas_style.py"
    ).exists()
    assert "MainWindowIconCanvasStyle" not in factory_source
    assert "canvas_style" not in factory_source
    assert "window.canvas" not in factory_source
    assert "self.window" not in factory_source
    assert "renderer_style_access" not in factory_source
    assert "ring_double_segments_for" not in factory_source
    assert "from chemvas.domain.document import Atom" not in factory_source


def test_main_window_icon_factory_delegates_hidpi_icon_rendering_to_pixmap_factory() -> (
    None
):
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text(encoding="utf-8")

    assert "QPixmap" not in factory_source
    assert "QPainter" not in factory_source
    assert "QApplication" not in factory_source
    assert "devicePixelRatio()" not in factory_source


def test_main_window_icon_geometry_helper_stays_removed() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text(encoding="utf-8")

    assert not (APP_ROOT / "chemvas" / "ui" / "main_window_icon_geometry.py").exists()
    assert "main_window_icon_geometry" not in factory_source
    assert "def regular_icon_polygon" not in factory_source
    assert "def benzene_icon_polygon" not in factory_source
    assert "def template_preview_ring_sides" not in factory_source
    assert "def chair_icon_points" not in factory_source


def test_main_window_bond_icons_use_only_static_design_mapping() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text(encoding="utf-8")

    assert not (
        APP_ROOT / "chemvas" / "ui" / "main_window_bond_icon_renderer.py"
    ).exists()
    assert "MainWindowBondIconRenderer" not in factory_source
    assert "benzene_icon_inner_segments" not in factory_source
    for icon_name in (
        "bond",
        "bond_double",
        "bond_triple",
        "wedge",
        "hash",
        "benzene",
        "bond_bold",
        "bond_dotted",
    ):
        assert f'self.make_design_icon("{icon_name}")' in factory_source
    assert "def icon_bond_length(" not in factory_source
    assert "bold_bond_pen()" not in factory_source
    assert "hash_spacing_px()" not in factory_source
    assert "dotted_bond_pen()" not in factory_source


def test_main_window_arrow_icons_use_only_static_design_mapping() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text(encoding="utf-8")

    # Arrow previews/presets/controls render through the shared SVG design icon
    # set. The per-shape QPainter renderer they used to delegate to is gone, so
    # arrow icon geometry has one source instead of two.
    assert not (
        APP_ROOT / "chemvas" / "ui" / "main_window_arrow_icon_renderer.py"
    ).exists()
    assert "MainWindowArrowIconRenderer" not in factory_source
    assert 'self._design_icon(f"arrow_{kind}"' in factory_source
    assert "def draw_arrow_head" not in factory_source
    assert "quadTo(15, 6, 24, 15)" not in factory_source


def test_main_window_template_icons_use_only_static_design_mapping() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text(encoding="utf-8")

    assert not (
        APP_ROOT / "chemvas" / "ui" / "main_window_template_icon_renderer.py"
    ).exists()
    assert "_TEMPLATE_ICON_BY_LABEL" in factory_source
    assert "def icon_templates(" not in factory_source
    assert "template_preview_ring_polygon" not in factory_source
    assert "template_preview_ring_sides" not in factory_source
    assert "chair_icon_points" not in factory_source


def test_main_window_utility_icon_accessors_stay_removed() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text(encoding="utf-8")

    # The window chrome takes these actions from the menus, not from toolbar
    # icons, so nothing called the utility accessors after the SVG cutover. They
    # went with their renderer; a caller that needs one adds it back next to the
    # design icon it renders, not as a second painting path.
    assert not (
        APP_ROOT / "chemvas" / "ui" / "main_window_utility_icon_renderer.py"
    ).exists()
    assert "MainWindowUtilityIconRenderer" not in factory_source
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
        assert f"def icon_{icon_name}(" not in factory_source

    # The text style bar reaches its font control through the context bar spec
    # tables, so the accessor went the same way as the utility ones.
    assert "def icon_font(" not in factory_source

    assert "drawRect(7, 8, 10, 12)" not in factory_source
    assert "drawLine(QPointF(15.0, 5.0), QPointF(15.0, 17.5))" not in factory_source
    assert "drawEllipse(7, 7, 16, 16)" not in factory_source


def test_main_window_tool_icons_use_only_static_design_mapping() -> None:
    factory = APP_ROOT / "chemvas" / "ui" / "main_window_icon_factory.py"
    factory_source = factory.read_text(encoding="utf-8")

    assert not (
        APP_ROOT / "chemvas" / "ui" / "main_window_tool_icon_renderer.py"
    ).exists()
    assert "MainWindowToolIconRenderer" not in factory_source
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
    # `icon_select` is the one accessor left drawing the move glyph; the
    # `icon_move` alias that duplicated it had no caller and is gone.
    assert factory_source.count('self.make_design_icon("move")') == 1
    assert "def icon_move(" not in factory_source
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
    controller_source = controller.read_text(encoding="utf-8")
    lifecycle_source = lifecycle_service.read_text(encoding="utf-8")

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
    controller_source = controller.read_text(encoding="utf-8")

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


def test_canvas_handle_controller_does_not_use_context_facade() -> None:
    removed_context = APP_ROOT / "chemvas" / "ui" / "canvas_handle_context.py"
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_handle_controller.py"
    pattern = re.compile(
        r"\bCanvasHandleContext\b|\bcanvas_handle_context_for\b|self\.context\b"
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
    access_source = access.read_text(encoding="utf-8")

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


def test_bond_build_and_update_do_not_own_style_or_geometry_dispatch() -> None:
    build = APP_ROOT / "chemvas" / "ui" / "bond_graphics_build_service.py"
    update = APP_ROOT / "chemvas" / "ui" / "bond_geometry_update_service.py"
    forbidden = re.compile(
        r"\bbond\.(?:style|order)\b"
        r"|\b(?:BOLD_BOND_STYLES|is_dotted_double_bond_style"
        r"|is_plain_double_bond_style|double_position_for_style"
        r"|normalized_plain_double_style|ring_center_for_bond"
        r"|trim_line_for_labels|wedge_polygon|hash_segments"
        r"|dotted_bond_path|plain_double_segments|ring_double_segments"
        r"|parallel_bond_segments|line_normal|bold_strip_polygon)\b"
    )

    assert _matching_lines(forbidden, [build, update]) == []


def test_alias_attachment_derivation_has_one_domain_owner() -> None:
    owner = APP_ROOT / "chemvas" / "domain" / "atom_aliases.py"
    consumers = [path for path in _app_python_files() if path != owner]

    assert _matching_lines(re.compile(r"\bAliasAttachment\("), consumers) == []
    assert _matching_lines(re.compile(r"\b_alias_attachments\b"), consumers) == []


def test_removed_compatibility_surfaces_do_not_return() -> None:
    files = _app_python_files()
    removed_symbols = re.compile(
        r"\b(?:LEGACY_PROFILE_ID|LEGACY_CALCULATION_PLAN_VERSION"
        r"|LEGACY_CANVAS_FILE_VERSION|LEGACY_CLIPBOARD_SELECTION_VERSION"
        r"|CALCULATION_PLAN_CANVAS_FILE_VERSION|COMPACT_BONDS_CANVAS_FILE_VERSION"
        r"|COMPACT_BONDS_FILE_VERSION|GROUPS_CANVAS_FILE_VERSION"
        r"|PERSPECTIVE_CANVAS_FILE_VERSION"
        r"|PRECOMPLEX_CANVAS_FILE_VERSION|CLIPBOARD_SELECTION_PERSPECTIVE_VERSION"
        r"|ARROW_MENU_ITEMS|ARROW_PRESET_ITEMS|ACS_COLOR_PALETTE"
        r"|render_scene_to_svg|_command_requires_exact_history_transaction"
        r"|draw_ring_double_bond_for|load_from_file"
        r"|draw_ring_double_bond|draw_dotted_double_bond"
        r"|square_pair_double_dagger|globalPos|LineHeightType)\b"
    )
    signature_fallback = re.compile(
        r'"(?:snapshot|render_insert_preview|bracket_kind)"\s+in\s+str\(\w+\)'
    )

    assert _matching_lines(removed_symbols, files) == []
    assert _matching_lines(signature_fallback, files) == []


def test_selection_style_access_does_not_reexport_selection_info() -> None:
    access = APP_ROOT / "chemvas" / "ui" / "selection_style_access.py"

    assert _matching_lines(re.compile(r"\bemit_selection_info_for\b"), [access]) == []


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
    source = (APP_ROOT / "chemvas" / "ui" / "perspective_tool_controller.py").read_text(
        encoding="utf-8"
    )

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


def test_production_code_uses_tool_controller_instead_of_canvas_tools_alias() -> None:
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
    tree = ast.parse(hover_state.read_text(encoding="utf-8"))
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


def test_input_view_state_access_is_strict_runtime_owned() -> None:
    state_module = APP_ROOT / "chemvas" / "ui" / "input_view_state.py"
    access_module = APP_ROOT / "chemvas" / "ui" / "input_view_access.py"
    state_source = state_module.read_text(encoding="utf-8")
    access_source = access_module.read_text(encoding="utf-8")
    access_tree = ast.parse(access_source)
    getter = next(
        node
        for node in access_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "input_view_state_for"
    )
    getter_source = ast.get_source_segment(access_source, getter) or ""
    fallback_pattern = re.compile(
        r"\bensure_canvas_state\b"
        r"|\b(?:getattr|setattr)\(\s*canvas\b"
        r"|\bcanvas\.input_view_state\b"
    )

    assert "class InputViewState" in state_source
    assert "def input_view_state_for" not in state_source
    assert "canvas.runtime_state.input_view_state" in getter_source
    assert fallback_pattern.search(state_source) is None
    assert fallback_pattern.search(getter_source) is None


def test_callback_state_accessor_is_strict_runtime_owned() -> None:
    callback_state = APP_ROOT / "chemvas" / "ui" / "canvas_callback_state.py"
    source = callback_state.read_text(encoding="utf-8")
    tree = ast.parse(source)
    getter = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "callback_state_for"
    )
    getter_source = ast.get_source_segment(source, getter) or ""
    fallback_pattern = re.compile(
        r"\bensure_canvas_state\b"
        r"|\b(?:getattr|setattr)\(\s*canvas\b"
        r"|\bcanvas\.callback_state\b"
    )

    assert "class CanvasCallbackState" in source
    assert "canvas.runtime_state.callback_state" in getter_source
    assert fallback_pattern.search(getter_source) is None


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


def test_state_accessors_do_not_refresh_existing_state_from_canvas_attrs() -> None:
    pattern = re.compile(
        r"if state is not None:\s*"
        r"(?:\n\s*)+refresh_state_from_canvas_(?:attrs|attr_map)\("
    )
    matches = [
        str(path.relative_to(APP_ROOT.parents[0]))
        for path in _app_python_files()
        if pattern.search(path.read_text(encoding="utf-8"))
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
    source = tool_context.read_text(encoding="utf-8")
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
    tree = ast.parse(controller.read_text(encoding="utf-8"))
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


def test_removed_tools_facade_stays_absent() -> None:
    assert not (APP_ROOT / "chemvas" / "ui" / "tools.py").exists()


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
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
        "chemvas.domain.transactions.outcome",
        "chemvas.domain.transactions.recovery",
        "chemvas.ui.canvas_history_service",
        "chemvas.ui.transactions.document",
        "chemvas.ui.transactions.object_graph_snapshot",
        "chemvas.ui.transactions.scene_rect",
        "chemvas.ui.transactions.scene_runtime",
        "chemvas.ui.history_atom_position_restore",
        "chemvas.ui.history_canvas_access",
        "chemvas.ui.history_commands",
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


def test_document_savepoint_does_not_depend_on_history_policy_or_commands() -> None:
    graph = _static_app_import_graph()

    assert (
        not {
            "chemvas.ui.canvas_history_service",
            "chemvas.ui.history_commands",
        }
        & graph["chemvas.ui.transactions.document"]
    )


def test_history_stack_snapshot_has_one_production_owner() -> None:
    owners = [
        path
        for path in _app_python_files()
        if re.search(
            r"^class HistoryStackSnapshot\b",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    ]

    assert owners == [APP_ROOT / "chemvas" / "ui" / "canvas_history_service.py"]


def test_removed_history_recovery_lattice_stays_absent() -> None:
    pattern = re.compile(
        r"\b(?:HistoryAuthoritySnapshot|RecordingHistoryPolicySnapshot"
        r"|CallbackFreeHistoryBaseline|restore_snapshot_with_retry"
        r"|HistoryCommandSnapshot|restore_with_result"
        r"|history_operation_scope"
        r"|consume_authoritative_history_failure_restore)\b"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_rollback_kernel_has_no_restore_retry_or_qt_base_port_bypass() -> None:
    kernel_files = [
        APP_ROOT / "chemvas" / "core" / "history.py",
        APP_ROOT / "chemvas" / "domain" / "transactions" / "recovery.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_history_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_history_recording_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_color_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_document_session_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas_scene_reset_service.py",
        APP_ROOT / "chemvas" / "ui" / "history_canvas_access.py",
        APP_ROOT / "chemvas" / "ui" / "history_commands.py",
        APP_ROOT / "chemvas" / "ui" / "insert_smiles_service.py",
        APP_ROOT / "chemvas" / "ui" / "sheet_setup_access.py",
        *sorted((APP_ROOT / "chemvas" / "ui" / "transactions").glob("*.py")),
    ]
    retry_pattern = re.compile(
        r"\b(?:restore_with_retry|restore_attempts?|rollback_retries"
        r"|retrying(?:\s+\w+){0,4}\s+(?:restore|rollback))\b",
        re.IGNORECASE,
    )
    base_port_pattern = re.compile(
        r"\b(?:QObject|QAbstractGraphicsShapeItem"
        r"|QGraphics(?:Item|TextItem|EllipseItem|PolygonItem|Scene|View))"
        r"\.[A-Za-z_]\w*\("
    )
    adversarial_pattern = re.compile(
        r"\b(?:inspect\.getattr_static|except\s+BaseException"
        r"|(?:def\s+)?reassert\()"
    )

    assert _matching_lines(retry_pattern, kernel_files) == []
    assert _matching_lines(base_port_pattern, kernel_files) == []
    assert _matching_lines(adversarial_pattern, kernel_files) == []


def test_history_commands_does_not_export_scene_snapshot_toolkit() -> None:
    history_commands = APP_ROOT / "chemvas" / "ui" / "history_commands.py"
    pattern = re.compile(
        r"^(?:class|def) _?(?:SceneRuntimeSnapshot|capture_scene_runtime"
        r"|restore_scene_runtime|restore_scene_runtime_identity"
        r"|verify_scene_runtime_identity)\b",
        re.MULTILINE,
    )

    assert _matching_lines(pattern, [history_commands]) == []


def test_core_does_not_import_ui_statically() -> None:
    """core stays importable without Qt: any ui dependency must be lazy."""
    violations: list[str] = []
    for path in sorted((APP_ROOT / "chemvas" / "core").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
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


def test_core_has_no_direct_qt_dependencies() -> None:
    qt_modules: set[str] = set()
    for path in sorted((APP_ROOT / "chemvas" / "core").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
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

    assert qt_modules == set()


def test_chemvas_is_the_only_production_top_level_package() -> None:
    packages = {
        path.name
        for path in APP_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }

    assert packages == {"chemvas"}


def _canvas_runtime_state_field_names() -> set[str]:
    tree = ast.parse(
        (APP_ROOT / "chemvas" / "ui" / "canvas_runtime_state.py").read_text(
            encoding="utf-8"
        )
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CanvasRuntimeState":
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError("CanvasRuntimeState class not found")


# Functions whose name looks like a state accessor but which are not one, with
# the reason each is exempt from reading CanvasRuntimeState.
NON_RUNTIME_STATE_ACCESSORS = {
    # Setter, not an accessor.
    "sheet_setup_state.py:set_sheet_setup_state_for",
    # Whole-canvas snapshot/restore helpers, not a single state field.
    "canvas_window_access.py:snapshot_canvas_state_for",
    "canvas_window_access.py:restore_canvas_state_for",
    # Applies a captured insert session; does not resolve a container field.
    "insert_session_access.py:apply_insert_session_state_for",
    # Serializes one scene item's state, not canvas state.
    "scene_item_state_serialization.py:scene_item_state_for",
}

EXPECTED_RUNTIME_STATE_ACCESSORS = {
    "atom_coords_access.py:atom_coords_3d_state_for",
    "canvas_atom_graphics_state.py:atom_graphics_state_for",
    "canvas_bond_graphics_state.py:bond_graphics_state_for",
    "canvas_calculation_plan_state.py:calculation_plan_state_for",
    "canvas_callback_state.py:callback_state_for",
    "canvas_document_metadata_state.py:document_metadata_state_for",
    "canvas_graph_state.py:graph_state_for",
    "canvas_group_state.py:group_state_for",
    "canvas_history_state.py:history_state_for",
    "canvas_hover_state.py:hover_state_for",
    "canvas_insert_state.py:insert_state_for",
    "canvas_mark_registry.py:mark_registry_for",
    "canvas_rotation_state.py:rotation_state_for",
    "canvas_scene_items_state.py:scene_items_state_for",
    "canvas_smiles_input_state.py:smiles_input_state_for",
    "canvas_text_style_state.py:text_style_state_for",
    "canvas_tool_settings_state.py:tool_settings_state_for",
    "handle_state.py:handle_state_for",
    "input_view_access.py:input_view_state_for",
    "scene_clipboard_state.py:scene_clipboard_state_for",
    "selection_info_state.py:selection_info_state_for",
    "selection_outline_state.py:selection_outline_state_for",
    "selection_style_state.py:selection_style_state_for",
    "sheet_setup_state.py:sheet_setup_state_for",
    "spatial_index_state.py:spatial_index_state_for",
}


def test_state_accessors_read_the_runtime_container_directly() -> None:
    """Every canvas state accessor resolves its field on CanvasRuntimeState.

    Attaching state to the canvas instead splits it in two: the container keeps
    the real one while the accessor hands out a shadow copy. Reading the field
    off the slotted container makes a renamed or misspelled field raise.

    The check enumerates rather than samples: an accessor that stops reading the
    container at all is a violation, not a skipped file, so neither a renamed
    lookup helper nor an accessor that synthesizes its own state can pass.
    """
    field_names = _canvas_runtime_state_field_names()
    runtime_read = re.compile(r"canvas\.runtime_state\.(?P<name>\w+)\b")
    fallback = re.compile(
        r"\bensure_canvas_state\b|\b(?:getattr|setattr)\(\s*canvas\s*,\s*[\"']"
    )
    accessor_name = re.compile(r"_(?:state|registry)_for$")
    checked: list[str] = []
    violations: list[str] = []
    for path in sorted((APP_ROOT / "chemvas" / "ui").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not accessor_name.search(node.name):
                continue
            accessor_key = f"{path.name}:{node.name}"
            if accessor_key in NON_RUNTIME_STATE_ACCESSORS:
                continue
            body = ast.get_source_segment(source, node) or ""
            names = {match.group("name") for match in runtime_read.finditer(body)}
            checked.append(accessor_key)
            if not names:
                violations.append(
                    f"{path.name}:{node.name} does not read the runtime container"
                )
                continue
            for name in sorted(names - field_names):
                violations.append(
                    f"{path.name}:{node.name}: {name!r} is not a"
                    " CanvasRuntimeState field"
                )
            if fallback.search(body):
                violations.append(
                    f"{path.name}:{node.name} falls back off the runtime container"
                )

    assert violations == []
    # Keep the inventory exact: a renamed, deleted, or newly introduced state
    # accessor must update this boundary deliberately instead of falling out of
    # the name-based enumeration unnoticed.
    assert set(checked) == EXPECTED_RUNTIME_STATE_ACCESSORS


def test_ensure_canvas_state_stays_removed() -> None:
    """The lazy attach-on-first-use accessor does not come back.

    It let a state accessor create a second copy of a state on the canvas
    whenever the container did not already hold one.
    """
    pattern = re.compile(r"\bensure_canvas_state\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_unregistered_transform_and_edit_bond_tools_stay_removed() -> None:
    """Neither tool was ever a key in ``ToolController.tools``.

    They could only be built by hand, so nothing in the running application
    could reach them.
    """
    pattern = re.compile(r"\b(?:TransformTool|EditBondTool)\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_orbital_handle_overlay_access_wrapper_stays_removed() -> None:
    """Only ``TransformTool`` called it.

    The live rotate-handle path goes through ``HandleOverlayService`` and
    ``CanvasHandleController`` instead.
    """
    pattern = re.compile(r"\bshow_orbital_handles_for\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_tool_context_bond_id_from_event_port_stays_removed() -> None:
    """``EditBondTool`` was the only caller of the ``ToolContext`` port.

    The identically named ``CanvasHitTestingService`` method stays: the
    right-click context menu still routes through it.
    """
    tool_context = APP_ROOT / "chemvas" / "ui" / "tool_context.py"
    pattern = re.compile(r"^\s+def bond_id_from_event\b")

    assert _matching_lines(pattern, [tool_context]) == []


def test_unreachable_snap_setting_accessors_stay_removed() -> None:
    """No menu, toolbar, or context bar ever called these.

    The curved-arrow and orbital snap fields they wrote stay on
    ``CanvasToolSettingsState`` because the handle mutation code still reads
    them, and ``snap_angle_step`` is still written through the generic
    ``set_tool_setting_for``.
    """
    controller = APP_ROOT / "chemvas" / "ui" / "canvas_tool_mode_controller.py"
    accessor_names = (
        "set_curved_snap",
        "get_curved_snap",
        "set_curved_snap_step",
        "get_curved_snap_step",
        "set_curved_symmetry",
        "get_curved_symmetry",
        "set_orbital_snap_enabled",
        "get_orbital_snap_enabled",
        "set_orbital_snap_step",
        "get_orbital_snap_step",
        "set_snap_angle_step",
    )
    names = "|".join(re.escape(name) for name in accessor_names)
    pattern = re.compile(rf"^\s+def (?:{names})\b")

    assert _matching_lines(pattern, [controller]) == []


def test_write_only_tool_setting_surfaces_stay_removed() -> None:
    """``curved_symmetry`` was never read and ``TOOL_SETTING_ATTRS`` never used.

    The field only ever fed its own accessor pair, and the tuple had no
    consumer at all.
    """
    pattern = re.compile(r"\b(?:curved_symmetry|TOOL_SETTING_ATTRS)\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_access_ports_without_a_production_caller_stay_removed() -> None:
    """Wrappers and helpers only the tests ever called.

    Each ``*_access`` wrapper forwarded to a service the production code
    already reaches directly, so it was a second door nobody walked through.
    The rest lost their last caller with those wrappers: the scene item map
    helpers and ``remove_scene_items`` under ``rebuild_graphics_for``, and
    ``build_template_entries`` under the retired menu population path.
    ``bold_bond_width_for`` is not ``renderer_bold_bond_width_for`` and
    ``remove_scene_items`` is not ``remove_scene_item``; both survivors are
    live and stay.
    """
    removed_ports = (
        "rebuild_graphics_for",
        "scale_qpoints_to_bond_length",
        "mark_offset_from_click_for",
        "visible_label_rect_for_atom_for",
        "mark_clearance_for_kind_for",
        "label_cut_radius_for_atom_for",
        "build_selected_structure_payload_for",
        "selection_signature_for",
        "add_benzene_template_for",
        "bold_bond_width_for",
        "clear_canvas_scene_item_map",
        "clear_canvas_scene_item_list_map",
        "clear_scene_item_map",
        "clear_scene_item_list_map",
        "remove_scene_items",
        "build_template_entries",
    )
    pattern = re.compile(
        rf"\b(?:{'|'.join(re.escape(name) for name in removed_ports)})\b"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_service_methods_only_the_tests_called_stay_removed() -> None:
    """Six methods whose only callers lived in the test suite.

    Each ban is scoped to the module that defined the method, because the
    bare names collide with live surfaces elsewhere.
    """
    ui_root = APP_ROOT / "chemvas" / "ui"
    scoped_bans = {
        "canvas_graph_service.py": ("atom_bond_order_sum",),
        "canvas_geometry_controller.py": ("ring_for_bond",),
        "scene_delete_logic.py": ("has_work",),
        "main_window_status_service.py": ("zoom_status_tip",),
        "main_window_state.py": ("reset_canvas_name_counter",),
        "canvas_document_session_service.py": ("_snapshot_canvas_scene",),
    }
    violations: list[str] = []
    for file_name, method_names in scoped_bans.items():
        names = "|".join(re.escape(name) for name in method_names)
        pattern = re.compile(rf"^\s*def (?:{names})\b")
        violations.extend(_matching_lines(pattern, [ui_root / file_name]))

    assert violations == []


def test_duplicate_rdkit_export_reset_wrapper_stays_removed() -> None:
    """The module-level wrapper duplicated ``RDKitExportJobRegistry.reset_for_tests``.

    The class method stays; only the second name for it is gone.
    """
    pattern = re.compile(r"\breset_rdkit_export_job_state_for_tests\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def test_exports_and_constants_without_a_reader_stay_removed() -> None:
    """Names nothing imported, iterated, or read.

    ``compute_identifiers_for`` is the access wrapper, not the live
    ``compute_identifiers`` on the adapter.
    """
    removed_names = (
        "compute_identifiers_for",
        "TEXT_STYLE_ATTRS",
        "CANVAS_TEMPLATE_FIELDS",
        "DESIGN_ICON_NAMES",
        "HEADLESS_SUBCOMMANDS",
        "hash_bond_width",
        "wedge_width_px",
    )
    pattern = re.compile(
        rf"\b(?:{'|'.join(re.escape(name) for name in removed_names)})\b"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_unused_members_stay_removed_from_their_defining_modules() -> None:
    """Three members whose bare names collide with live surfaces.

    ``_restore_observer_ports`` is not ``_try_restore_observer_ports`` and
    ``viewport_center`` is not ``viewport_center_scene_pos_for``; both
    survivors are live. The free ``canvas_name_counter`` helper is likewise not
    ``MainWindowState.canvas_name_counter``, the counter field the window still
    increments, so that ban is scoped to the module that defined the helper.
    """
    ui_root = APP_ROOT / "chemvas" / "ui"
    scoped_bans = {
        "scene_delete_controller.py": ("_restore_observer_ports",),
        "structure_build_service.py": ("latest_bond_id", "viewport_center"),
        "main_window_canvas_logic.py": ("canvas_name_counter",),
    }
    violations: list[str] = []
    for file_name, method_names in scoped_bans.items():
        names = "|".join(re.escape(name) for name in method_names)
        pattern = re.compile(rf"^\s*def (?:{names})\b")
        violations.extend(_matching_lines(pattern, [ui_root / file_name]))

    assert violations == []


def test_menu_population_path_stays_removed_from_tool_routing_service() -> None:
    """Nothing in the application built these menus.

    The context bar page factories draw the same template, arrow, and palette
    entries directly, so the QMenu path had no caller. Following the cascade to
    its fixed point also retired the entry builders and the two arrow menu
    activators. ``apply_color_preset`` and ``apply_ring_fill_preset`` stay:
    the panel toolbar routes through them.
    """
    service = APP_ROOT / "chemvas" / "ui" / "main_window_tool_routing_service.py"
    method_names = (
        "populate_template_menu",
        "populate_arrow_menu",
        "populate_palette_menu",
        "add_menu_action",
        "palette_icon",
        "template_entries",
        "acs_color_palette",
        "activate_arrow_type_from_menu",
        "activate_arrow_preset_from_menu",
    )
    names = "|".join(re.escape(name) for name in method_names)
    pattern = re.compile(rf"^\s*def (?:{names})\b")

    assert _matching_lines(pattern, [service]) == []


def test_canvas_tab_reorder_wiring_stays_removed() -> None:
    """Reordering canvas tabs was a dead direction.

    Each window holds one canvas and the tab strip is hidden, so the tabs were
    marked movable and the move signal was connected to a handler that
    discarded its arguments.
    """
    pattern = re.compile(r"\b(?:on_canvas_tab_moved|tabMoved)\b")

    assert _matching_lines(pattern, _app_python_files()) == []


def _unread_strict_parameters(source: str) -> list[tuple[int, str]]:
    """Functions declaring a ``strict`` parameter their body never loads."""

    def parameters(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
        args = node.args
        declared = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        if args.vararg is not None:
            declared.append(args.vararg)
        if args.kwarg is not None:
            declared.append(args.kwarg)
        return {argument.arg for argument in declared}

    dead: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "strict" not in parameters(node):
            continue
        loads = 0
        pending: list[ast.AST] = list(node.body)
        while pending:
            child = pending.pop()
            if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
            ) and "strict" in parameters(child):
                # A nested scope rebinding the name reads its own parameter.
                continue
            if (
                isinstance(child, ast.Name)
                and child.id == "strict"
                and isinstance(child.ctx, ast.Load)
            ):
                loads += 1
            pending.extend(ast.iter_child_nodes(child))
        if loads == 0:
            dead.append((node.lineno, node.name))
    return dead


def test_no_production_function_declares_an_unread_strict_parameter() -> None:
    """A ``strict`` flag must be read by the function that declares it.

    A flag nobody reads is a promise the function does not keep: every call
    site picks a mode the body then ignores. The rule is also what drives such
    a removal to its fixed point, because a function whose only ``strict``
    read was forwarding it to such a callee becomes a violation itself once
    the callee's parameter goes. Forwarding counts as a read, so the
    ``_scene_items_*`` chain and the restore-side helpers that genuinely
    switch on the flag all pass.
    """
    violations = [
        f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}: {name}"
        for path in _app_python_files()
        for line_no, name in _unread_strict_parameters(path.read_text(encoding="utf-8"))
    ]

    assert violations == []


def test_window_tool_settings_port_stays_removed() -> None:
    """The window-level tool-settings lookup lost its only reason to exist.

    ``tool_action_key_for_canvas_state`` branches on the active tool alone, so
    the toolbar sync stopped reading the tool settings, the tool state service
    stopped being handed the port, and the port itself stopped having a
    caller. The bare name is safe to ban outright: the live surfaces are
    ``tool_settings_state_for`` and the ``tool_settings_state`` runtime field,
    neither of which contains it, and ``tool_actions_for_window`` and
    ``tool_action_for_window`` are different ports that stay.
    """
    pattern = re.compile(r"\b_?tool_settings_for_window\b")

    assert _matching_lines(pattern, _app_python_files()) == []


# --- Single-owner pins for constants and helpers that were duplicated -------
#
# Each rule below is a pattern ban, not an assertion that a phrasing exists:
# it names the one module allowed to own a value or a shape and fails if a
# second definition of the same thing appears anywhere under app/.


_SET_BUILDERS = frozenset({"set", "frozenset"})


def _split_call_strings(node: ast.expr) -> list[str] | None:
    """The words of a literal ``"a b c".split()``, else ``None``.

    A whitespace-separated string is a set of strings written without the
    quotes and commas, so the pins have to read it as one.
    """
    if not isinstance(node, ast.Call) or node.keywords or len(node.args) > 1:
        return None
    function = node.func
    if not isinstance(function, ast.Attribute) or function.attr != "split":
        return None
    subject = function.value
    if not isinstance(subject, ast.Constant) or not isinstance(subject.value, str):
        return None
    separators: list[str] = []
    for argument in node.args:
        if not isinstance(argument, ast.Constant):
            return None
        if not isinstance(argument.value, str):
            return None
        separators.append(argument.value)
    return subject.value.split(*separators)


def _string_collection_value(node: ast.expr) -> tuple[str, ...] | None:
    """The strings a single expression spells out, else ``None``."""
    entries: tuple[object, ...]
    if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
        try:
            evaluated = ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError):
            return None
        if not isinstance(evaluated, (set, frozenset, tuple, list)):
            return None
        entries = tuple(evaluated)
    else:
        words = _split_call_strings(node)
        if words is None:
            return None
        entries = tuple(words)
    strings = tuple(entry for entry in entries if isinstance(entry, str))
    if not strings or len(strings) != len(entries):
        return None
    return strings


def _set_builder_argument(node: ast.AST) -> ast.expr | None:
    """The single argument of a ``set(...)``/``frozenset(...)`` call."""
    if not isinstance(node, ast.Call) or node.keywords or len(node.args) != 1:
        return None
    if not isinstance(node.func, ast.Name) or node.func.id not in _SET_BUILDERS:
        return None
    return node.args[0]


def _string_set_literals(tree: ast.AST) -> list[tuple[int, frozenset[str]]]:
    """Every literal collection of plain strings, with its line number.

    A duplicated set of strings is the same duplicate however it is spelled,
    so a set display, a bare tuple and a bare list all count, as does
    ``set(...)`` or ``frozenset(...)`` wrapping any of them or wrapping a
    literal ``"a b c".split()``. A wrapped literal is reported once, at the
    call, so a module that writes ``frozenset((...))`` stays one owner rather
    than becoming two.

    What still escapes: a collection assembled at runtime — from a dict's
    keys or values, a comprehension, a concatenation of names, or a string
    split on a computed separator — because none of those spell the members
    where the source can be read.
    """
    wrapped = {
        id(argument)
        for node in ast.walk(tree)
        if (argument := _set_builder_argument(node)) is not None
    }
    literals: list[tuple[int, frozenset[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.expr) or id(node) in wrapped:
            continue
        argument = _set_builder_argument(node)
        entries = _string_collection_value(node if argument is None else argument)
        if entries is None:
            continue
        literals.append((node.lineno, frozenset(entries)))
    return literals


def _modules_listing(members: frozenset[str]) -> list[str]:
    """Modules with a string-collection literal containing every member."""
    owners: list[str] = []
    for path in _app_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line_no, literal in _string_set_literals(tree):
            if members <= literal:
                owners.append(f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}")
    return owners


ARROW_KIND_MEMBERS = frozenset(
    {
        "arrow",
        "equilibrium",
        "resonance",
        "curved_single",
        "curved_double",
        "inhibit",
        "dotted",
    }
)
DOCUMENT_SETTINGS_KEY_MEMBERS = frozenset(
    {
        "bond_length_px",
        "arrow_line_width",
        "arrow_head_scale",
        "orbital_phase_enabled",
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
        "sheet_size",
        "sheet_orientation",
    }
)
DOCUMENT_STATE_MODULE = "app/chemvas/domain/document/state.py"


def test_arrow_kinds_are_listed_in_one_module() -> None:
    """The seven arrow kind strings are spelled out exactly once.

    Seven modules used to list them. An eighth kind added to the schema but
    missed in one of the copies is silent: the document validates it while a
    scene, an outline, an attach route, or a tool treats it as something else.
    Supersets are fine as long as they union the schema's frozenset instead of
    relisting the members.
    """
    owners = _modules_listing(ARROW_KIND_MEMBERS)

    assert [owner.rsplit(":", 1)[0] for owner in owners] == [DOCUMENT_STATE_MODULE]


def test_document_settings_keys_are_listed_in_one_module() -> None:
    """The twenty document-settings keys are spelled out exactly once."""
    owners = _modules_listing(DOCUMENT_SETTINGS_KEY_MEMBERS)

    assert [owner.rsplit(":", 1)[0] for owner in owners] == [DOCUMENT_STATE_MODULE]


def _spells_out_its_value(node: ast.expr) -> bool:
    """True when the source spells the expression's value out in full."""
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return False
    return True


def _body_after_docstring(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.stmt]:
    """The function's statements, with a leading docstring dropped."""
    first = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return node.body[1:]
    return node.body


def _getattr_forwarding_wrappers(source: str) -> list[tuple[int, str]]:
    """Functions whose whole body forwards to ``getattr``.

    The builtin already is that function, so the wrapper buys a name and
    nothing else. The attribute may arrive as a parameter or be hardcoded as a
    string, the default may be a parameter or any value the source spells out,
    and the two- and three-argument forms both count. A docstring above the
    ``return`` does not change the shape.

    Deliberately not matched, because each is a different function rather than
    a pass-through:

    * a helper that passes a module-private sentinel as the default. The
      caller cannot spell that value, so "no such attribute" comes back
      distinguishable from "the attribute is None".
    * a wrapper whose target is not one of its own parameters, which reads a
      fixed object instead of forwarding the caller's.
    """
    wrappers: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = _body_after_docstring(node)
        if len(body) != 1:
            continue
        statement = body[0]
        if not isinstance(statement, ast.Return):
            continue
        call = statement.value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "getattr"
            and not call.keywords
            and len(call.args) in (2, 3)
        ):
            continue
        parameters = {
            argument.arg
            for argument in (
                node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            )
        }
        target, attribute, *default = call.args
        if not isinstance(target, ast.Name) or target.id not in parameters:
            continue
        if isinstance(attribute, ast.Name):
            if attribute.id not in parameters:
                continue
        elif not (
            isinstance(attribute, ast.Constant) and isinstance(attribute.value, str)
        ):
            continue
        if default:
            fallback = default[0]
            if isinstance(fallback, ast.Name):
                if fallback.id not in parameters:
                    continue
            elif not _spells_out_its_value(fallback):
                continue
        wrappers.append((node.lineno, node.name))
    return wrappers


def test_no_production_function_only_forwards_to_getattr() -> None:
    """A wrapper whose whole body forwards to getattr is getattr."""
    violations = [
        f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}: {name}"
        for path in _app_python_files()
        for line_no, name in _getattr_forwarding_wrappers(
            path.read_text(encoding="utf-8")
        )
    ]

    assert violations == []


def test_normalize_3d_has_one_production_owner() -> None:
    """The 3-D unit-vector helper is defined once and re-exported.

    Rotation geometry used to carry its own copy, epsilon and all. Selection
    now re-exports the bond geometry implementation, which is an import, not a
    second ``def``. Bond geometry owns it because that module imports no Qt,
    while the selection package does; the edge only runs the cheap direction.
    """
    owners = [
        path
        for path in _app_python_files()
        if re.search(
            r"^def normalize_3d\b",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    ]

    assert owners == [
        APP_ROOT / "chemvas" / "features" / "rendering" / "bond_geometry.py"
    ]


def test_sha256_hex_pattern_is_compiled_in_one_module() -> None:
    """One module compiles the 64-hex-digit hash pattern."""
    pattern = re.compile(r"re\.compile\(\s*r?[\"\']\[0-9a-f\]\{64\}")
    owners = sorted(
        {
            match.rsplit(":", 2)[0]
            for match in _matching_lines(pattern, _app_python_files())
        }
    )

    assert owners == ["app/chemvas/domain/document/precomplex.py"]


def _inline_color_rollback_handlers(source: str) -> list[int]:
    """Except-handlers that add a colour rollback note themselves.

    ``_run_color_rollback_step`` is the one place that catches a failing
    rollback and annotates the original error; anywhere else doing it inline
    is that helper written out longhand.
    """
    tree = ast.parse(source)
    helper_lines = {
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_run_color_rollback_step"
    }
    helper_bodies = {
        inner
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.lineno in helper_lines
        for inner in ast.walk(node)
    }
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node in helper_bodies:
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "_add_color_rollback_note"
            ):
                violations.append(inner.lineno)
    return sorted(set(violations))


def test_color_rollback_notes_go_through_the_step_helper() -> None:
    """No handler expands ``_run_color_rollback_step`` by hand."""
    module = APP_ROOT / "chemvas" / "ui" / "canvas_color_mutation_service.py"
    violations = _inline_color_rollback_handlers(module.read_text(encoding="utf-8"))

    assert violations == []


# --- Single-owner pins for the merged algorithm implementations -------------
#
# Six implementations that used to exist two, three or four times over now
# exist once. Each rule below bans the *shape* of the duplicate rather than
# any phrasing of it, and each was replayed against the tree from before its
# merge to confirm it reports the copies that were really there.


def _called_function_names(node: ast.AST) -> set[str]:
    """Every name called anywhere inside ``node``, plain or as an attribute."""
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            names.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            names.add(child.func.attr)
    return names


WORKLIST_TAKE_METHODS = frozenset({"pop", "popleft"})
WORKLIST_PUT_METHODS = frozenset({"append", "appendleft", "extend"})
GRAPH_ALGORITHMS_MODULE = "app/chemvas/ui/graph_algorithms.py"


def _drained_worklist_name(node: ast.While) -> str | None:
    """The worklist a ``while`` loop runs until empty, if it is written as one.

    ``while stack:`` and ``while len(stack) > 0:`` are the same loop, so both
    spellings answer with the name.
    """
    test = node.test
    if isinstance(test, ast.Name):
        return test.id
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        for side in (test.left, test.comparators[0]):
            if (
                isinstance(side, ast.Call)
                and isinstance(side.func, ast.Name)
                and side.func.id == "len"
                and len(side.args) == 1
                and isinstance(side.args[0], ast.Name)
            ):
                return side.args[0].id
    return None


def _method_calls_on_name(node: ast.AST, name: str) -> set[str]:
    """The method names called on the local variable ``name`` inside ``node``."""
    return {
        child.func.attr
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and isinstance(child.func.value, ast.Name)
        and child.func.value.id == name
    }


def _iterates_a_neighbour_mapping(node: ast.AST) -> bool:
    """True when something inside ``node`` loops over ``mapping[x]``/``.get(x)``.

    That is what separates a graph walk from a worklist over a tree of
    objects, which reaches its next items by calling a method on the item.
    """
    for child in ast.walk(node):
        if not isinstance(child, (ast.For, ast.AsyncFor, ast.comprehension)):
            continue
        source = child.iter
        if isinstance(source, ast.Subscript) and isinstance(source.value, ast.Name):
            return True
        if (
            isinstance(source, ast.Call)
            and isinstance(source.func, ast.Attribute)
            and source.func.attr == "get"
            and isinstance(source.func.value, ast.Name)
        ):
            return True
    return False


def _marks_a_visited_set(node: ast.AST, worklist: str) -> bool:
    """True when ``node`` calls ``.add`` on some set other than the worklist."""
    return any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "add"
        and isinstance(child.func.value, ast.Name)
        and child.func.value.id != worklist
        for child in ast.walk(node)
    )


def _loop_nested_while_loops(tree: ast.AST) -> set[int]:
    """``id()`` of every ``while`` that sits inside another loop."""
    nested: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            continue
        for child in ast.walk(node):
            if child is not node and isinstance(child, ast.While):
                nested.add(id(child))
    return nested


def _seeded_reachability_walks(source: str) -> list[int]:
    """Line numbers of every seeded depth-or-breadth-first reachability walk.

    The shape, not the wording: a ``while`` loop that drains a worklist, takes
    from it, puts back into it, marks a separate visited set, and reaches its
    next candidates through a neighbour mapping. List or ``deque``, ``pop`` or
    ``popleft``, ``adjacency[x]`` or ``adjacency.get(x)`` all read the same.

    Deliberately out of scope, so that this stays a rule about the one walk
    that was merged rather than a ban on graph code:

    * a walk nested inside another loop. Those enumerate components or roots
      -- ``domain.document.graph``, ``selection_rotation_planarity``,
      ``core.rdkit_conversion`` and the spanning forest in this same module --
      which is a different question from "what does this seed reach".
    * a walk that records where it has been in a dict rather than a set, the
      way the shortest-cycle search in this module records predecessors.
    * a recursive walk, which has no worklist to drain.
    """
    tree = ast.parse(source)
    nested = _loop_nested_while_loops(tree)
    walks: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.While) or id(node) in nested:
            continue
        worklist = _drained_worklist_name(node)
        if worklist is None:
            continue
        methods = _method_calls_on_name(node, worklist)
        if not (methods & WORKLIST_TAKE_METHODS):
            continue
        if not (methods & WORKLIST_PUT_METHODS):
            continue
        if not _marks_a_visited_set(node, worklist):
            continue
        if not _iterates_a_neighbour_mapping(node):
            continue
        walks.append(node.lineno)
    return walks


def test_seeded_graph_reachability_is_walked_in_one_place() -> None:
    """One seeded reachability walk exists under ``app/``.

    ``graph_algorithms`` spelled the same walk three times -- reach a
    component, answer whether an edge has an alternative path, reach a set of
    seeds -- and the three disagreed about when the target check runs and
    whether the search may stop early. ``_walk_reachable`` is now the only
    one, and a second copy anywhere is what this catches.
    """
    walks = [
        f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}"
        for path in _app_python_files()
        for line_no in _seeded_reachability_walks(path.read_text(encoding="utf-8"))
    ]

    assert [walk.rsplit(":", 1)[0] for walk in walks] == [GRAPH_ALGORITHMS_MODULE]


BOND_CYCLE_CACHE = "bond_cycle_cache"
BOND_CYCLE_CACHE_MUTATORS = frozenset(
    {"clear", "pop", "popitem", "setdefault", "update"}
)
GRAPH_INDEX_OPERATIONS_MODULE = "app/chemvas/ui/graph_index_operations.py"
CANVAS_GRAPH_STATE_MODULE = "app/chemvas/ui/canvas_graph_state.py"
CYCLE_SEARCH_HELPER = "edge_has_reachable_alternative_path"


def _is_bond_cycle_cache(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == BOND_CYCLE_CACHE


def _bond_cycle_cache_writes(source: str) -> list[int]:
    """Line numbers where something writes the bond-cycle cache.

    A write is an assignment to the attribute or to a slot of it, or a call to
    one of the mapping methods that mutate. Reads -- ``.get``, ``in``,
    subscripting on the right-hand side -- are not writes, because the point of
    the pin is that one place decides what freshness means.
    """
    writes: list[int] = []
    for node in ast.walk(ast.parse(source)):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            if _is_bond_cycle_cache(target) or (
                isinstance(target, ast.Subscript) and _is_bond_cycle_cache(target.value)
            ):
                writes.append(node.lineno)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in BOND_CYCLE_CACHE_MUTATORS
            and _is_bond_cycle_cache(node.func.value)
        ):
            writes.append(node.lineno)
    return sorted(set(writes))


def test_bond_cycle_cache_has_one_writer() -> None:
    """Only ``cached_bond_in_cycle`` writes entries into the bond-cycle cache.

    The graph service and the rotation planarity helper each used to compute
    the answer and store it, so the rule that an entry is valid while
    ``graph_version`` is unchanged was written down twice and could drift on
    one side. ``canvas_graph_state`` still appears because it declares the
    field and empties it when the graph changes; that is the state owner
    resetting its own slot, not a second author of entries.

    What escapes: a writer that reaches the mapping through a local alias
    (``cache = graph.bond_cycle_cache``), because the attribute is no longer
    named at the write.
    """
    writers = sorted(
        {
            f"{path.relative_to(APP_ROOT.parents[0])}"
            for path in _app_python_files()
            if _bond_cycle_cache_writes(path.read_text(encoding="utf-8"))
        }
    )

    assert writers == [CANVAS_GRAPH_STATE_MODULE, GRAPH_INDEX_OPERATIONS_MODULE]


def _modules_using(name: str) -> list[str]:
    """Modules that import or call ``name``, however they spell the import."""
    users: list[str] = []
    for path in _app_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                alias.name == name for alias in node.names
            ):
                used = True
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name
            ):
                used = True
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == name
            ):
                used = True
        if used:
            users.append(str(path.relative_to(APP_ROOT.parents[0])))
    return sorted(users)


def test_cycle_membership_is_decided_in_one_module() -> None:
    """One module turns the alternative-path search into "is this bond cyclic".

    That search is the whole of ``bond_in_cycle``; a second consumer of it is
    a second implementation of the question, cache or no cache. Importing it
    under another name still counts, because the import is read rather than
    the call.
    """
    assert _modules_using(CYCLE_SEARCH_HELPER) == [GRAPH_INDEX_OPERATIONS_MODULE]


HISTORY_COMMANDS_MODULE = "app/chemvas/ui/history_commands.py"
GROUP_TRANSACTION_HELPER = "_run_group_state_transaction"
GROUP_COMMAND_CLASSES = ("GroupSceneItemsCommand", "UngroupSceneItemsCommand")
GROUP_STATE_CALLS = frozenset(
    {
        "_group_state_snapshot",
        "_restore_group_state",
        "group_state_for",
        "remove_group_for",
        "restore_group_for",
        "set_group_for",
    }
)
SCENE_RUNTIME_CAPTURE = "capture_scene_runtime"


def _group_rollback_scaffolds(source: str) -> list[tuple[int, str]]:
    """Functions that capture the scene runtime *and* touch group state.

    That pair is what a group rollback scaffold is: the runtime snapshot is
    the thing being protected, group state is what is being changed. A
    re-inlined copy has to do both however it names its locals, so the pin
    does not depend on the copy calling ``_group_state_snapshot``.
    """
    scaffolds: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        called = _called_function_names(node)
        if SCENE_RUNTIME_CAPTURE in called and called & GROUP_STATE_CALLS:
            scaffolds.append((node.lineno, node.name))
    return scaffolds


def _group_command_scaffold_routing(source: str) -> dict[str, bool]:
    """For each group command's ``redo``/``undo``, whether it calls the scaffold."""
    routing: dict[str, bool] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef) or node.name not in GROUP_COMMAND_CLASSES:
            continue
        for member in node.body:
            if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if member.name not in ("redo", "undo"):
                continue
            routing[f"{node.name}.{member.name}"] = (
                GROUP_TRANSACTION_HELPER in _called_function_names(member)
            )
    return routing


def test_group_commands_share_one_rollback_scaffold() -> None:
    """One function owns the group capture / apply / roll-back order.

    ``GroupSceneItemsCommand`` and ``UngroupSceneItemsCommand`` spelled it in
    both ``redo`` and ``undo``: four copies of an ordering -- group state,
    then the command's own compensation, then the outline, then the runtime
    snapshot, then the scene rect -- that only reads correctly when all four
    agree, and two of them did not.

    Only functions that capture the scene runtime count, so a group command
    that mutates state with no rollback at all is a different defect and is
    not caught here.
    """
    history_commands = APP_ROOT / "chemvas" / "ui" / "history_commands.py"
    source = history_commands.read_text(encoding="utf-8")

    scaffolds = [name for _line_no, name in _group_rollback_scaffolds(source)]

    assert scaffolds == [GROUP_TRANSACTION_HELPER]


def test_every_group_command_slot_routes_through_the_scaffold() -> None:
    """All four group command slots reach the scaffold rather than their own."""
    history_commands = APP_ROOT / "chemvas" / "ui" / "history_commands.py"
    routing = _group_command_scaffold_routing(
        history_commands.read_text(encoding="utf-8")
    )

    assert routing == {
        "GroupSceneItemsCommand.redo": True,
        "GroupSceneItemsCommand.undo": True,
        "UngroupSceneItemsCommand.redo": True,
        "UngroupSceneItemsCommand.undo": True,
    }


SCENE_ITEM_ACCESS_MODULE = "app/chemvas/ui/scene_item_access.py"
CANVAS_SCENE_RESOLVERS = frozenset(
    {
        "canvas_scene_for",
        "canvas_scene_for_item_operation",
        "optional_canvas_scene_for",
    }
)
CANVAS_DETACH_BODY = "_detach_item_from_canvas_scene"
TRI_STATE_DETACH_WRAPPER = "remove_attached_item_from_canvas_scene"


def _canvas_scoped_detachers(source: str) -> list[tuple[int, str]]:
    """Functions that resolve the canvas's own scene and then detach from it.

    The scene-scoped clears in ``hover_rendering``, ``preview_scene_renderer``,
    ``bond_preview_renderer`` and ``features.selection.handles`` are a
    different function and stay out: they are handed a scene rather than
    resolving one from a canvas, and the commit that merged this pair records
    why they are not merged with each other either.
    """
    detachers: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        called = _called_function_names(node)
        if "removeItem" in called and called & CANVAS_SCENE_RESOLVERS:
            detachers.append((node.lineno, node.name))
    return detachers


def test_canvas_scoped_scene_detach_has_one_body() -> None:
    """One function detaches an item from the canvas's own scene.

    Two wrappers used to spell the same fifteen lines, differing only in what
    they answer when the canvas has no scene or the item's C++ object is gone.
    Both now pass that answer to ``_detach_item_from_canvas_scene`` as
    ``unresolved``.
    """
    detachers = [
        f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}: {name}"
        for path in _app_python_files()
        for line_no, name in _canvas_scoped_detachers(path.read_text(encoding="utf-8"))
    ]

    assert [detacher.rsplit(":", 2)[0] for detacher in detachers] == [
        SCENE_ITEM_ACCESS_MODULE
    ]
    assert [detacher.rsplit(": ", 1)[1] for detacher in detachers] == [
        CANVAS_DETACH_BODY
    ]


def _return_annotation_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> frozenset[str]:
    """The leaf names of a return annotation, with ``None`` spelled as a name.

    ``bool | None``, ``None | bool`` and ``Optional[bool]`` all answer
    ``{"bool", "None"}``; a bare ``bool`` answers ``{"bool"}``.
    """
    names: set[str] = set()
    annotation = node.returns
    if annotation is None:
        return frozenset()
    for child in ast.walk(annotation):
        if isinstance(child, ast.Name) and child.id != "Optional":
            names.add(child.id)
        elif isinstance(child, ast.Constant) and child.value is None:
            names.add("None")
    return frozenset(names)


def test_attached_scene_detach_keeps_its_third_answer() -> None:
    """The tri-state detach result stays a tri-state.

    ``SceneItemLifecycleService.remove_scene_item`` reads ``None`` as "stop"
    and ``False`` as "carry on": a ``False`` item was provably never in this
    scene, so ring-fill bond geometry can be refreshed against it, while a
    ``None`` item may have been and reading it would raise. Narrowing either
    signature to ``bool`` would start refreshing geometry against dead items,
    and the merged body is exactly where that narrowing would look harmless.
    """
    scene_item_access = APP_ROOT / "chemvas" / "ui" / "scene_item_access.py"
    tree = ast.parse(scene_item_access.read_text(encoding="utf-8"))
    annotations = {
        node.name: _return_annotation_names(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {CANVAS_DETACH_BODY, TRI_STATE_DETACH_WRAPPER}
    }

    assert annotations == {
        CANVAS_DETACH_BODY: frozenset({"bool", "None"}),
        TRI_STATE_DETACH_WRAPPER: frozenset({"bool", "None"}),
    }


SOURCE_GEOMETRY_KEY_MEMBERS = frozenset(
    {
        "rdkit_version",
        "rdkit_formal_charge",
        "rdkit_radical_electrons",
        "electron_count",
        "geometry_embedding",
        "geometry_random_seed",
        "geometry_optimization_policy",
        "geometry_optimization_result",
        "mol_atom_count",
        "xyz_atom_count",
        "atom_map",
    }
)
CALCULATION_BUNDLE_MODULE = "app/chemvas/bootstrap/calculation_bundle.py"
PRECOMPLEX_SCHEMA_MODULE = "app/chemvas/domain/document/precomplex.py"


def _dict_literal_key_sets(tree: ast.AST) -> list[tuple[int, frozenset[str]]]:
    """Every mapping whose string keys the source spells out, with its line.

    A ``{...}`` display and a ``dict(...)`` call with keywords are the same
    mapping written two ways, so both count. A comprehension does not: its
    keys come from somewhere else, and that somewhere is where they are
    spelled -- which ``_string_set_literals`` reads.
    """
    key_sets: list[tuple[int, frozenset[str]]] = []
    for node in ast.walk(tree):
        keys: list[str] = []
        if isinstance(node, ast.Dict):
            keys = [
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "dict"
        ):
            keys = [keyword.arg for keyword in node.keywords if keyword.arg is not None]
        else:
            continue
        if keys:
            key_sets.append((node.lineno, frozenset(keys)))
    return key_sets


def _modules_spelling_out(members: frozenset[str]) -> list[str]:
    """Modules that write every one of ``members`` out as keys or as strings."""
    owners: list[str] = []
    for path in _app_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        spellings = _dict_literal_key_sets(tree) + _string_set_literals(tree)
        for line_no, spelled in sorted(spellings, key=lambda entry: entry[0]):
            if members <= spelled:
                owners.append(f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}")
    return owners


def test_precomplex_source_geometry_keys_are_spelled_twice_on_purpose() -> None:
    """The eleven geometry keys appear once as a fingerprint, once as a schema.

    ``calculation_bundle`` wrote the fingerprint out three times -- store it,
    then rebuild it at each of two reproducibility checks -- so a twelfth
    field added to ``CalculationArtifacts`` and pasted into two of the three
    would leave a bundle claiming a reproducibility it does not have.
    ``_source_geometry_fingerprint`` produces it now.

    ``domain.document.precomplex._validate_source_geometry`` is the second
    entry and is not a copy: it checks a *stored* mapping against the schema
    rather than reproducing one from artifacts, and it lives in the layer that
    owns the document format. Two entries is the rule; a third anywhere, or a
    second inside either module, is a duplicate.

    Both the mapping and the bare list of names count, because rebuilding the
    fingerprint through ``{name: getattr(artifacts, name) for name in NAMES}``
    is the same duplicate with the keys moved one line up.
    """
    owners = _modules_spelling_out(SOURCE_GEOMETRY_KEY_MEMBERS)

    assert [owner.rsplit(":", 1)[0] for owner in owners] == [
        CALCULATION_BUNDLE_MODULE,
        PRECOMPLEX_SCHEMA_MODULE,
    ]


RING_FILL_SCENE_SERVICE_MODULE = "app/chemvas/ui/canvas_ring_fill_scene_service.py"
RING_ATOM_IDS_ITEM_ROLE = 2


def _ring_atom_role_reads(tree: ast.AST) -> set[int]:
    """``id()`` of every call that reads a scene item's ring-atom-ids role.

    ``item.data(2)`` is the spelling in the tree today; a module-level
    constant bound to ``2`` and passed by name is the same read, so both
    resolve. ``data(1)`` and the rest do not, which is what keeps the mark and
    handle payload readers out of this.
    """
    role_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and node.value.value == RING_ATOM_IDS_ITEM_ROLE
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    reads: set[int] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "data"
            and len(node.args) == 1
            and not node.keywords
        ):
            continue
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and argument.value == (
            RING_ATOM_IDS_ITEM_ROLE
        ):
            reads.add(id(node))
        elif isinstance(argument, ast.Name) and argument.id in role_names:
            reads.add(id(node))
    return reads


def _ring_polygon_rebuilders(source: str) -> list[tuple[int, str]]:
    """Functions that re-fit a ring polygon to the atoms it is drawn over.

    Two independent marks, either of which is enough: the function reads the
    ring-atom-ids role, or it resolves atoms by id. Both sit next to a
    ``setPolygon``, and a rebuild cannot avoid both -- it has to learn which
    atoms the ring names, and it has to find them.

    Not caught: setting a polygon that arrives already built, which is what
    ``history_canvas_access`` restores and what ``canvas_model_access``
    rescales.
    """
    tree = ast.parse(source)
    role_reads = _ring_atom_role_reads(tree)
    rebuilders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        called = _called_function_names(node)
        if "setPolygon" not in called:
            continue
        reads_role = any(id(child) in role_reads for child in ast.walk(node))
        if reads_role or "atom_for_id" in called:
            rebuilders.append((node.lineno, node.name))
    return rebuilders


def test_ring_fill_polygons_are_rebuilt_in_one_place() -> None:
    """One function refits ring-fill polygons to their atoms.

    ``CanvasMoveController.move_rings_for_atoms`` and
    ``CanvasRingFillSceneService.update_ring_fills_for_atoms`` carried the same
    fourteen lines. The service owns ring-fill scene items, so
    ``rebuild_ring_fill_polygons`` lives there and the move controller calls
    it; the two entry points stay because the move controller is deliberately
    service-free.
    """
    rebuilders = [
        f"{path.relative_to(APP_ROOT.parents[0])}:{line_no}: {name}"
        for path in _app_python_files()
        for line_no, name in _ring_polygon_rebuilders(path.read_text(encoding="utf-8"))
    ]

    assert [rebuilder.rsplit(":", 2)[0] for rebuilder in rebuilders] == [
        RING_FILL_SCENE_SERVICE_MODULE
    ]
