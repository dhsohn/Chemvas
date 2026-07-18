from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZipFile


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
            "chemvas/adapters/qt/file_open_events.py",
            "chemvas/bootstrap/application.py",
            "chemvas/bootstrap/main_window.py",
            "chemvas/domain/document/model.py",
            "chemvas/shell/main_window.py",
            "chemvas/ui/__init__.py",
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
            "chemvas/file_open.py",
            "chemvas/main.py",
            "chemvas/ui/main_window.py",
            "chemvas/ui/main_window_app.py",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the Chemvas wheel contract")
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    verify_wheel(args.wheel)


if __name__ == "__main__":
    main()
