"""Distribution contents follow the package declaration, not a partial file list."""

import ast
import io
import runpy
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest
from scripts import verify_dist

ROOT = Path(__file__).resolve().parents[1]
DIST_INFO = "chemvas-0.0.0.dist-info"
SDIST_ROOT = "chemvas-0.0.0"
# The experimental browser editor in this checkout; no distribution carries it.
BROWSER_EDITOR_MODULES = frozenset(
    ("chemvas/bootstrap/web_adapter.py", "chemvas/bootstrap/web_drafts.py")
)
BROWSER_EDITOR_ASSETS = frozenset(
    (
        "chemvas/web/app.mjs",
        "chemvas/web/clipboard.mjs",
        "chemvas/web/index.html",
        "chemvas/web/scene.mjs",
        "chemvas/web/style.css",
        "chemvas/web/transport.mjs",
    )
)


@pytest.fixture
def current_package_files():
    package = ROOT / "app" / "chemvas"
    return {
        path.relative_to(ROOT / "app").as_posix()
        for path in package.rglob("*")
        if path.is_file()
        and (
            path.suffix == ".py"
            or (
                path.parent == package / "assets" / "icon"
                and path.suffix in {".svg", ".png"}
            )
        )
    } - BROWSER_EDITOR_MODULES


def _wheel(tmp_path, package_files, *, extra=(), entry_point=None):
    target = tmp_path / "chemvas.whl"
    with ZipFile(target, "w") as archive:
        for name in sorted(package_files | set(extra)):
            archive.writestr(name, "synthetic package file\n")
        archive.writestr(
            f"{DIST_INFO}/entry_points.txt",
            entry_point
            if entry_point is not None
            else "[console_scripts]\nchemvas = chemvas.bootstrap.application:main\n",
        )
    return target


def _build_inputs():
    return {
        name: (verify_dist.ROOT / name).read_bytes()
        for name in verify_dist.SDIST_BUILD_INPUTS
    }


def _sdist(tmp_path, package_files, *, extra=(), build_inputs=None):
    target = tmp_path / "chemvas.tar.gz"
    if build_inputs is None:
        build_inputs = _build_inputs()
    names = {
        "PKG-INFO",
        "LICENSE",
        "README.md",
        "app/chemvas.egg-info/PKG-INFO",
        *build_inputs,
        *(f"app/{name}" for name in package_files),
        *extra,
    }
    with tarfile.open(target, "w:gz") as archive:
        for name in sorted(names):
            data = build_inputs.get(name, b"synthetic distribution file\n")
            info = tarfile.TarInfo(f"{SDIST_ROOT}/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return target


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_current_package_inventory_is_accepted(tmp_path, current_package_files, kind):
    writer = _wheel if kind == "wheel" else _sdist
    verify = verify_dist.verify_wheel if kind == "wheel" else verify_dist.verify_sdist
    verify(writer(tmp_path, current_package_files))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize(
    "missing", ["chemvas/ui/canvas/canvas_view.py", "chemvas/core/rdkit_conversion.py"]
)
def test_missing_runtime_module_is_rejected(
    tmp_path, current_package_files, kind, missing
):
    assert missing in current_package_files
    writer = _wheel if kind == "wheel" else _sdist
    verify = verify_dist.verify_wheel if kind == "wheel" else verify_dist.verify_sdist
    with pytest.raises(ValueError, match="missing.*" + missing):
        verify(writer(tmp_path, current_package_files - {missing}))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize(
    "extra", ["chemvas/ui/obsolete_wrapper.py", "chemvas/assets/unlisted.txt"]
)
def test_undeclared_package_file_is_rejected(
    tmp_path, current_package_files, kind, extra
):
    writer = _wheel if kind == "wheel" else _sdist
    verify = verify_dist.verify_wheel if kind == "wheel" else verify_dist.verify_sdist
    with pytest.raises(ValueError, match="unexpected.*" + extra):
        verify(writer(tmp_path, current_package_files | {extra}))


def test_wheel_keeps_namespace_and_console_entry_point_guards(
    tmp_path, current_package_files
):
    with pytest.raises(ValueError, match="unexpected wheel roots"):
        verify_dist.verify_wheel(
            _wheel(tmp_path, current_package_files, extra={"ui/__init__.py"})
        )
    with pytest.raises(ValueError, match="console entry point"):
        verify_dist.verify_wheel(
            _wheel(tmp_path, current_package_files, entry_point="[console_scripts]\n")
        )


def test_sdist_keeps_top_level_guard(tmp_path, current_package_files):
    with pytest.raises(ValueError, match="unexpected sdist entries"):
        verify_dist.verify_sdist(
            _sdist(tmp_path, current_package_files, extra={"examples/unused.txt"})
        )


@pytest.mark.parametrize(
    "member", ["chemvas-0.0.0/examples/synthetic-link", "another-root/synthetic-link"]
)
@pytest.mark.parametrize(
    "member_type", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE]
)
def test_sdist_keeps_all_member_root_guards(
    tmp_path, current_package_files, member, member_type
):
    artifact = _sdist(tmp_path, current_package_files)
    with tarfile.open(artifact, "r:gz") as archive:
        original = [(info, archive.extractfile(info).read()) for info in archive]
    with tarfile.open(artifact, "w:gz") as archive:
        for info, data in original:
            archive.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(member)
        link.type = member_type
        link.linkname = "synthetic-target"
        archive.addfile(link)
    with pytest.raises(ValueError, match="unexpected sdist|one sdist root"):
        verify_dist.verify_sdist(artifact)


