from __future__ import annotations

import argparse
import tarfile
from pathlib import Path
from zipfile import ZipFile

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


def verify_wheel(path: Path) -> None:
    with ZipFile(path) as wheel:
        names = frozenset(wheel.namelist())
        roots = {name.partition("/")[0] for name in names if "/" in name}
        dist_info_roots = {root for root in roots if root.endswith(".dist-info")}
        if len(dist_info_roots) != 1:
            raise ValueError(
                f"expected one .dist-info directory, found {dist_info_roots}"
            )
        allowed_roots = {"chemvas", *dist_info_roots}
        if roots != allowed_roots:
            raise ValueError(f"unexpected wheel roots: {sorted(roots - allowed_roots)}")

        required = {
            "chemvas/__init__.py",
            "chemvas/__main__.py",
            "chemvas/adapters/macos_app_identity.py",
            "chemvas/adapters/qt/file_open_events.py",
            "chemvas/adapters/qt/renderer.py",
            "chemvas/bootstrap/application.py",
            "chemvas/bootstrap/calculation_bundle.py",
            "chemvas/bootstrap/document_patch.py",
            "chemvas/bootstrap/document_render.py",
            "chemvas/bootstrap/main_window.py",
            "chemvas/core/document_io.py",
            "chemvas/domain/document/calculation_plan.py",
            "chemvas/domain/document/model.py",
            "chemvas/features/calculation_bundle/__init__.py",
            "chemvas/features/calculation_bundle/model.py",
            "chemvas/features/calculation_bundle/plan.py",
            "chemvas/features/calculation_bundle/service.py",
            "chemvas/features/document_patch/__init__.py",
            "chemvas/features/document_patch/service.py",
            "chemvas/features/rendering/acs1996_style.py",
            "chemvas/shell/icon_design.py",
            "chemvas/shell/icon_factory.py",
            "chemvas/shell/icon_pixmap_factory.py",
            "chemvas/shell/main_window.py",
            "chemvas/shell/palette.py",
            "chemvas/shell/stylesheet.py",
            "chemvas/shell/theme.py",
            "chemvas/shell/toolbar_buttons.py",
            "chemvas/shell/toolbar_styles.py",
            "chemvas/ui/__init__.py",
            "chemvas/ui/calculation_mapping_highlight.py",
            "chemvas/ui/calculation_step_dialog.py",
            "chemvas/ui/canvas_calculation_plan_state.py",
            "chemvas/assets/icon/chemvas.svg",
            "chemvas/assets/icon/chemvas-16.png",
            "chemvas/assets/icon/chemvas-512.png",
        }
        missing = required - names
        if missing:
            raise ValueError(f"wheel is missing required files: {sorted(missing)}")

        forbidden = {
            "chemvas/core/document_state.py",
            "chemvas/core/model.py",
            "chemvas/core/rdkit_types.py",
            "chemvas/core/renderer.py",
            "chemvas/core/style_acs1996.py",
            "chemvas/file_open.py",
            "chemvas/main.py",
            "chemvas/ui/main_window.py",
            "chemvas/ui/main_window_app.py",
            "chemvas/ui/main_window_design_icon_renderer.py",
            "chemvas/ui/main_window_icon_factory.py",
            "chemvas/ui/main_window_icon_pixmap_factory.py",
            "chemvas/ui/main_window_palette.py",
            "chemvas/ui/main_window_stylesheet.py",
            "chemvas/ui/main_window_template_icon_renderer.py",
            "chemvas/ui/main_window_theme.py",
            "chemvas/ui/main_window_toolbar_buttons.py",
            "chemvas/ui/main_window_toolbar_styles.py",
            "chemvas/ui/structure_fragment_build_service.py",
            "chemvas/ui/structure_template_build_service.py",
            "chemvas/ui/structure_template_commands.py",
            "chemvas/ui/tools.py",
        }
        unexpected = forbidden & names
        if unexpected:
            raise ValueError(
                f"wheel contains removed compatibility files: {sorted(unexpected)}"
            )

        dist_info = next(iter(dist_info_roots))
        entry_points = wheel.read(f"{dist_info}/entry_points.txt").decode()
        expected_entry_point = "chemvas = chemvas.bootstrap.application:main"
        if expected_entry_point not in entry_points:
            raise ValueError(f"wheel console entry point is not {expected_entry_point}")


def verify_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as sdist:
        names = frozenset(member.name for member in sdist.getmembers())
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
        missing = required - names
        if missing:
            raise ValueError(f"sdist is missing required files: {sorted(missing)}")


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
