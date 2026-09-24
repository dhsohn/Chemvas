from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

CHEMVAS_ROOT = Path(__file__).resolve().parents[1] / "app" / "chemvas"
APP_ROOT = CHEMVAS_ROOT.parent
TARGET_LAYERS = frozenset(("domain", "features", "adapters", "shell", "bootstrap"))
REMOVED_COMPATIBILITY_MODULES = frozenset(
    {
        "chemvas.ui.main_window_canvas_tab_ui_service",
        "chemvas.ui.note_selection_box",
        "chemvas.core.document_state",
        "chemvas.core.model",
        "chemvas.core.rdkit_types",
        "chemvas.core.renderer",
        "chemvas.core.style_acs1996",
        "chemvas.domain.transactions.bound_attribute",
        "chemvas.domain.transactions.history_authority",
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
        "chemvas.ui.history_push_failure_recovery",
        "chemvas.ui.history_recovery_note",
        "chemvas.ui.history_restore_retry",
        "chemvas.ui.history_stack_snapshot",
        "chemvas.ui.canvas_delete_transaction",
        "chemvas.ui.graph_algorithms",
        "chemvas.ui.graph_index_operations",
        "chemvas.ui.graph_rotation_policy",
        "chemvas.ui.transactions.history_command",
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
        "chemvas.ui.main_window_arrow_icon_renderer",
        "chemvas.ui.main_window_bond_icon_renderer",
        "chemvas.ui.main_window_bootstrap",
        "chemvas.ui.main_window_icon_canvas_style",
        "chemvas.ui.main_window_services",
        "chemvas.ui.main_window_template_icon_renderer",
        "chemvas.ui.main_window_tool_icon_renderer",
        "chemvas.ui.main_window_utility_icon_renderer",
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
        "chemvas.ui.structure_fragment_build_service",
        "chemvas.ui.structure_insert_service",
        "chemvas.ui.structure_payload_logic",
        "chemvas.ui.structure_template_build_service",
        "chemvas.ui.structure_template_commands",
        "chemvas.ui.template_insert_logic",
        "chemvas.ui.template_preview_logic",
        "chemvas.ui.tools",
    }
)


@dataclass(frozen=True)
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


@cache
def _import_edges() -> tuple[ImportEdge, ...]:
    module_paths = {
        _module_name(path): path for path in sorted(CHEMVAS_ROOT.rglob("*.py"))
    }
    edges: list[ImportEdge] = []
    for source, path in module_paths.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
    return tuple(edges)


def _feature_public_api_violations(
    edges: tuple[ImportEdge, ...],
) -> tuple[ImportEdge, ...]:
    violations: list[ImportEdge] = []
    for edge in edges:
        dependency_parts = edge.dependency.split(".")
        if len(dependency_parts) <= 3 or dependency_parts[:2] != [
            "chemvas",
            "features",
        ]:
            continue

        feature_package = ".".join(dependency_parts[:3])
        if edge.source == feature_package or edge.source.startswith(
            f"{feature_package}."
        ):
            continue
        violations.append(edge)
    return tuple(violations)


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


def test_import_edge_inventory_is_cached_and_immutable() -> None:
    edges = _import_edges()

    assert isinstance(edges, tuple)
    assert _import_edges() is edges