def test_wheel_keeps_directory_root_guard(tmp_path, current_package_files):
    artifact = _wheel(tmp_path, current_package_files)
    with ZipFile(artifact, "a") as archive:
        archive.writestr("foreign/", "")
    with pytest.raises(ValueError, match="unexpected wheel roots"):
        verify_dist.verify_wheel(artifact)


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize(
    "leaked",
    [
        *sorted(BROWSER_EDITOR_MODULES),
        *sorted(BROWSER_EDITOR_ASSETS),
        "chemvas/bootstrap/web_session.py",
        "chemvas/web/__init__.py",
        "chemvas/assets/icon/preview.html",
        "chemvas/ui/viewer.js",
    ],
)
def test_browser_editor_leak_is_rejected(tmp_path, current_package_files, kind, leaked):
    writer = _wheel if kind == "wheel" else _sdist
    verify = verify_dist.verify_wheel if kind == "wheel" else verify_dist.verify_sdist
    with pytest.raises(ValueError, match="experimental browser editor.*" + leaked):
        verify(writer(tmp_path, current_package_files | {leaked}))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize(
    "missing",
    [
        "chemvas/bootstrap/application.py",
        "chemvas/adapters/qt/file_open_events.py",
        "chemvas/assets/icon/chemvas.svg",
    ],
)
def test_missing_qt_desktop_file_is_named(
    tmp_path, current_package_files, kind, missing
):
    assert missing in verify_dist.REQUIRED_DESKTOP_FILES
    writer = _wheel if kind == "wheel" else _sdist
    verify = verify_dist.verify_wheel if kind == "wheel" else verify_dist.verify_sdist
    with pytest.raises(ValueError, match="missing Qt desktop files.*" + missing):
        verify(writer(tmp_path, current_package_files - {missing}))


def test_required_desktop_files_are_shipped(current_package_files):
    assert verify_dist.REQUIRED_DESKTOP_FILES <= current_package_files


@pytest.mark.parametrize("name", ["setup.py", "pyproject.toml"])
def test_sdist_must_carry_the_reviewed_build_inputs(
    tmp_path, current_package_files, name
):
    """A wheel rebuilt from the sdist must see the same boundary."""
    build_inputs = _build_inputs()
    del build_inputs[name]
    with pytest.raises(ValueError, match="missing required files.*" + name):
        verify_dist.verify_sdist(
            _sdist(tmp_path, current_package_files, build_inputs=build_inputs)
        )
    reopened = {
        "setup.py": (b'"chemvas.bootstrap.web_drafts",\n', b""),
        "pyproject.toml": (b'"assets/icon/*.png"]', b'"assets/icon/*.png", "web/*"]'),
    }[name]
    build_inputs = _build_inputs()
    build_inputs[name] = build_inputs[name].replace(*reopened)
    assert build_inputs[name] != _build_inputs()[name]
    with pytest.raises(ValueError, match=f"sdist {name} differs"):
        verify_dist.verify_sdist(
            _sdist(tmp_path, current_package_files, build_inputs=build_inputs)
        )


