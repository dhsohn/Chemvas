"""Keep the experimental browser editor out of built distributions.

Project metadata and package discovery live in ``pyproject.toml``. The browser
editor runs from a source checkout only, but its Python modules share the
``chemvas.bootstrap`` package with shipped code, and declarative setuptools
configuration can only exclude whole packages. This hook drops the named
modules from both the sdist file list and the wheel. Its HTML/CSS/MJS assets
are simply not declared as package data. The sdist carries this file, so a
wheel rebuilt from the sdist keeps the same boundary.

``scripts/verify_dist.py`` rejects any artifact that contains browser editor
files using its own patterns, so a stale or incomplete list here cannot ship.
"""

from __future__ import annotations

from setuptools import setup
from setuptools.command.build_py import build_py

SOURCE_CHECKOUT_ONLY_MODULES = frozenset(
    (
        "chemvas.bootstrap.web_adapter",
        "chemvas.bootstrap.web_drafts",
    )
)


class BuildPyWithoutBrowserEditor(build_py):
    def find_package_modules(
        self, package: str, package_dir: str
    ) -> list[tuple[str, str, str]]:
        return [
            (owner, module, path)
            for owner, module, path in super().find_package_modules(
                package, package_dir
            )
            if f"{owner}.{module}" not in SOURCE_CHECKOUT_ONLY_MODULES
        ]


setup(cmdclass={"build_py": BuildPyWithoutBrowserEditor})
