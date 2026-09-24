from __future__ import annotations

"""Architecture boundary rules.

Checks protect ownership, dependency direction, and recovery contracts.
Services may use public Qt APIs and their owned state directly; accessor and
port modules are optional. Do not freeze helper inventories, layer counts, or
particular call spellings. A pattern ban needs a contract behind it just as a
positive assertion does. Update a structural check when its responsibility
moves, retaining behavioral coverage of the contract (ADR 0005).
"""

import ast
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


@lru_cache(maxsize=1024)
def _parse_source(source: str) -> ast.Module:
    # Shared trees are read-only. Mutation controls supply changed source text,
    # which gets a different entry even when its path and metadata are unchanged.
    return ast.parse(source)


def test_source_parsing_observes_same_length_file_edits(tmp_path):
    path = tmp_path / "source.py"
    original = "value = 1\n"
    path.write_text(original, encoding="utf-8")
    first = _parse_source(path.read_text(encoding="utf-8"))

    # Read content afresh: timestamps can coincide for fast same-length edits.
    updated = "value = 2\n"
    path.write_text(updated, encoding="utf-8")
    second = _parse_source(path.read_text(encoding="utf-8"))
    assert isinstance(first.body[0], ast.Assign)
    assert isinstance(second.body[0], ast.Assign)
    assert ast.literal_eval(first.body[0].value) == 1
    assert ast.literal_eval(second.body[0].value) == 2
    path.unlink()
    with pytest.raises(FileNotFoundError):
        _parse_source(path.read_text(encoding="utf-8"))


def test_source_parsing_reuses_only_identical_text():
    _parse_source.cache_clear()
    source = "value = 1\n"
    first = _parse_source(source)
    assert _parse_source(source) is first
    assert _parse_source("value = 2\n") is not first
    assert _parse_source.cache_info().misses == 2
    assert _parse_source.cache_info().hits == 1
    with pytest.raises(SyntaxError):
        _parse_source("def broken(")


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
    "active_line_kind",
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


def _app_python_files() -> list[Path]:
    return sorted(APP_ROOT.rglob("*.py"))


def _ui_path(filename: str) -> Path:
    """Locate one editor module by file name inside the ``chemvas.ui`` subpackages."""
    matches = sorted((APP_ROOT / "chemvas" / "ui").rglob(filename))
    assert len(matches) == 1, (filename, matches)
    return matches[0]


def _matching_lines(pattern: re.Pattern[str], paths: list[Path]) -> list[str]:
    matches: list[str] = []
    for path in paths:
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                matches.append(
                    f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}: {line.strip()}"
                )
    return matches