def test_target_layer_dependency_direction() -> None:
    forbidden_layers = {
        "domain": {"features", "adapters", "shell", "bootstrap"},
        "features": {"shell", "bootstrap"},
        "adapters": {"shell", "bootstrap"},
        "shell": {"bootstrap"},
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


# Explicit operation entry points; document plan schema/preservation is outside
# this set and stays available if Calculation support is later retired.
CALCULATION_OPERATION_CALLERS = {
    "chemvas.features.calculation_bundle": frozenset(
        {"chemvas.bootstrap.calculation_bundle", "chemvas.ui.calculation_step_dialog"}
    ),
    "chemvas.bootstrap.calculation_bundle": frozenset(
        {"chemvas.bootstrap.application"}
    ),
    "chemvas.ui.calculation_step_dialog": frozenset(
        {"chemvas.ui.main_window_menu_bar"}
    ),
    "chemvas.ui.calculation_mapping_highlight": frozenset(
        {"chemvas.ui.calculation_step_dialog"}
    ),
}


def _calculation_boundary_violations(
    edges: tuple[ImportEdge, ...],
) -> tuple[ImportEdge, ...]:
    return tuple(
        edge
        for edge in edges
        for operation, callers in CALCULATION_OPERATION_CALLERS.items()
        if (edge.dependency == operation or edge.dependency.startswith(operation + "."))
        and not (edge.source == operation or edge.source.startswith(operation + "."))
        and edge.source not in callers
    )


def test_general_editing_does_not_depend_on_the_calculation_feature() -> None:
    assert [
        _formatted(edge) for edge in _calculation_boundary_violations(_import_edges())
    ] == []


def test_calculation_boundary_rejects_new_consumers_and_allows_registrations() -> None:
    for operation, callers in CALCULATION_OPERATION_CALLERS.items():
        for consumer in (
            "chemvas.core.document_io",
            "chemvas.features.document_patch.service",
            "chemvas.ui.canvas_document_state",
            "chemvas.features.export.service",
        ):
            edge = ImportEdge(consumer, operation, CHEMVAS_ROOT / "injected.py", 1)
            assert _calculation_boundary_violations((edge,)) == (edge,)
        for consumer in callers | {operation + ".service"}:
            edge = ImportEdge(consumer, operation, CHEMVAS_ROOT / "injected.py", 1)
            assert _calculation_boundary_violations((edge,)) == ()


def test_domain_has_no_framework_or_adapter_dependencies() -> None:
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if _layer(edge.source) == "domain"
        and (edge.dependency.startswith(("PyQt6", "rdkit", "chemvas.adapters")))
    ]

    assert violations == []


def test_migrated_selection_runtime_types_do_not_reintroduce_public_any() -> None:
    paths = [
        CHEMVAS_ROOT / "features" / "selection" / "active_tool.py",
        CHEMVAS_ROOT / "features" / "selection" / "outline.py",
    ]

    assert all(
        "from typing import Any" not in path.read_text(encoding="utf-8")
        for path in paths
    )


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


def test_headless_document_api_does_not_require_image_or_gui_dependencies() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from chemvas.bootstrap.application import main; "
                "from chemvas.domain.document import MoleculeModel, validate_image_states; "
                "assert callable(main); assert MoleculeModel is not None; "
                "assert validate_image_states([]) is None; "
                "assert not any(name.split('.')[0] in {'PIL', 'PyQt6'} "
                "for name in sys.modules)"
            ),
            str(APP_ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
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
    source = registry.read_text(encoding="utf-8")

    assert "chemvas.ui" not in source
    assert "services_for_window" not in source


def test_drag_transaction_uses_shared_history_savepoint_port() -> None:
    drag = CHEMVAS_ROOT / "ui" / "selection_drag_tool.py"
    source = drag.read_text(encoding="utf-8")

    assert "chemvas.ui.transactions.document import" in source
    assert "DocumentSavepoint.capture(" in source


def test_core_history_has_no_ui_or_concrete_runtime_dependencies() -> None:
    """The bound operation contracts apply to lazy and type-only imports too."""
    forbidden = (
        "chemvas.ui",
        "chemvas.bootstrap",
        "chemvas.adapters",
        "PyQt6",
        "rdkit",
    )
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if edge.source == "chemvas.core.history"
        and any(
            edge.dependency == prefix or edge.dependency.startswith(prefix + ".")
            for prefix in forbidden
        )
    ]
    assert violations == []


def test_domain_and_core_do_not_depend_on_concrete_adapters() -> None:
    """Qt editor code may use adapters; document and core code stay independent."""
    violations = [
        _formatted(edge)
        for edge in _import_edges()
        if (
            edge.dependency == "chemvas.adapters"
            or edge.dependency.startswith("chemvas.adapters.")
        )
        and (
            edge.source in {"chemvas.domain", "chemvas.core"}
            or edge.source.startswith(("chemvas.domain.", "chemvas.core."))
        )
    ]

    assert violations == []


