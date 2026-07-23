from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CHEMVAS_ROOT = Path(__file__).resolve().parents[1] / "app" / "chemvas"
APP_ROOT = CHEMVAS_ROOT.parent
TARGET_LAYERS = frozenset(("domain", "features", "adapters", "shell", "bootstrap"))
REMOVED_COMPATIBILITY_MODULES = frozenset(
    {
        "chemvas.core.document_state",
        "chemvas.core.model",
        "chemvas.core.rdkit_types",
        "chemvas.file_open",
        "chemvas.main",
        "chemvas.ui.active_tool_reference",
        "chemvas.ui.benzene_preview_access",
        "chemvas.ui.benzene_preview_renderer",
        "chemvas.ui.benzene_preview_scene_access",
        "chemvas.ui.benzene_preview_service",
        "chemvas.ui.bond_hover_preview_service",
        "chemvas.ui.bond_preview_geometry",
        "chemvas.ui.bond_preview_scene_items",
        "chemvas.ui.bond_dotted_geometry",
        "chemvas.ui.bond_geometry_primitives",
        "chemvas.ui.bond_graphics_logic",
        "chemvas.ui.bond_stereo_geometry",
        "chemvas.ui.bond_style_logic",
        "chemvas.ui.bracket_types",
        "chemvas.ui.canvas_hover_refresh",
        "chemvas.ui.canvas_auxiliary_service_bundle",
        "chemvas.ui.canvas_bond_renderer_state",
        "chemvas.ui.canvas_rotation_preview_controller",
        "chemvas.ui.canvas_rotation_preview_state",
        "chemvas.ui.canvas_rdkit_state",
        "chemvas.ui.canvas_renderer_state",
        "chemvas.ui.canvas_service_types",
        "chemvas.ui.handle_interaction_logic",
        "chemvas.ui.history_command_snapshot",
        "chemvas.ui.history_recovery_note",
        "chemvas.ui.history_restore_retry",
        "chemvas.ui.history_stack_snapshot",
        "chemvas.ui.hover_highlight_access",
        "chemvas.ui.hover_highlight_logic",
        "chemvas.ui.hover_interaction_access",
        "chemvas.ui.hover_interaction_service",
        "chemvas.ui.hover_scene_access",
        "chemvas.ui.hover_scene_renderer",
        "chemvas.ui.hover_scene_service",
        "chemvas.ui.hover_service_bundle",
        "chemvas.ui.label_layout_logic",
        "chemvas.ui.main_window",
        "chemvas.ui.main_window_app",
        "chemvas.ui.main_window_bootstrap",
        "chemvas.ui.main_window_services",
        "chemvas.ui.mark_hover_preview_service",
        "chemvas.ui.note_html_sanitizer",
        "chemvas.ui.ring_occupancy_logic",
        "chemvas.ui.scene_item_attach_snapshot",
        "chemvas.ui.scene_rect_snapshot",
        "chemvas.ui.scene_transform_logic",
        "chemvas.ui.selection_access",
        "chemvas.ui.selection_center_logic",
        "chemvas.ui.selection_hit_logic",
        "chemvas.ui.selection_outline_paths",
        "chemvas.ui.selection_press_logic",
        "chemvas.ui.selection_rotation_geometry",
        "chemvas.ui.selection_rotation_logic",
        "chemvas.ui.session_autosave_hook",
        "chemvas.ui.session_snapshot_logic",
        "chemvas.ui.shape_geometry",
        "chemvas.ui.smiles_insert_logic",
        "chemvas.ui.structure_growth_logic",
        "chemvas.ui.structure_insert_service",
        "chemvas.ui.structure_payload_logic",
        "chemvas.ui.template_insert_logic",
        "chemvas.ui.template_preview_logic",
    }
)
BOOTSTRAP_LEGACY_COMPOSITION_MODULES = frozenset(
    {
        "chemvas.bootstrap.application",
        "chemvas.bootstrap.file_open",
        "chemvas.bootstrap.main_window",
        "chemvas.bootstrap.main_window_runtime",
        "chemvas.bootstrap.main_window_services",
    }
)