def test_production_code_does_not_reach_into_canvas_private_members() -> None:
    pattern = re.compile(
        r"\b(?:canvas|self\.canvas)\._"
        r"|vars\(\s*canvas\s*\)\[\s*\"_[A-Za-z]"
        r"|getattr\(\s*canvas\s*,\s*\"_[A-Za-z]"
        r"|setattr\(\s*canvas\s*,\s*\"_[A-Za-z]"
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_removed_canvas_state_aliases_do_not_return() -> None:
    """Direct access to owned state does not restore the old canvas mirrors."""
    property_names = "|".join(re.escape(name) for name in CANVAS_STATE_PROPERTIES)
    pattern = re.compile(rf"\b(?:canvas|self\.canvas)\.(?:{property_names})\b")

    assert _matching_lines(pattern, _app_python_files()) == []


@pytest.mark.parametrize(
    "source",
    [
        "def update(canvas): return canvas.scene()",
        "def update(canvas): return canvas.runtime_state.graph_state",
        "def update(canvas): return canvas.services.move_controller",
        "def __init__(self, move_controller): self._move_controller = move_controller",
    ],
)
def test_public_editor_access_needs_no_forwarding_layer(monkeypatch, tmp_path, source):
    path = tmp_path / "controller.py"
    path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(__name__ + ".APP_ROOT", tmp_path / "app")
    monkeypatch.setattr(__name__ + "._app_python_files", lambda: [path])

    test_production_code_does_not_reach_into_canvas_private_members()
    test_removed_canvas_state_aliases_do_not_return()


@pytest.mark.parametrize(
    ("source", "guard"),
    [
        (
            "def update(canvas): return canvas._graph_state",
            test_production_code_does_not_reach_into_canvas_private_members,
        ),
        (
            'def update(canvas): return getattr(canvas, "_graph_state")',
            test_production_code_does_not_reach_into_canvas_private_members,
        ),
        (
            "def update(canvas): return canvas.atom_items",
            test_removed_canvas_state_aliases_do_not_return,
        ),
    ],
)
def test_direct_access_keeps_private_and_state_alias_guards(
    monkeypatch, tmp_path, source, guard
):
    path = tmp_path / "controller.py"
    path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(__name__ + ".APP_ROOT", tmp_path / "app")
    monkeypatch.setattr(__name__ + "._app_python_files", lambda: [path])

    with pytest.raises(AssertionError):
        guard()


def test_main_window_code_binds_preview_rdkit_through_preview_api() -> None:
    paths = sorted((APP_ROOT / "chemvas" / "ui" / "window").glob("main_window*.py"))
    pattern = re.compile(r"\bpreview_3d\._rdkit\b")

    assert _matching_lines(pattern, paths) == []


def test_production_code_does_not_cache_contexts_as_private_fields() -> None:
    pattern = re.compile(
        r"\bvars\([^)]*\)\.get\(\s*\"_[A-Za-z0-9_]+_context\""
        r"|\bvars\([^)]*\)\[\s*\"_[A-Za-z0-9_]+_context\"\s*\]"
        r"|\"_[A-Za-z0-9_]+_context\"\s*\]\s*="
    )

    assert _matching_lines(pattern, _app_python_files()) == []


def test_ts_bracket_values_are_read_and_drawn_through_records() -> None:
    painters = sorted(
        path.relative_to(APP_ROOT.parents[0]).as_posix()
        for path in _app_python_files()
        if re.search(
            r"\bcontext\.decorations\.ts_bracket_path\(",
            path.read_text(encoding="utf-8"),
        )
        and path.name != "scene_decoration_build_access.py"
    )
    assert painters == ["app/chemvas/ui/annotations/records.py"]
    removed = re.compile(
        r"\bts_bracket_state_dict\b|\badopt_ts_bracket_item_for\b|\bTsBracketPathBuilder\b"
    )
    assert _matching_lines(removed, _app_python_files()) == []


def test_shape_values_live_in_records_not_on_graphics_items() -> None:
    """A shape item is drawn from its record and is never asked what it is.

    Two modules paint a shape: ``annotations.graphics`` creates the item
    and ``annotations.records`` redraws it from its record. Nothing else may
    build a shape outline, and the item-side reader and the adoption that
    derived a record from paint are gone for good.
    """
    painters = sorted(
        path.relative_to(APP_ROOT.parents[0]).as_posix()
        for path in _app_python_files()
        if re.search(r"\bshape_path\(", path.read_text(encoding="utf-8"))
        and path.name != "shape_geometry.py"
    )
    assert painters == [
        "app/chemvas/ui/annotations/graphics.py",
        "app/chemvas/ui/annotations/records.py",
    ]
    removed = re.compile(
        r"\bshape_state_dict\b(?!_for)|\badopt_shape_item_for\b|\bsync_shape_record_for\b"
    )
    assert _matching_lines(removed, _app_python_files()) == []


def test_note_committed_text_private_state_stays_inside_note_item() -> None:
    allowed_paths = {APP_ROOT / "chemvas" / "ui" / "annotations/items.py"}
    paths = [path for path in _app_python_files() if path not in allowed_paths]
    forbidden = re.compile(r"\._last_text\b")

    assert _matching_lines(forbidden, paths) == []


# Each row is one removed per-service context facade: the context module that
# must stay deleted (None where an earlier row already covers it), the modules
# that must not name it, and every pattern that row bans. Rows carry their own
# patterns rather than deriving them from the module name -- the class names
# are not mechanically derivable (canvas_chemdraw_shortcut_context.py ->
# CanvasChemDrawShortcutContext) and several rows ban extra service-lookup
# spellings that only apply to that one module.
def test_core_history_does_not_fall_back_to_self_releasing_snapshots() -> None:
    module = APP_ROOT / "chemvas" / "core" / "history.py"
    forbidden = re.compile(
        r"\bsnapshot\.release\b"
        r"|\bgetattr\(\s*snapshot\s*,\s*[\"']release[\"']"
    )

    assert _matching_lines(forbidden, [module]) == []


def test_document_session_history_rollback_does_not_rebind_stacks() -> None:
    module = (
        APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_document_session_service.py"
    )
    forbidden = re.compile(r"\bsnapshot\.state\.(?:history|redo_stack)\s*=")

    assert _matching_lines(forbidden, [module]) == []


def test_document_session_does_not_snapshot_legacy_sheet_fields() -> None:
    module = (
        APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_document_session_service.py"
    )
    tree = _parse_source(module.read_text(encoding="utf-8"))
    forbidden = {"sheet_size", "sheet_orientation"}
    constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert constants.isdisjoint(forbidden)


def test_sheet_setup_values_exist_only_in_the_runtime_state() -> None:
    forbidden_names = {"sheet_size", "sheet_orientation"}
    violations: list[str] = []

    for path in _app_python_files():
        tree = _parse_source(path.read_text(encoding="utf-8"))
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


def test_clipboard_copy_uses_canonical_export_scope_without_parallel_visibility_owner():
    tree = _parse_source(
        _ui_path("scene_clipboard_copy_service.py").read_text(encoding="utf-8")
    )
    scope_names = {
        alias.asname or alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "chemvas.features.export"
        for alias in node.names
        if alias.name == "exported_scene"
    }
    assert any(
        isinstance(item.context_expr, ast.Call)
        and isinstance(item.context_expr.func, ast.Name)
        and item.context_expr.func.id in scope_names
        for function in tree.body
        if isinstance(function, ast.FunctionDef)
        and function.name == "copy_selection_to_clipboard_for_canvas"
        for node in ast.walk(function)
        if isinstance(node, ast.With)
        for item in node.items
    )
    for filename, helper in (
        ("scene_clipboard_access.py", "visible_canvas_items_to_hide_for_copy"),
        ("scene_clipboard_transaction_logic.py", "visible_items_to_hide_for_copy"),
    ):
        assert helper not in _ui_path(filename).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("variant", "allowed"),
    [
        ("parenthesized", True),
        ("import_alias", True),
        ("wrong_import", False),
        ("missing_scope", False),
        ("unscoped_call", False),
    ],
)
def test_clipboard_export_scope_guard_checks_structure(monkeypatch, variant, allowed):
    service = APP_ROOT / "chemvas" / "ui" / "scene" / "scene_clipboard_copy_service.py"
    source = (
        "from chemvas.features.export import exported_scene\n\n"
        "def copy_selection_to_clipboard_for_canvas(canvas, items):\n"
        "    with exported_scene(canvas_scene_for(canvas), items):\n"
        "        build_clipboard_mime_data(canvas)\n"
    )
    scope = "with exported_scene(canvas_scene_for(canvas), items):"
    assert scope in source
    if variant == "parenthesized":
        changed = source.replace(
            scope, "with (exported_scene(canvas_scene_for(canvas), items)):"
        )
        assert ast.dump(_parse_source(changed)) == ast.dump(_parse_source(source))
    elif variant == "import_alias":
        changed = source.replace(
            "from chemvas.features.export import exported_scene",
            "from chemvas.features.export import exported_scene as export_scope",
        ).replace("with exported_scene(", "with export_scope(")
    elif variant == "wrong_import":
        changed = source.replace(
            "from chemvas.features.export import exported_scene",
            "from contextlib import nullcontext as exported_scene",
        )
    elif variant == "missing_scope":
        changed = source.replace(scope, "with nullcontext():")
    else:
        changed = source.replace(
            scope,
            "exported_scene(canvas_scene_for(canvas), items)\n    with nullcontext():",
        )
    assert changed != source
    read_text = Path.read_text

    def read_source(path, *args, **kwargs):
        return changed if path == service else read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_source)
    if allowed:
        test_clipboard_copy_uses_canonical_export_scope_without_parallel_visibility_owner()
    else:
        with pytest.raises(AssertionError):
            test_clipboard_copy_uses_canonical_export_scope_without_parallel_visibility_owner()


def test_alias_attachment_derivation_has_one_domain_owner() -> None:
    owner = APP_ROOT / "chemvas" / "domain" / "atom_aliases.py"
    consumers = [path for path in _app_python_files() if path != owner]

    assert _matching_lines(re.compile(r"\bAliasAttachment\("), consumers) == []
    assert _matching_lines(re.compile(r"\b_alias_attachments\b"), consumers) == []


def test_canvas_runtime_state_attach_does_not_mirror_runtime_services_to_canvas() -> (
    None
):
    runtime_state = APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_runtime_state.py"
    pattern = re.compile(r"\bcanvas\.history_service\s*=")

    assert _matching_lines(pattern, [runtime_state]) == []


def _runtime_state_fields(node: ast.AST) -> set[str]:
    return {
        child.attr
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute)
        and isinstance(child.ctx, ast.Load)
        and isinstance(child.value, ast.Attribute)
        and child.value.attr == "runtime_state"
        and isinstance(child.value.value, ast.Name)
        and child.value.value.id == "canvas"
    }


def _has_state_fallback(node: ast.AST, *, legacy_field: str | None = None) -> bool:
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Attribute)
            and child.attr == legacy_field
            and isinstance(child.value, ast.Name)
            and child.value.id == "canvas"
        ):
            return True
        if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Name):
            continue
        if child.func.id == "ensure_canvas_state":
            return True
        if (
            child.func.id in {"getattr", "setattr"}
            and child.args
            and isinstance(child.args[0], ast.Name)
            and child.args[0].id == "canvas"
        ):
            return True
    return False


def test_graph_algorithms_are_canvas_free() -> None:
    graph_modules = [
        APP_ROOT / "chemvas" / "features" / "graph" / "__init__.py",
        APP_ROOT / "chemvas" / "features" / "graph" / "algorithms.py",
    ]
    pattern = re.compile(r"\bcanvas\b|\bfrom ui\.|\bimport ui\.")

    assert _matching_lines(pattern, graph_modules) == []


