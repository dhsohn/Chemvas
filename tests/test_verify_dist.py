"""Distribution contents follow the package declaration, not a partial file list."""

import io
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest
from scripts import verify_dist

ROOT = Path(__file__).resolve().parents[1]
DIST_INFO = "chemvas-0.0.0.dist-info"
SDIST_ROOT = "chemvas-0.0.0"


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
    }


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


def _sdist(tmp_path, package_files, *, extra=()):
    target = tmp_path / "chemvas.tar.gz"
    names = {
        "pyproject.toml",
        "PKG-INFO",
        "LICENSE",
        "README.md",
        "app/chemvas.egg-info/PKG-INFO",
        *(f"app/{name}" for name in package_files),
        *extra,
    }
    with tarfile.open(target, "w:gz") as archive:
        for name in sorted(names):
            data = b"synthetic distribution file\n"
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
    "missing", ["chemvas/ui/canvas_view.py", "chemvas/core/rdkit_conversion.py"]
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
    monkeypatch.setattr(verify_dist, "ROOT", source)
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