FEATURE_QT_MIGRATION_ALLOWLIST = frozenset(
    {
        "chemvas.features.annotations.shape_geometry",
        "chemvas.features.export.painting",
        "chemvas.features.export.raster",
        "chemvas.features.export.scope",
        "chemvas.features.export.service",
        "chemvas.features.export.vector",
        "chemvas.features.insertion.ring_occupancy",
        "chemvas.features.insertion.structure_growth",
        "chemvas.features.rendering.bond_dotted",
        "chemvas.features.rendering.bond_geometry",
        "chemvas.features.rendering.bond_stereo",
        "chemvas.features.selection.center",
        "chemvas.features.selection.handles",
        "chemvas.features.selection.outline",
        "chemvas.features.selection.rotation",
        "chemvas.features.session.autosave",
    }
)


@dataclass(frozen=True, slots=True)
class ImportEdge:
    source: str
    dependency: str
    path: Path
    line: int


def _module_name(path: Path) -> str:
    relative = path.relative_to(CHEMVAS_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(("chemvas", *parts))


def _resolved_from_module(
    source: str,
    path: Path,
    node: ast.ImportFrom,
) -> str:
    if not node.level:
        return node.module or ""
    package = source if path.name == "__init__.py" else source.rpartition(".")[0]
    package_parts = package.split(".") if package else []
    keep_count = max(0, len(package_parts) - node.level + 1)
    parts = package_parts[:keep_count]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _import_edges() -> list[ImportEdge]:
    module_paths = {
        _module_name(path): path for path in sorted(CHEMVAS_ROOT.rglob("*.py"))
    }
    edges: list[ImportEdge] = []
    for source, path in module_paths.items():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            dependencies: list[str] = []
            if isinstance(node, ast.Import):
                dependencies.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_from = _resolved_from_module(source, path, node)
                if node.module or not node.level:
                    dependencies.append(imported_from)
                    dependencies.extend(
                        candidate
                        for alias in node.names
                        if (candidate := f"{imported_from}.{alias.name}")
                        in module_paths
                        or candidate in REMOVED_COMPATIBILITY_MODULES
                    )
                else:
                    dependencies.extend(
                        candidate
                        for alias in node.names
                        if (candidate := f"{imported_from}.{alias.name}")
                        in module_paths
                    )
            for dependency in dependencies:
                if dependency:
                    edges.append(ImportEdge(source, dependency, path, node.lineno))
    return edges


def _layer(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "chemvas" and parts[1] in TARGET_LAYERS:
        return parts[1]
    return None


def _formatted(edge: ImportEdge) -> str:
    relative = edge.path.relative_to(CHEMVAS_ROOT.parents[1])
    return f"{relative}:{edge.line}: {edge.source} -> {edge.dependency}"


def test_target_layer_packages_exist() -> None:
    assert {
        path.name
        for path in CHEMVAS_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    } >= TARGET_LAYERS


def test_target_layer_dependency_direction() -> None:
    forbidden_layers = {
        "domain": {"features", "adapters", "shell", "bootstrap"},
        "features": {"adapters", "shell", "bootstrap"},
        "adapters": {"shell", "bootstrap"},
        "shell": {"adapters", "bootstrap"},
        "bootstrap": set(),
    }
    violations: list[str] = []
    for edge in _import_edges():
        source_layer = _layer(edge.source)
        dependency_layer = _layer(edge.dependency)
        if source_layer is None or dependency_layer is None:
            continue
        if dependency_layer in forbidden_layers[source_layer]:
            violations.append(_formatted(edge))

    assert violations == []


def test_non_bootstrap_layers_do_not_depend_on_legacy_core_or_ui() -> None:
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if _layer(edge.source) not in {None, "bootstrap"}
        and (
            edge.dependency in {"chemvas.core", "chemvas.ui"}
            or edge.dependency.startswith(("chemvas.core.", "chemvas.ui."))
        )
    ]

    assert violations == []


def test_bootstrap_legacy_dependencies_are_confined_to_composition_modules() -> None:
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if _layer(edge.source) == "bootstrap"
        and edge.source not in BOOTSTRAP_LEGACY_COMPOSITION_MODULES
        and edge.dependency.startswith(("chemvas.core", "chemvas.ui"))
    ]

    assert violations == []


def test_domain_has_no_framework_or_adapter_dependencies() -> None:
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if _layer(edge.source) == "domain"
        and (edge.dependency.startswith(("PyQt6", "rdkit", "chemvas.adapters")))
    ]

    assert violations == []