def test_production_window_helpers_do_not_reach_into_window_private_members() -> None:
    allowed_paths = {
        APP_ROOT / "chemvas" / "ui" / "window" / "main_window_ports.py",
    }
    main_window_files = sorted(
        path
        for path in _app_python_files()
        if path.parent == APP_ROOT / "chemvas" / "ui" / "window"
        and path.name.startswith("main_window")
        if path not in allowed_paths
    )
    assert main_window_files, "No main-window helpers found in the source inventory"
    pattern = re.compile(
        r"\b(?:window|self\.window)\._"
        r"|vars\(\s*window\s*\)\[\s*\"_[A-Za-z]"
        r"|getattr\(\s*window\s*,\s*\"_[A-Za-z]"
        r"|setattr\(\s*window\s*,\s*\"_[A-Za-z]"
    )

    assert _matching_lines(pattern, main_window_files) == []


def test_window_private_guard_rejects_empty_inventory(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(globals(), "APP_ROOT", tmp_path)
    with pytest.raises(AssertionError):
        test_production_window_helpers_do_not_reach_into_window_private_members()


def test_window_private_guard_allows_canonical_ports(monkeypatch, tmp_path) -> None:
    helpers = tmp_path / "chemvas" / "ui" / "window"
    helpers.mkdir(parents=True)
    (helpers / "main_window_example_service.py").write_text(
        "def probe(window):\n    return window.public_value\n", encoding="utf-8"
    )
    (helpers / "main_window_ports.py").write_text(
        "def probe(window):\n    return window._private_value\n", encoding="utf-8"
    )
    monkeypatch.setitem(globals(), "APP_ROOT", tmp_path)
    test_production_window_helpers_do_not_reach_into_window_private_members()


@pytest.mark.parametrize(
    "access",
    [
        "window._service",
        "self.window._service",
        'vars(window)["_service"]',
        'getattr(window, "_service")',
        'setattr(window, "_service", None)',
    ],
)
def test_window_private_guard_rejects_current_layout_violation(
    monkeypatch, tmp_path, access
) -> None:
    root = tmp_path / "app"
    helpers = root / "chemvas" / "ui"
    helpers.mkdir(parents=True)
    (helpers / "main_window_example_service.py").write_text(
        f"def probe(window):\n    return {access}\n", encoding="utf-8"
    )
    monkeypatch.setitem(globals(), "APP_ROOT", root)
    with pytest.raises(AssertionError):
        test_production_window_helpers_do_not_reach_into_window_private_members()


@pytest.mark.parametrize(
    "left,right",
    [
        ("from example import right", "from example import left"),
        ("from . import right", "from . import left"),
        ("from . import right as peer", "from . import left as peer"),
        ("import example.right", "import example.left"),
    ],
)
def test_eager_import_guard_rejects_module_cycles(monkeypatch, tmp_path, left, right):
    package = tmp_path / "example"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "left.py").write_text(left, encoding="utf-8")
    (package / "right.py").write_text(right, encoding="utf-8")
    monkeypatch.setitem(globals(), "APP_ROOT", tmp_path)
    with pytest.raises(AssertionError):
        test_eager_production_import_graph_stays_acyclic()


@pytest.mark.parametrize("eager_only", [False, True])
def test_import_graph_rejects_empty_inventory(monkeypatch, tmp_path, eager_only):
    monkeypatch.setitem(globals(), "APP_ROOT", tmp_path)
    with pytest.raises(AssertionError, match="No Python modules"):
        _static_app_import_graph(eager_only=eager_only)


@pytest.mark.parametrize(
    "source,eager,runtime",
    [
        ("from example import right", True, True),
        ("from . import right as peer", True, True),
        ("from example.right import READY", True, True),
        ("def lazy():\n    from example import right", False, True),
        ("async def lazy():\n    from example import right", False, True),
        ("if TYPE_CHECKING:\n    from example import right", False, False),
        ("if typing.TYPE_CHECKING:\n    from example import right", False, False),
        (
            "def lazy():\n    if TYPE_CHECKING:\n        from example import right",
            False,
            False,
        ),
        (
            "if TYPE_CHECKING:\n    pass\nelse:\n    from example import right",
            True,
            True,
        ),
        ("class Widget:\n    from example import right", True, True),
        (
            "try:\n    pass\nexcept RuntimeError:\n    from example import right",
            True,
            True,
        ),
        ("match value:\n    case 1:\n        from example import right", True, True),
    ],
)
def test_import_graph_preserves_lazy_and_type_only_boundaries(
    monkeypatch, tmp_path, source, eager, runtime
):
    package = tmp_path / "example"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "left.py").write_text(source, encoding="utf-8")
    (package / "right.py").write_text("READY = True", encoding="utf-8")
    monkeypatch.setitem(globals(), "APP_ROOT", tmp_path)
    assert "example.right" in _static_app_import_graph()["example.left"]
    assert (
        "example.right" in _static_app_import_graph(eager_only=True)["example.left"]
    ) is eager
    assert (
        "example.right" in _static_app_import_graph(runtime_only=True)["example.left"]
    ) is runtime
    assert all(
        dependency in {"example", "example.right"}
        for dependency in _static_app_import_graph()["example.left"]
    )


# --- Dependency contracts ------------------------------------------------


def _eager_imports(
    node: ast.AST, *, enter_functions: bool = False
) -> Iterator[ast.Import | ast.ImportFrom]:
    """Visit import-time statements, including class/exception/match bodies.

    ``enter_functions`` also visits function bodies, which turns the walk into
    every import that can execute: eager and lazy, never ``TYPE_CHECKING``.
    """
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        yield node
        return
    if (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not enter_functions
    ):
        return
    if isinstance(node, ast.If) and (
        (isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING")
        or (
            isinstance(node.test, ast.Attribute)
            and isinstance(node.test.value, ast.Name)
            and node.test.value.id == "typing"
            and node.test.attr == "TYPE_CHECKING"
        )
    ):
        for statement in node.orelse:
            yield from _eager_imports(statement, enter_functions=enter_functions)
        return
    for child in ast.iter_child_nodes(node):
        yield from _eager_imports(child, enter_functions=enter_functions)


def _static_app_import_graph(
    *, eager_only: bool = False, runtime_only: bool = False
) -> dict[str, set[str]]:
    """Share module discovery and resolution across the import contracts.

    The default graph has every import statement. ``eager_only`` keeps what runs
    at import time; ``runtime_only`` adds lazy function-level imports to that
    and still leaves ``TYPE_CHECKING`` blocks out, because an annotation-only
    edge cannot make two modules wait on each other.
    """
    assert not (eager_only and runtime_only)
    module_paths: dict[str, Path] = {}
    for path in _app_python_files():
        relative = path.relative_to(APP_ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        module_paths[".".join(parts)] = path

    graph = {module: set() for module in module_paths}
    assert graph, "No Python modules found in the source inventory"
    for module, path in module_paths.items():
        tree = _parse_source(path.read_text(encoding="utf-8"))
        if eager_only:
            nodes: Iterable[ast.AST] = _eager_imports(tree)
        elif runtime_only:
            nodes = _eager_imports(tree, enter_functions=True)
        else:
            nodes = ast.walk(tree)
        for node in nodes:
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
    graph = _static_app_import_graph(runtime_only=True)
    protected_modules = {
        "chemvas.core.history",
        "chemvas.domain.transactions.outcome",
        "chemvas.domain.transactions.recovery",
        "chemvas.ui.canvas.canvas_history_service",
        "chemvas.ui.transactions.document",
        "chemvas.ui.transactions.object_graph_snapshot",
        "chemvas.ui.transactions.scene_rect",
        "chemvas.ui.transactions.scene_runtime",
        "chemvas.ui.history.history_atom_position_restore",
        "chemvas.ui.history.history_operations",
        "chemvas.ui.history.history_commands",
    }
    # The concrete history_operations adapter is assembled lazily by runtime
    # creation and refers to typed canvas services. The global eager-DAG guard
    # covers it; the policy/command/savepoint cluster here also forbids lazy
    # cycles. Annotation-only edges are not counted: they never execute, and
    # counting them is what forced CanvasRuntimeServices to declare its bundles
    # as Any. The price is written down here: the TYPE_CHECKING block in
    # canvas_runtime_services is the one separator between the protected
    # modules and the service bundles that import them eagerly. Moving any of
    # those imports out of the block, to module level or into a function,
    # closes a real cycle, and this test and the eager-DAG test both fail on
    # it. Core history additionally cannot import the UI, type-only or not
    # (tests/test_package_dependencies.py).
    assert protected_modules <= set(graph)
    cyclic_components = [
        sorted(component)
        for component in _strongly_connected_components(graph)
        if len(component) > 1 and component & protected_modules
    ]

    assert cyclic_components == []


def test_eager_production_import_graph_stays_acyclic() -> None:
    graph = _static_app_import_graph(eager_only=True)
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
            "chemvas.ui.canvas.canvas_history_service",
            "chemvas.ui.history.history_commands",
        }
        & graph["chemvas.ui.transactions.document"]
    )