@pytest.mark.parametrize(
    "source",
    [
        "chemvas.ui.new_controller",
        "chemvas.shell.new_panel",
        "chemvas.features.new_feature.qt",
        "chemvas.adapters.qt.new_renderer",
        "chemvas.bootstrap.new_composition",
    ],
)
def test_desktop_dependencies_need_no_wrapper_or_migration_entry(monkeypatch, source):
    path = CHEMVAS_ROOT / "injected.py"
    edges = (
        ImportEdge(source, "PyQt6.QtWidgets", path, 1),
        ImportEdge(source, "chemvas.adapters.qt.renderer", path, 2),
    )
    if source.startswith("chemvas.bootstrap."):
        edges += (ImportEdge(source, "chemvas.ui.canvas_view", path, 3),)
    monkeypatch.setattr(sys.modules[__name__], "_import_edges", lambda: edges)

    test_target_layer_dependency_direction()
    test_non_bootstrap_layers_do_not_depend_on_legacy_core_or_ui()
    test_domain_has_no_framework_or_adapter_dependencies()
    test_domain_and_core_do_not_depend_on_concrete_adapters()


@pytest.mark.parametrize(
    ("source", "dependency", "guard"),
    [
        (
            "chemvas.domain.document",
            "PyQt6.QtCore",
            test_domain_has_no_framework_or_adapter_dependencies,
        ),
        (
            "chemvas.domain.document",
            "rdkit.Chem",
            test_domain_has_no_framework_or_adapter_dependencies,
        ),
        (
            "chemvas.domain.document",
            "chemvas.features.selection",
            test_target_layer_dependency_direction,
        ),
        (
            "chemvas.domain.document",
            "chemvas.ui.canvas_view",
            test_non_bootstrap_layers_do_not_depend_on_legacy_core_or_ui,
        ),
        (
            "chemvas.core.history",
            "chemvas.adapters.qt.renderer",
            test_domain_and_core_do_not_depend_on_concrete_adapters,
        ),
        (
            "chemvas.core.history",
            "chemvas.adapters",
            test_domain_and_core_do_not_depend_on_concrete_adapters,
        ),
        (
            "chemvas.core",
            "chemvas.adapters.qt.renderer",
            test_domain_and_core_do_not_depend_on_concrete_adapters,
        ),
        (
            "chemvas.domain",
            "chemvas.adapters",
            test_domain_and_core_do_not_depend_on_concrete_adapters,
        ),
        (
            "chemvas.features.selection",
            "chemvas.shell.main_window",
            test_target_layer_dependency_direction,
        ),
        (
            "chemvas.features.selection",
            "chemvas.ui.canvas_view",
            test_non_bootstrap_layers_do_not_depend_on_legacy_core_or_ui,
        ),
        (
            "chemvas.features.selection",
            "chemvas.bootstrap.application",
            test_target_layer_dependency_direction,
        ),
        (
            "chemvas.adapters.qt.renderer",
            "chemvas.ui.canvas_view",
            test_non_bootstrap_layers_do_not_depend_on_legacy_core_or_ui,
        ),
        (
            "chemvas.adapters.qt.renderer",
            "chemvas.bootstrap.application",
            test_target_layer_dependency_direction,
        ),
        (
            "chemvas.shell.main_window",
            "chemvas.bootstrap.application",
            test_target_layer_dependency_direction,
        ),
    ],
)
def test_relaxed_editor_rules_still_reject_boundary_violations(
    monkeypatch, source, dependency, guard
):
    edge = ImportEdge(source, dependency, CHEMVAS_ROOT / "injected.py", 1)
    monkeypatch.setattr(sys.modules[__name__], "_import_edges", lambda: (edge,))

    with pytest.raises(AssertionError):
        guard()


def test_feature_callers_use_package_public_api() -> None:
    violations = [
        _formatted(edge) for edge in _feature_public_api_violations(_import_edges())
    ]

    assert violations == []


def test_feature_public_api_guard_rejects_internal_module_imports() -> None:
    path = CHEMVAS_ROOT / "adapters" / "qt" / "renderer.py"
    public_import = ImportEdge(
        source="chemvas.adapters.qt.renderer",
        dependency="chemvas.features.rendering",
        path=path,
        line=8,
    )
    private_import = ImportEdge(
        source="chemvas.adapters.qt.renderer",
        dependency="chemvas.features.rendering.acs1996_style",
        path=path,
        line=8,
    )
    same_feature_import = ImportEdge(
        source="chemvas.features.rendering.bond_geometry",
        dependency="chemvas.features.rendering.bond_style",
        path=CHEMVAS_ROOT / "features" / "rendering" / "bond_geometry.py",
        line=10,
    )

    assert _feature_public_api_violations(
        (public_import, private_import, same_feature_import)
    ) == (private_import,)
