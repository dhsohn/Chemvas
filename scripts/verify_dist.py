from __future__ import annotations

import argparse
import tarfile
import tomllib
from fnmatch import fnmatchcase
from glob import glob
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SDIST_ALLOWED_TOP_LEVEL = frozenset(
    (
        "LICENSE",
        "MANIFEST.in",
        "PKG-INFO",
        "README.md",
        "app",
        "pyproject.toml",
        "setup.cfg",
    )
)


def declared_package_files() -> set[str]:
    """Read this project's regular-package and explicit package-data declaration."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    settings = config["tool"]["setuptools"]
    discovery = settings["packages"]["find"]
    if (
        config["build-system"]["build-backend"] != "setuptools.build_meta"
        or settings["include-package-data"] is not False
        or set(settings)
        - {"dynamic", "include-package-data", "packages", "package-data"}
        or discovery["where"] != ["app"]
        or discovery["namespaces"] is not False
        or set(discovery) - {"where", "include", "exclude", "namespaces"}
    ):
        raise ValueError(
            "package declaration changed; review distribution verification"
        )
    source = ROOT / "app"
    include = discovery.get("include", ["*"])
    exclude = discovery.get("exclude", [])
    package_data = settings.get("package-data", {})
    files: set[str] = set()
    for initializer in source.rglob("__init__.py"):
        directory = initializer.parent
        relative = directory.relative_to(source)
        if not all(
            (source / parent / "__init__.py").is_file()
            for parent in relative.parents
            if parent != Path(".")
        ):
            continue
        package = ".".join(relative.parts)
        if not any(fnmatchcase(package, pattern) for pattern in include) or any(
            fnmatchcase(package, pattern) for pattern in exclude
        ):
            continue
        files.update(
            path.relative_to(source).as_posix()
            for path in directory.glob("*.py")
            if path.is_file()
        )
        for pattern in [*package_data.get("*", []), *package_data.get(package, [])]:
            for name in glob(str(directory / pattern), recursive=True):
                path = Path(name)
                if path.is_file():
                    files.add(path.relative_to(source).as_posix())
    if "chemvas/__init__.py" not in files or any(
        not name.startswith("chemvas/") for name in files
    ):
        raise ValueError("package declaration must contain only the chemvas namespace")
    return files


def _verify_package_files(actual: set[str], kind: str) -> None:
    expected = declared_package_files()
    missing = expected - actual
    unexpected = actual - expected
    if missing or unexpected:
        raise ValueError(
            f"{kind} package inventory mismatch: missing {sorted(missing)}; "
            f"unexpected {sorted(unexpected)}"
        )


def verify_wheel(path: Path) -> None:
    with ZipFile(path) as wheel:
        names = set(wheel.namelist())
        roots = {name.partition("/")[0] for name in names}
        dist_info_roots = {root for root in roots if root.endswith(".dist-info")}
        if len(dist_info_roots) != 1:
            raise ValueError(
                f"expected one .dist-info directory, found {dist_info_roots}"
            )
        allowed_roots = {"chemvas", *dist_info_roots}
        if roots != allowed_roots:
            raise ValueError(f"unexpected wheel roots: {sorted(roots - allowed_roots)}")

        _verify_package_files(
            {
                name
                for name in names
                if name.partition("/")[0] == "chemvas" and not name.endswith("/")
            },
            "wheel",
        )

        dist_info = next(iter(dist_info_roots))
        entry_points = wheel.read(f"{dist_info}/entry_points.txt").decode()
        expected_entry_point = "chemvas = chemvas.bootstrap.application:main"
        if expected_entry_point not in entry_points:
            raise ValueError(f"wheel console entry point is not {expected_entry_point}")


def verify_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as sdist:
        members = sdist.getmembers()
        names = {member.name for member in members}
        file_names = {member.name for member in members if member.isfile()}
        roots = {name.partition("/")[0] for name in names}
        if len(roots) != 1:
            raise ValueError(
                f"expected one sdist root directory, found {sorted(roots)}"
            )
        root = next(iter(roots))
        entries = {
            name.removeprefix(f"{root}/").partition("/")[0]
            for name in names
            if name != root
        }
        unexpected = entries - SDIST_ALLOWED_TOP_LEVEL
        if unexpected:
            raise ValueError(f"unexpected sdist entries: {sorted(unexpected)}")
        required = {
            f"{root}/pyproject.toml",
            f"{root}/PKG-INFO",
            f"{root}/LICENSE",
            f"{root}/README.md",
            f"{root}/app/chemvas/__init__.py",
        }
        missing = required - file_names
        if missing:
            raise ValueError(f"sdist is missing required files: {sorted(missing)}")
        _verify_package_files(
            {
                member.name.removeprefix(f"{root}/app/")
                for member in members
                if member.isfile()
                and member.name.startswith(f"{root}/app/")
                and not member.name.startswith(f"{root}/app/chemvas.egg-info/")
            },
            "sdist",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the Chemvas distribution contracts"
    )
    parser.add_argument("distributions", type=Path, nargs="+")
    args = parser.parse_args()
    for distribution in args.distributions:
        if distribution.name.endswith(".whl"):
            verify_wheel(distribution)
        elif distribution.name.endswith(".tar.gz"):
            verify_sdist(distribution)
        else:
            raise ValueError(f"unsupported distribution artifact: {distribution}")


if __name__ == "__main__":
    main()