def test_history_stack_snapshot_has_one_production_owner() -> None:
    owners = []
    for path in _app_python_files():
        tree = _parse_source(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            fields = {
                child.target.id
                for child in node.body
                if isinstance(child, ast.AnnAssign)
                and isinstance(child.target, ast.Name)
            }
            if {"state", "history", "redo_stack"} <= fields:
                owners.append(path)

    assert owners == [
        APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_history_service.py"
    ]


def test_document_lifecycle_does_not_reach_into_history_stacks() -> None:
    """Document replacement/reset use stack policy, not the mutable stack fields."""
    violations = []
    for name in ("canvas_document_session_service", "canvas_scene_reset_service"):
        path = _ui_path(f"{name}.py")
        tree = _parse_source(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                attribute, receiver = node.attr, node.value
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "setattr", "delattr", "hasattr"}
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
            ):
                attribute, receiver = node.args[1].value, node.args[0]
            else:
                continue
            if attribute not in {"history", "redo_stack"}:
                continue
            # The session's injected history service is not a stack field.
            if (
                attribute == "history"
                and isinstance(receiver, ast.Name)
                and receiver.id == "self"
            ):
                continue
            violations.append(f"{path.name}:{node.lineno}: {ast.unparse(node)}")

    assert violations == []


def test_rollback_kernel_has_no_restore_retry_or_qt_base_port_bypass() -> None:
    kernel_files = [
        APP_ROOT / "chemvas" / "core" / "history.py",
        APP_ROOT / "chemvas" / "domain" / "transactions" / "recovery.py",
        APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_history_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_history_recording_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_color_mutation_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_document_session_service.py",
        APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_scene_reset_service.py",
        APP_ROOT / "chemvas" / "ui" / "history" / "history_commands.py",
        APP_ROOT / "chemvas" / "ui" / "history" / "history_operations.py",
        APP_ROOT / "chemvas" / "ui" / "insert" / "insert_controller.py",
        APP_ROOT / "chemvas" / "ui" / "canvas" / "sheet_setup_access.py",
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


def test_core_does_not_import_ui_statically() -> None:
    """core stays importable without Qt: any ui dependency must be lazy."""
    violations: list[str] = []
    for path in sorted((APP_ROOT / "chemvas" / "core").rglob("*.py")):
        tree = _parse_source(path.read_text(encoding="utf-8"))
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


def test_core_history_does_not_resolve_runtime_implementations() -> None:
    """History receives operations; even a lazy implementation lookup is wrong."""
    path = APP_ROOT / "chemvas" / "core" / "history.py"
    tree = _parse_source(path.read_text(encoding="utf-8"))
    aliases = _imported_name_aliases(tree)
    called = {aliases.get(name, name) for name in _called_function_names(tree)}
    assert not {"import_module", "__import__"} & called


def _history_receiver_violations(source: str) -> list[tuple[int, str]]:
    """Commands may call an operation, not inspect/store its backing canvas."""
    violations = []
    state_fields = {"canvas", "model", "runtime_state", "services"}
    for function in ast.walk(_parse_source(source)):
        if not isinstance(function, ast.FunctionDef):
            continue
        args = function.args.posonlyargs + function.args.args
        if len(args) < 2 or args[0].arg != "self":
            continue
        if function.name not in {"undo", "redo", "_apply", "_compensate"}:
            continue
        receiver = args[1].arg
        if receiver == "canvas":
            violations.append((function.lineno, "canvas receiver"))
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == receiver
                and node.attr in state_fields
            ):
                violations.append((node.lineno, "receiver state access"))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "setattr", "delattr", "hasattr"}
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == receiver
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in state_fields
            ):
                violations.append((node.lineno, "receiver state lookup"))
            if (
                isinstance(node, (ast.Assign, ast.AnnAssign))
                and isinstance(node.value, ast.Name)
                and node.value.id == receiver
            ):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                if any(isinstance(target, ast.Attribute) for target in targets):
                    violations.append((node.lineno, "stored receiver"))
    return violations


@pytest.mark.parametrize(
    "module", ["core/history.py", "ui/history/history_commands.py"]
)
def test_history_commands_do_not_receive_or_retain_canvas(module) -> None:
    source = (APP_ROOT / "chemvas" / module).read_text(encoding="utf-8")
    assert _history_receiver_violations(source) == []


@pytest.mark.parametrize(
    "method",
    [
        "def undo(self, canvas): pass",
        "def redo(self, target): target.model.next_atom_id = 4",
        "def _apply(self, target): getattr(target, 'runtime_state')",
        "def redo(self, target): self.saved_receiver = target",
    ],
)
def test_history_receiver_guard_rejects_canvas_coupling(method):
    assert _history_receiver_violations("class Command:\n    " + method)
    assert (
        _history_receiver_violations(
            "class Command:\n    def redo(self, target): target.remove_atom_for_history(4)"
        )
        == []
    )


def _history_proxy_violations(source: str) -> list[tuple[int, str]]:
    """The UI adapter names operations instead of exposing a general canvas proxy."""
    violations = []
    for node in ast.walk(_parse_source(source)):
        if isinstance(node, ast.FunctionDef) and node.name in {
            "__getattr__",
            "__getattribute__",
        }:
            violations.append((node.lineno, "generic attribute proxy"))
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Attribute):
            if node.value.attr.lstrip("_") == "canvas":
                violations.append((node.lineno, "exposed canvas"))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "setattr", "delattr"}
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Attribute)
            and node.args[0].attr.lstrip("_") == "canvas"
            and not isinstance(node.args[1], ast.Constant)
        ):
            violations.append((node.lineno, "dynamic canvas operation"))
        if isinstance(node, ast.Attribute) and node.attr == "canvas":
            violations.append((node.lineno, "public canvas field"))
    return violations