def test_feature_qt_dependencies_match_shrinking_migration_inventory() -> None:
    direct_qt_modules = {
        edge.source
        for edge in _import_edges()
        if _layer(edge.source) == "features" and edge.dependency.startswith("PyQt6")
    }

    assert direct_qt_modules == FEATURE_QT_MIGRATION_ALLOWLIST


def test_migrated_selection_runtime_types_do_not_reintroduce_public_any() -> None:
    paths = [
        CHEMVAS_ROOT / "features" / "selection" / "active_tool.py",
        CHEMVAS_ROOT / "features" / "selection" / "outline.py",
    ]

    assert all("from typing import Any" not in path.read_text() for path in paths)


def test_hover_feature_policy_is_qt_and_adapter_free() -> None:
    hover_package = "chemvas.features.hover"
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if (edge.source == hover_package or edge.source.startswith(f"{hover_package}."))
        and edge.dependency.startswith(("PyQt6", "rdkit", "chemvas.adapters"))
    ]

    assert violations == []


def test_hover_feature_import_does_not_load_qt() -> None:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        import_path for import_path in (str(APP_ROOT), pythonpath) if import_path
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import chemvas.features.hover; "
                "assert not any(name == 'PyQt6' or name.startswith('PyQt6.') "
                "for name in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_rdkit_adapter_import_does_not_load_qt() -> None:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(APP_ROOT), pythonpath) if path
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from chemvas.core.rdkit_adapter import RDKitAdapter; "
                "assert RDKitAdapter is not None; "
                "assert not any(name == 'PyQt6' or name.startswith('PyQt6.') "
                "for name in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_production_code_does_not_import_removed_compatibility_modules() -> None:
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if edge.dependency in REMOVED_COMPATIBILITY_MODULES
    ]

    assert violations == []


def test_removed_compatibility_module_files_stay_absent() -> None:
    remaining: list[str] = []
    for module in sorted(REMOVED_COMPATIBILITY_MODULES):
        relative = Path(*module.split(".")[1:]).with_suffix(".py")
        path = CHEMVAS_ROOT / relative
        if path.exists():
            remaining.append(str(path.relative_to(CHEMVAS_ROOT.parents[1])))

    assert remaining == []


def test_main_window_shell_is_constructed_only_by_bootstrap() -> None:
    consumers = [
        _formatted(edge)
        for edge in _import_edges()
        if edge.dependency == "chemvas.shell.main_window"
        and edge.source != "chemvas.bootstrap.main_window"
    ]

    assert consumers == []


def test_window_registry_does_not_know_ui_services() -> None:
    registry = CHEMVAS_ROOT / "bootstrap" / "window_registry.py"
    source = registry.read_text()

    assert "chemvas.ui" not in source
    assert "services_for_window" not in source


def test_drag_transaction_uses_shared_object_graph_savepoints() -> None:
    drag = CHEMVAS_ROOT / "ui" / "selection_drag_tool.py"
    source = drag.read_text()

    assert "chemvas.ui.transactions.object_graph_snapshot" in source
    assert "chemvas.ui.canvas_delete_transaction import" not in source


def test_concrete_adapters_are_known_only_by_adapters_and_bootstrap() -> None:
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if edge.dependency.startswith("chemvas.adapters.")
        and _layer(edge.source) not in {"adapters", "bootstrap"}
    ]

    assert violations == []


def test_cross_feature_imports_use_package_public_api() -> None:
    violations: list[str] = []
    for edge in _import_edges():
        source_parts = edge.source.split(".")
        dependency_parts = edge.dependency.split(".")
        if len(source_parts) < 3 or source_parts[:2] != ["chemvas", "features"]:
            continue
        if (
            len(dependency_parts) <= 3
            or dependency_parts[:2] != ["chemvas", "features"]
            or dependency_parts[2] == source_parts[2]
        ):
            continue
        violations.append(_formatted(edge))

    assert violations == []


def test_export_callers_use_feature_public_api() -> None:
    export_package = "chemvas.features.export"
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if not (
            edge.source == export_package
            or edge.source.startswith(f"{export_package}.")
        )
        and edge.dependency.startswith(f"{export_package}.")
    ]

    assert violations == []


def test_hover_callers_use_feature_public_api() -> None:
    hover_package = "chemvas.features.hover"
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if not (
            edge.source == hover_package or edge.source.startswith(f"{hover_package}.")
        )
        and edge.dependency.startswith(f"{hover_package}.")
    ]

    assert violations == []