def _build_hook_modules():
    tree = ast.parse((ROOT / "setup.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "SOURCE_CHECKOUT_ONLY_MODULES"
        ):
            return {
                module.replace(".", "/") + ".py"
                for module in ast.literal_eval(node.value.args[0])
            }
    raise AssertionError("setup.py no longer names its source-checkout-only modules")


def test_browser_editor_stays_runnable_from_the_source_checkout():
    source = ROOT / "app"
    for name in BROWSER_EDITOR_MODULES | BROWSER_EDITOR_ASSETS:
        assert (source / name).is_file(), name
    assert (
        verify_dist.source_checkout_only_files(BROWSER_EDITOR_ASSETS)
        == BROWSER_EDITOR_ASSETS
    )
    # Discovery still finds the modules, so the build hook must drop exactly them.
    declared = verify_dist.declared_package_files()
    assert verify_dist.source_checkout_only_files(declared) == BROWSER_EDITOR_MODULES
    assert _build_hook_modules() == BROWSER_EDITOR_MODULES


def test_build_hook_drops_browser_editor_modules(monkeypatch):
    import setuptools
    from setuptools.dist import Distribution

    captured = {}
    monkeypatch.setattr(setuptools, "setup", lambda **options: captured.update(options))
    runpy.run_path(str(ROOT / "setup.py"), run_name="chemvas_build_hook")
    distribution = Distribution(
        {
            "name": "chemvas",
            "package_dir": {"": "app"},
            "packages": ["chemvas.bootstrap"],
        }
    )
    distribution.script_name = str(ROOT / "setup.py")
    command = captured["cmdclass"]["build_py"](distribution)
    modules = command.find_package_modules(
        "chemvas.bootstrap", str(ROOT / "app" / "chemvas" / "bootstrap")
    )
    shipped = {f"chemvas/bootstrap/{module}.py" for _package, module, _path in modules}
    assert "chemvas/bootstrap/application.py" in shipped
    assert "chemvas/bootstrap/document_render.py" in shipped
    assert not shipped & BROWSER_EDITOR_MODULES


def test_shipped_modules_do_not_import_the_browser_editor():
    """Only the guarded ``--ui web`` dispatch may name the browser editor."""
    source = ROOT / "app"
    declared = verify_dist.declared_package_files()
    shipped = declared - verify_dist.source_checkout_only_files(declared)
    offenders = []
    for name in sorted(shipped):
        if not name.endswith(".py") or name == "chemvas/bootstrap/application.py":
            continue
        tree = ast.parse((source / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [
                    node.module,
                    *(f"{node.module}.{alias.name}" for alias in node.names),
                ]
            else:
                continue
            if verify_dist.source_checkout_only_files(
                {module.replace(".", "/") + ".py" for module in modules}
            ):
                offenders.append(f"{name}:{node.lineno}")
    assert offenders == []


@pytest.fixture
def package_source(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[build-system]\nbuild-backend = "setuptools.build_meta"\n'
        "[tool.setuptools]\ninclude-package-data = false\n"
        '[tool.setuptools.packages.find]\nwhere = ["app"]\n'
        'include = ["chemvas*"]\nnamespaces = false\n'
        '[tool.setuptools.package-data]\nchemvas = ["assets/*.png"]\n',
        encoding="utf-8",
    )
    for name in (
        "chemvas/__init__.py",
        "chemvas/core/__init__.py",
        "chemvas/core/runtime.py",
        "chemvas/assets/icon.png",
        "chemvas/assets/unlisted.txt",
        "chemvas/not_a_package/ignored.py",
        "chemvas/not_a_package/child/__init__.py",
        "other/__init__.py",
    ):
        path = source / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic\n", encoding="utf-8")
    (source / "setup.py").write_bytes((ROOT / "setup.py").read_bytes())
    monkeypatch.setattr(verify_dist, "ROOT", source)
    monkeypatch.setattr(
        verify_dist,
        "REQUIRED_DESKTOP_FILES",
        frozenset(("chemvas/__init__.py", "chemvas/core/runtime.py")),
    )
    return source


def test_regular_packages_and_explicit_data_follow_declaration(package_source):
    expected = {
        "chemvas/__init__.py",
        "chemvas/core/__init__.py",
        "chemvas/core/runtime.py",
        "chemvas/assets/icon.png",
    }
    assert verify_dist.declared_package_files() == expected
    declaration = package_source / "pyproject.toml"
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace("assets/*.png", "assets/*.txt"),
        encoding="utf-8",
    )
    assert verify_dist.declared_package_files() == (
        expected - {"chemvas/assets/icon.png"} | {"chemvas/assets/unlisted.txt"}
    )
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace(
            'include = ["chemvas*"]',
            'include = ["chemvas*"]\nexclude = ["chemvas.core"]',
        ),
        encoding="utf-8",
    )
    assert verify_dist.declared_package_files() == {
        "chemvas/__init__.py",
        "chemvas/assets/unlisted.txt",
    }


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_new_source_file_becomes_required_without_verifier_edit(
    package_source, tmp_path, kind
):
    before = verify_dist.declared_package_files()
    writer = _wheel if kind == "wheel" else _sdist
    verify = verify_dist.verify_wheel if kind == "wheel" else verify_dist.verify_sdist
    artifact = writer(tmp_path, before)
    verify(artifact)
    (package_source / "app/chemvas/core/new_module.py").write_text(
        "new source file\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="missing.*chemvas/core/new_module.py"):
        verify(artifact)
    verify(writer(tmp_path, before | {"chemvas/core/new_module.py"}))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_changed_data_declaration_rejects_stale_artifact(
    package_source, tmp_path, kind
):
    before = verify_dist.declared_package_files()
    writer = _wheel if kind == "wheel" else _sdist
    verify = verify_dist.verify_wheel if kind == "wheel" else verify_dist.verify_sdist
    artifact = writer(tmp_path, before)
    declaration = package_source / "pyproject.toml"
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace("assets/*.png", "assets/*.txt"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing.*unlisted.txt.*unexpected.*icon.png"):
        verify(artifact)
    verify(
        writer(
            tmp_path,
            before - {"chemvas/assets/icon.png"} | {"chemvas/assets/unlisted.txt"},
        )
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("setuptools.build_meta", "another.backend"),
        ("include-package-data = false", "include-package-data = true"),
        ("namespaces = false", "namespaces = true"),
        ('where = ["app"]', 'where = ["src"]'),
    ],
)
def test_different_packaging_shapes_require_explicit_verifier_review(
    package_source, old, new
):
    declaration = package_source / "pyproject.toml"
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="package declaration changed"):
        verify_dist.declared_package_files()


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_declared_browser_editor_is_still_rejected(package_source, tmp_path, kind):
    """A declaration that ships the browser editor does not make the leak valid."""
    browser_editor = {"chemvas/bootstrap/web_adapter.py", "chemvas/web/index.html"}
    for name in ("chemvas/bootstrap/__init__.py", *browser_editor):
        (package_source / "app" / name).parent.mkdir(parents=True, exist_ok=True)
        (package_source / "app" / name).write_text("synthetic\n", encoding="utf-8")
    declaration = package_source / "pyproject.toml"
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace(
            '"assets/*.png"', '"assets/*.png", "web/*.html"'
        ),
        encoding="utf-8",
    )
    declared = verify_dist.declared_package_files()
    assert browser_editor <= declared
    writer = _wheel if kind == "wheel" else _sdist
    verify = verify_dist.verify_wheel if kind == "wheel" else verify_dist.verify_sdist
    with pytest.raises(ValueError, match="experimental browser editor"):
        verify(writer(tmp_path, declared))
    verify(writer(tmp_path, declared - browser_editor))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_narrowed_declaration_cannot_drop_desktop_files(package_source, tmp_path, kind):
    """An artifact that matches a narrowed declaration still needs the Qt files."""
    declaration = package_source / "pyproject.toml"
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace(
            'include = ["chemvas*"]',
            'include = ["chemvas*"]\nexclude = ["chemvas.core"]',
        ),
        encoding="utf-8",
    )
    declared = verify_dist.declared_package_files()
    assert "chemvas/core/runtime.py" not in declared
    writer = _wheel if kind == "wheel" else _sdist
    verify = verify_dist.verify_wheel if kind == "wheel" else verify_dist.verify_sdist
    with pytest.raises(
        ValueError, match="missing Qt desktop files.*chemvas/core/runtime.py"
    ):
        verify(writer(tmp_path, declared))