def test_history_operations_do_not_expose_a_generic_canvas_proxy() -> None:
    path = APP_ROOT / "chemvas" / "ui" / "history" / "history_operations.py"
    assert _history_proxy_violations(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "method",
    [
        "def __getattr__(self, name): return getattr(self.__canvas, name)",
        "def canvas_for_command(self): return self.__canvas",
        "def invoke(self, name): return getattr(self.__canvas, name)()",
        "def __init__(self, canvas): self.canvas = canvas",
    ],
)
def test_history_proxy_guard_rejects_unbound_canvas_access(method):
    assert _history_proxy_violations("class Operations:\n    " + method)
    assert (
        _history_proxy_violations(
            "class Operations:\n    def remove_atom_for_history(self, atom_id): "
            "remove_atom(self.__canvas, atom_id)"
        )
        == []
    )


def test_core_has_no_direct_qt_dependencies() -> None:
    qt_modules: set[str] = set()
    for path in sorted((APP_ROOT / "chemvas" / "core").rglob("*.py")):
        tree = _parse_source(path.read_text(encoding="utf-8"))
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


SCENE_DRAWING_MODULES = (
    "atom_label_renderer.py",
    "bond_renderer.py",
    "bond_geometry_plan_service.py",
    "bond_geometry_update_service.py",
    "bond_graphics_build_service.py",
    "bond_graphics_draw_service.py",
    "bond_line_geometry_service.py",
    "bond_ring_double_geometry_service.py",
    "annotations/arrows.py",
    "annotations/graphics.py",
    "scene_geometry.py",
    "molecule_scene_renderer.py",
    "document_scene.py",
    "figure_export_service.py",
    "export_readability_service.py",
)


def _drawing_editor_dependencies(source: str) -> list[str]:
    violations = []
    forbidden = {
        "canvas_view",
        "canvas_runtime_services",
        "canvas_services",
        "canvas_history_service",
        "canvas_view_ports",
    }
    for node in ast.walk(_parse_source(source)):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").rsplit(".", 1)[-1] in forbidden:
                violations.append(node.module)
        elif isinstance(node, ast.Import):
            violations.extend(
                alias.name
                for alias in node.names
                if alias.name.rsplit(".", 1)[-1] in forbidden
            )
        elif isinstance(node, ast.Attribute) and node.attr in {
            "canvas",
            "services",
            "history",
            "viewport",
            "runtime_state",
        }:
            violations.append(node.attr)
    return violations


def test_scene_drawing_uses_a_typed_context_without_editor_resolution() -> None:
    for filename in SCENE_DRAWING_MODULES:
        source = _ui_path(filename).read_text(encoding="utf-8")
        assert _drawing_editor_dependencies(source) == [], filename
        arguments = [
            node
            for node in ast.walk(_parse_source(source))
            if isinstance(node, ast.arg) and node.arg == "context"
        ]
        assert arguments, filename
        assert all(
            node.annotation is not None
            and ast.unparse(node.annotation) == "SceneRenderContext"
            for node in arguments
        ), filename


def test_scene_composition_does_not_construct_or_resolve_an_editor() -> None:
    for filename in ("scene_rendering.py", "smiles_preview_picture.py"):
        source = _ui_path(filename).read_text(encoding="utf-8")
        assert _drawing_editor_dependencies(source) == [], filename


@pytest.mark.parametrize(
    "source",
    [
        "from chemvas.ui.canvas.canvas_services import build_canvas_services",
        "import chemvas.ui.canvas.canvas_view as editor",
        "def draw(context): return context.services",
        "def draw(context): return context.canvas",
    ],
)
def test_scene_drawing_guard_rejects_editor_dependencies(source: str) -> None:
    assert _drawing_editor_dependencies(source)
    assert (
        _drawing_editor_dependencies(
            "def draw(context: SceneRenderContext): return context.scene"
        )
        == []
    )


def _canvas_runtime_state_field_names() -> set[str]:
    fields: set[str] = set()
    for filename, class_name in (
        ("scene_render_context.py", "SceneRenderState"),
        ("canvas_runtime_state.py", "CanvasRuntimeState"),
    ):
        tree = _parse_source(_ui_path(filename).read_text(encoding="utf-8"))
        node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        if class_name == "CanvasRuntimeState":
            assert [ast.unparse(base) for base in node.bases] == ["SceneRenderState"]
        own_fields = {
            stmt.target.id
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
        }
        assert not fields & own_fields, (
            "Drawing state must not be mirrored by the editor"
        )
        fields.update(own_fields)
    return fields


# Functions whose name looks like a state accessor but which are not one, with
# the reason each is exempt from reading CanvasRuntimeState.
NON_RUNTIME_STATE_ACCESSORS = {
    # Setter, not an accessor.
    "canvas/sheet_setup_state.py:set_sheet_setup_state_for",
    # Serializes one scene item's state, not canvas state.
    "annotations/state.py:scene_item_state_for",
}


def test_state_accessors_read_the_runtime_container_directly() -> None:
    """Every canvas state accessor resolves its field on CanvasRuntimeState.

    Attaching state to the canvas instead splits it in two: the container keeps
    the real one while the accessor hands out a shadow copy. Reading the field
    off the slotted container makes a renamed or misspelled field raise.

    Check the remaining state lookups without requiring a particular helper
    inventory. Removing a lookup in favor of an injected state owner is allowed;
    a retained lookup must not manufacture a shadow state.
    """
    field_names = _canvas_runtime_state_field_names()
    accessor_name = re.compile(r"_(?:state|registry)_for$")
    checked: list[str] = []
    violations: list[str] = []
    ui_root = APP_ROOT / "chemvas" / "ui"
    for path in sorted(ui_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = _parse_source(source)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not accessor_name.search(node.name):
                continue
            accessor_key = f"{path.relative_to(ui_root).as_posix()}:{node.name}"
            if accessor_key in NON_RUNTIME_STATE_ACCESSORS:
                continue
            names = _runtime_state_fields(node)
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
            if _has_state_fallback(node):
                violations.append(
                    f"{path.name}:{node.name} falls back off the runtime container"
                )

    assert violations == []
    assert checked, "No state lookups inspected; retire this check with the last one"


def test_state_lookup_guard_allows_removing_a_forwarder(monkeypatch) -> None:
    path = _ui_path("canvas_callback_state.py")
    original_read = Path.read_text

    def read_source(candidate, *args, **kwargs):
        if candidate == path:
            return "# The consumer now receives graph state directly.\n"
        return original_read(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_source)
    test_state_accessors_read_the_runtime_container_directly()


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
    for node in ast.walk(_parse_source(source)):
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
        f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}: {name}"
        for path in _app_python_files()
        for line_no, name in _unread_strict_parameters(path.read_text(encoding="utf-8"))
    ]

    assert violations == []


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
        tree = _parse_source(path.read_text(encoding="utf-8"))
        for line_no, literal in _string_set_literals(tree):
            if members <= literal:
                owners.append(
                    f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}"
                )
    return owners


ARROW_KIND_MEMBERS = frozenset(
    {
        "arrow",
        "equilibrium",
        "equilibrium_forward",
        "equilibrium_reverse",
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
DOCUMENT_STATE_MODULE = "app/chemvas/domain/document/schema.py"


def test_arrow_kinds_are_listed_in_one_module() -> None:
    """The nine arrow kind strings are spelled out exactly once.

    Seven modules used to list them. A kind added to the schema but missed in
    one of the copies is silent: the document validates it while a
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
    for node in ast.walk(_parse_source(source)):
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
        f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}: {name}"
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
GRAPH_ALGORITHMS_MODULE = "app/chemvas/features/graph/algorithms.py"


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
    tree = _parse_source(source)
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
        f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}"
        for path in _app_python_files()
        for line_no in _seeded_reachability_walks(path.read_text(encoding="utf-8"))
    ]

    assert [walk.rsplit(":", 1)[0] for walk in walks] == [GRAPH_ALGORITHMS_MODULE]


BOND_CYCLE_CACHE = "bond_cycle_cache"
BOND_CYCLE_CACHE_MUTATORS = frozenset(
    {"clear", "pop", "popitem", "setdefault", "update"}
)
GRAPH_FEATURE_INIT_MODULE = "app/chemvas/features/graph/__init__.py"
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
    for node in ast.walk(_parse_source(source)):
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
    one side. ``CanvasGraphState`` — the state owner that declares the field
    and empties it when the graph changes — lives in the same feature module
    as ``cached_bond_in_cycle``, so the reset and the one author of entries
    are a single file.

    What escapes: a writer that reaches the mapping through a local alias
    (``cache = graph.bond_cycle_cache``), because the attribute is no longer
    named at the write.
    """
    writers = sorted(
        {
            f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}"
            for path in _app_python_files()
            if _bond_cycle_cache_writes(path.read_text(encoding="utf-8"))
        }
    )

    assert writers == [GRAPH_FEATURE_INIT_MODULE]


def _modules_using(name: str) -> list[str]:
    """Modules that import or call ``name``, however they spell the import."""
    users: list[str] = []
    for path in _app_python_files():
        tree = _parse_source(path.read_text(encoding="utf-8"))
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
            users.append(path.relative_to(APP_ROOT.parents[0]).as_posix())
    return sorted(users)


def test_cycle_membership_is_decided_in_one_module() -> None:
    """One module turns the alternative-path search into "is this bond cyclic".

    That search is the whole of ``bond_in_cycle``; a second consumer of it is
    a second implementation of the question, cache or no cache. Importing it
    under another name still counts, because the import is read rather than
    the call.

    What escapes: reaching the function off its module rather than by name
    (``getattr(graph_algorithms, "...")``), because then neither an import of
    the name nor a call spelling it appears in the tree.
    """
    assert _modules_using(CYCLE_SEARCH_HELPER) == [GRAPH_FEATURE_INIT_MODULE]


GROUP_TRANSACTION_HELPER = "_run_group_state_transaction"
GROUP_COMMAND_CLASSES = ("GroupSceneItemsCommand", "UngroupSceneItemsCommand")
GROUP_STATE_CALLS = frozenset(
    {
        "_group_state_snapshot",
        "_restore_group_state",
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
    for node in ast.walk(_parse_source(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        called = _called_function_names(node)
        touches_group_state = bool(called & GROUP_STATE_CALLS) or any(
            isinstance(sub, ast.Attribute) and sub.attr == "group_state"
            for sub in ast.walk(node)
        )
        if SCENE_RUNTIME_CAPTURE in called and touches_group_state:
            scaffolds.append((node.lineno, node.name))
    return scaffolds


def _group_command_scaffold_routing(source: str) -> dict[str, bool]:
    """For each group command's ``redo``/``undo``, whether it calls the scaffold."""
    routing: dict[str, bool] = {}
    for node in ast.walk(_parse_source(source)):
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
    history_commands = APP_ROOT / "chemvas" / "ui" / "history" / "history_commands.py"
    source = history_commands.read_text(encoding="utf-8")

    scaffolds = [name for _line_no, name in _group_rollback_scaffolds(source)]

    assert scaffolds == [GROUP_TRANSACTION_HELPER]


def test_every_group_command_slot_routes_through_the_scaffold() -> None:
    """All four group command slots reach the scaffold rather than their own."""
    history_commands = APP_ROOT / "chemvas" / "ui" / "history" / "history_commands.py"
    routing = _group_command_scaffold_routing(
        history_commands.read_text(encoding="utf-8")
    )

    assert routing == {
        "GroupSceneItemsCommand.redo": True,
        "GroupSceneItemsCommand.undo": True,
        "UngroupSceneItemsCommand.redo": True,
        "UngroupSceneItemsCommand.undo": True,
    }


CANVAS_DETACH_BODY = "_detach_item_from_canvas_scene"


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
        tree = _parse_source(path.read_text(encoding="utf-8"))
        spellings = _dict_literal_key_sets(tree) + _string_set_literals(tree)
        for line_no, spelled in sorted(spellings, key=lambda entry: entry[0]):
            if members <= spelled:
                owners.append(
                    f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}"
                )
    return owners


def test_precomplex_source_geometry_keys_are_spelled_once_by_the_schema() -> None:
    """The eleven stored geometry keys are spelled out by one schema only.

    Chemvas no longer generates precomplex candidates, so no module builds a
    source-geometry fingerprint from artifacts any more.
    ``domain.document.precomplex._validate_source_geometry`` still checks the
    stored mapping of documents written by older releases, and it lives in the
    layer that owns the document format. One entry is the rule; a second
    anywhere, or a second inside that module, is a duplicate.

    Both the mapping and the bare list of names count, because rebuilding the
    mapping through ``{name: getattr(artifacts, name) for name in NAMES}`` is
    the same duplicate with the keys moved one line up.
    """
    owners = _modules_spelling_out(SOURCE_GEOMETRY_KEY_MEMBERS)

    assert [owner.rsplit(":", 1)[0] for owner in owners] == [
        PRECOMPLEX_SCHEMA_MODULE,
    ]


RING_FILL_SCENE_SERVICE_MODULE = (
    "app/chemvas/ui/canvas/canvas_ring_fill_scene_service.py"
)
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
    ``setPolygon``, and a rebuild that has to learn which atoms the ring
    names and then go find them hits at least one of them.

    Not caught: setting a polygon that arrives already built, which is what
    ``history_operations`` restores and what ``canvas_model_access``
    rescales. Also not caught: a rebuild handed both answers instead of
    working them out -- the ring's atom ids as an argument, so nothing reads
    ``data(2)``, and a mapping to look them up in, so nothing calls
    ``atom_for_id``. Widening either mark to reach that would sweep in every
    function that indexes atoms next to a ``setPolygon``, so the rule stays
    narrow and the escape stays written down.
    """
    tree = _parse_source(source)
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
        f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}: {name}"
        for path in _app_python_files()
        for line_no, name in _ring_polygon_rebuilders(path.read_text(encoding="utf-8"))
    ]

    assert [rebuilder.rsplit(":", 2)[0] for rebuilder in rebuilders] == [
        RING_FILL_SCENE_SERVICE_MODULE
    ]


SCENE_ITEM_POOL_RESET_MODULES = [
    "app/chemvas/features/selection/handles.py",
    "app/chemvas/ui/insert/preview_scene_renderer.py",
]
SCENE_ITEM_POOL_RESET_BODIES = ["clear_handle_items", "clear_scene_items"]
LOOP_NODES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ListComp,
    ast.SetComp,
    ast.GeneratorExp,
    ast.DictComp,
)


def _parameter_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Every name the function is handed, however the signature spells it."""
    arguments = node.args
    declared = [
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
    ]
    if arguments.vararg is not None:
        declared.append(arguments.vararg)
    if arguments.kwarg is not None:
        declared.append(arguments.kwarg)
    return {argument.arg for argument in declared}


def _reads_an_item_scene(node: ast.AST) -> bool:
    """True when something inside ``node`` asks an item which scene it is in.

    ``item.scene()`` is the spelling in the tree. ``getattr(item, "scene")``
    reaches the same bound method with the name moved into a string, and a
    rule in this file has already been slipped past by exactly that move, so
    both count.
    """
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if (
            isinstance(child.func, ast.Attribute)
            and child.func.attr == "scene"
            and not child.args
            and not child.keywords
        ):
            return True
        if (
            isinstance(child.func, ast.Name)
            and child.func.id == "getattr"
            and len(child.args) >= 2
            and isinstance(child.args[1], ast.Constant)
            and child.args[1].value == "scene"
        ):
            return True
    return False


def _looped_scene_detach_names(node: ast.AST) -> set[str]:
    """The names ``removeItem`` is called on from inside a loop in ``node``.

    Every loop node counts, so re-spelling the plain ``for item in items`` as
    ``for item in tuple(items)``, as an index-driven ``while``, or as a
    comprehension run for its side effect does not move the call out of
    reach.
    """
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, LOOP_NODES):
            continue
        for inner in ast.walk(child):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "removeItem"
                and isinstance(inner.func.value, ast.Name)
            ):
                names.add(inner.func.value.id)
    return names


def _scene_item_pool_resets(source: str) -> list[tuple[int, str]]:
    """Functions handed a scene and a pool that empty the pool against it.

    Two marks, and the first is what keeps the rule narrow: ``removeItem`` is
    called from inside a loop on a name the function was *handed*. A function
    that goes and resolves its own scene is asking a different question, so
    ``ui.insert_controller``, ``ui.calculation_mapping_highlight`` and
    ``ui.tools.tool_overlay_logic`` are all out, and ``ui.scene_item_access`` is
    out twice over -- it needs a canvas, and ``_canvas_scoped_detachers``
    above owns that rule. Reaching the scene through ``self`` is out for the
    same reason, which is what keeps
    ``ui.canvas_document_session_service.restore`` from being swept in.

    The escapes, in order of how likely they are:

    * A re-duplication that resolves its own scene instead of taking one --
      ``calculation_mapping_highlight._remove_items`` is already almost this
      loop written that way, differing in that it finds its own scene and
      clears the pool in place. Dropping the parameter mark to reach it also
      sweeps in ``insert_controller``'s pre-clear detach, so the rule
      would need a third and fourth owner spelled out to stay green and would
      stop meaning "two owners". The mark stays and the escape is written
      down here.
    * A reset that detaches unconditionally, never asking an item which scene
      it is in. That is a different and less careful function: the ask is
      what survives an item whose C++ object Qt has already deleted.
    * A reset that reaches ``removeItem`` through a name it computes at run
      time, or that parks the scene on an object first and loops over that.
    """
    resets: list[tuple[int, str]] = []
    for node in ast.walk(_parse_source(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        handed = _parameter_names(node)
        detached = _looped_scene_detach_names(node) & handed
        if detached and _reads_an_item_scene(node):
            resets.append((node.lineno, node.name))
    return sorted(resets)


def test_scene_item_pool_reset_has_one_owner_per_layer() -> None:
    """Two functions empty a pool of scene items, one per layer.

    ``ui.hover_rendering.clear_hover_items`` and
    ``ui.bond_preview_renderer.clear_bond_preview_items`` each spelled the
    same six-line loop as ``ui.preview_scene_renderer.clear_scene_items``;
    both delegate to it now and compose the empty pool their own caller
    reassigns.

    ``features.selection.handles.clear_handle_items`` keeps its copy on
    purpose: the ``features`` layer never imports ``ui``, and no Qt-aware
    home exists that both layers can reach. Two entries is the rule -- a
    third anywhere, or a second inside either layer, is a duplicate.
    """
    resets = [
        f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}: {name}"
        for path in _app_python_files()
        for line_no, name in _scene_item_pool_resets(path.read_text(encoding="utf-8"))
    ]

    assert [
        reset.rsplit(":", 2)[0] for reset in resets
    ] == SCENE_ITEM_POOL_RESET_MODULES
    assert [
        reset.rsplit(": ", 1)[1] for reset in resets
    ] == SCENE_ITEM_POOL_RESET_BODIES


CORE_HISTORY_MODULE = "app/chemvas/core/history.py"
RESTORE_ATOM_STATE_PORT_CALL = "restore_atom_from_state_for_history"
SET_ATOM_POSITIONS_PORT_CALL = "set_atom_positions_for_history"
RESTORE_ATOM_STATES_BODIES = [
    "_restore_atom_states",
    "_restore_atom_states_best_effort",
]


def _imported_name_aliases(tree: ast.AST) -> dict[str, str]:
    """Local binding -> imported name, for every ``as`` rename in the module.

    ``ui.history_commands`` already imports
    ``set_atom_positions_for_history as _set_atom_positions_for_history``, so
    a rule that matched the call site's spelling would miss a copy that
    renamed its import the same way.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for alias in node.names:
            if alias.asname is not None:
                aliases[alias.asname] = alias.name.rsplit(".", 1)[-1]
    return aliases


def _restore_atoms_steps(source: str) -> list[tuple[int, str]]:
    """Functions that restore saved atom states and then place the atoms in 3-D.

    Both port calls, in one function. Nothing about the loop is read, so a
    comprehension run for its side effect, a renamed loop variable, an
    index-driven ``while`` or a rewritten ``if self.atom_coords_3d`` guard
    are all the same duplicate to this rule, and a copy that reaches the port
    through ``port.`` rather than ``_history_canvas_port()`` is too.

    Deliberately not caught: ``_remove_atoms_best_effort``, which the two
    commands still spell out twice because they genuinely differ on
    ``remove_marks``; ``MoveAtomsCommand._apply`` and ``_compensate``, which
    place atoms in 3-D without restoring any saved state.

    The escapes: half a copy -- restoring the atom states without the
    coordinate block, or the reverse -- is not two calls and is not caught.
    Neither is a copy that reaches either port method through a name it
    computes at run time, since the rule reads the spelling in the tree.
    Requiring only one of the two calls would flag six live functions that
    move atoms for other reasons, so the pair is the mark.
    """
    tree = _parse_source(source)
    aliases = _imported_name_aliases(tree)
    steps: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        called = {aliases.get(name, name) for name in _called_function_names(node)}
        if {RESTORE_ATOM_STATE_PORT_CALL, SET_ATOM_POSITIONS_PORT_CALL} <= called:
            steps.append((node.lineno, node.name))
    return sorted(steps)


def test_restore_atoms_steps_have_one_owner_per_failure_mode() -> None:
    """Two helpers restore atom states and their 3-D coordinates.

    ``AddAtomsCommand`` and ``DeleteAtomsCommand`` each wrote the sequence
    twice -- once for the straight path, once for the best-effort rollback --
    for four regions, byte-identical within each pair.
    ``_restore_atom_states`` and
    ``_restore_atom_states_best_effort`` own them now; the two entries are
    the two failure modes, not two copies, because only the rollback one
    wraps each step in ``run_rollback_step``.

    The projection restore that precedes the sequence in the delete command
    and the mark restore that follows it stay at their own call sites, so a
    fifth copy would most likely appear there -- inlined back into a command
    method to put the compensation order in one place again.
    """
    steps = [
        f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}: {name}"
        for path in _app_python_files()
        for line_no, name in _restore_atoms_steps(path.read_text(encoding="utf-8"))
    ]

    assert [step.rsplit(":", 2)[0] for step in steps] == [
        CORE_HISTORY_MODULE,
        CORE_HISTORY_MODULE,
    ]
    assert [step.rsplit(": ", 1)[1] for step in steps] == RESTORE_ATOM_STATES_BODIES


TRANSACTION_RECOVERY_MODULE = "app/chemvas/domain/transactions/recovery.py"
CANONICAL_RECOVERY_NOTE = "add_recovery_error_note"
ROLLBACK_RUNNER_BODIES = ["run_rollback_step"]


def _exception_note_attachments(source: str) -> list[int]:
    """Lines that attach a note to an exception.

    ``BaseException.add_note`` takes exactly one positional-only argument, so
    one positional argument and no keywords is the entire call shape and a
    copy cannot spell it any other way. Nothing about the receiver is read: a
    note put on a caught, re-raised, aliased or attribute-held error is the
    same attachment to this rule, and so is one hidden inside a nested
    closure, which is where the last two copies were found.

    The limitation is the name, not the shape. Chemvas has one live
    ``add_note`` collision -- the sticky-note canvases in ``tests`` answer
    ``add_note(selected=...)`` -- and it stays out of range twice over,
    because this rule reads production sources only and that API is
    keyword-driven. A production note API that took a single positional
    argument would be counted here and would have to be named something else.
    """
    lines: list[int] = []
    for node in ast.walk(_parse_source(source)):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        if not isinstance(called, ast.Attribute) or called.attr != "add_note":
            continue
        if len(node.args) != 1 or node.keywords:
            continue
        lines.append(node.lineno)
    return sorted(lines)


def test_exception_notes_have_one_owner() -> None:
    """One module attaches notes to exceptions.

    Seven modules used to phrase their own "rollback also encountered ..."
    sentence, so a reader chasing a secondary failure had to know which
    subsystem wrote it. ``domain.transactions.recovery`` owns the wording
    now; every other module reaches it through ``add_recovery_error_note`` or
    ``run_rollback_step`` and supplies a phase instead.

    The rule reads calls, not definitions, so re-adding a private
    ``_add_..._note`` helper does not evade it -- the ``add_note`` inside the
    helper is the violation. What it cannot see is a note attached through a
    method name assembled at run time, or through ``BaseException.add_note``
    fetched as an unbound attribute and called with two arguments.
    """
    owners = sorted(
        {
            path.relative_to(APP_ROOT.parents[0]).as_posix()
            for path in _app_python_files()
            if _exception_note_attachments(path.read_text(encoding="utf-8"))
        }
    )

    assert owners == [TRANSACTION_RECOVERY_MODULE]


def _canonical_note_names(tree: ast.AST) -> set[str]:
    """Local names bound to ``add_recovery_error_note`` in one module."""

    names = {CANONICAL_RECOVERY_NOTE}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            if alias.name == CANONICAL_RECOVERY_NOTE and alias.asname is not None:
                names.add(alias.asname)
    return names


def _is_canonical_note_statement(statement: ast.stmt, names: set[str]) -> bool:
    if isinstance(statement, ast.For) and not statement.orelse:
        return len(statement.body) == 1 and _is_canonical_note_statement(
            statement.body[0], names
        )
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return False
    called = statement.value.func
    return isinstance(called, ast.Name) and called.id in names


def _handler_only_notes(handler: ast.ExceptHandler, names: set[str]) -> bool:
    body = list(handler.body)
    if body and isinstance(body[-1], ast.Return):
        returned = body[-1].value
        if returned is not None and not isinstance(returned, (ast.Constant, ast.Name)):
            return False
        body = body[:-1]
    return bool(body) and all(
        _is_canonical_note_statement(statement, names) for statement in body
    )


def _rollback_runners(source: str) -> list[tuple[int, str]]:
    """Functions that are nothing but "run this, and note it if it fails".

    The shape is the whole definition: an optional docstring, then one
    ``try`` whose every handler does no more than call the canonical note
    (any number of times, or once per iteration of a loop) and optionally
    return a constant. That is ``run_rollback_step`` rewritten, which is why
    the canonical one is the single expected match rather than an exclusion
    -- if this detector ever stops recognizing it, the rule fails instead of
    passing on an empty scan.

    Deliberately not caught: the roughly thirty hand-written handlers that
    call the canonical note as one step among several. They re-raise, restore
    state, build a ``RestoreOutcome``, or run under a ``finally``, so they
    are compensation written at its own call site, not a second runner. A
    handler that grows past a bare note stops matching for the same reason,
    which is the escape: a re-derived runner that also logs, or that returns
    a computed value, reads as one of those and is missed.
    """
    tree = _parse_source(source)
    names = _canonical_note_names(tree)
    runners: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        opening = body[0]
        if (
            isinstance(opening, ast.Expr)
            and isinstance(opening.value, ast.Constant)
            and isinstance(opening.value.value, str)
        ):
            body = body[1:]
        if len(body) != 1 or not isinstance(body[0], ast.Try):
            continue
        attempt = body[0]
        if attempt.orelse or attempt.finalbody or not attempt.handlers:
            continue
        if all(_handler_only_notes(handler, names) for handler in attempt.handlers):
            runners.append((node.lineno, node.name))
    return sorted(runners)


def test_rollback_runner_has_one_owner() -> None:
    """One function runs a compensation step and notes its failure.

    A single owner for the note wording does not stop a module from wrapping
    it back up: ``canvas_history_service._notify_failed_operation`` had
    already grown into a private ``run_rollback_step`` with its operation and
    phase frozen in, and passed the note rule while doing it. Each such copy
    re-decides what to swallow and whether to return, which is the policy the
    canonical runner exists to hold.

    The import alias is followed: ``ui.history_commands`` used to import the
    note as ``_add_rollback_error_note``, and a copy that renamed its import
    that way would otherwise read as calling something else.
    """
    runners = [
        f"{path.relative_to(APP_ROOT.parents[0]).as_posix()}:{line_no}: {name}"
        for path in _app_python_files()
        for line_no, name in _rollback_runners(path.read_text(encoding="utf-8"))
    ]

    assert [runner.rsplit(":", 2)[0] for runner in runners] == [
        TRANSACTION_RECOVERY_MODULE
    ]
    assert [runner.rsplit(": ", 1)[1] for runner in runners] == ROLLBACK_RUNNER_BODIES


def test_document_item_state_does_not_own_transient_selection() -> None:
    path = APP_ROOT / "chemvas" / "ui" / "canvas" / "canvas_scene_items_state.py"
    assert _matching_lines(re.compile(r"\bselected_notes\b"), [path]) == []
