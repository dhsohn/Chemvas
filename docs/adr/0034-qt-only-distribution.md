# ADR 0034: Qt-only distribution

- Status: Accepted
- Date: 2026-10-04
- Depends on: ADR 0005 (responsibility-based editor boundaries)

## Problem

Chemvas 0.24.0 stabilizes desktop Qt drawing, headless CLI workflows, and
editable CDXML export. In parallel, an experimental browser presentation
adapter (`chemvas --ui web`) is under active development in the repository for
future Leaf integration.

The browser adapter is not ready or intended to be a standalone released web
product. Including its modules and web assets in versioned PyPI distribution
artifacts (wheels and sdist) would misrepresent experimental code as a public,
supported product surface, impose release stability guarantees on incomplete
web features, and lead to user confusion if the web server fails or behaves
incompletely in packaged environments.

## Decision

1. **Qt-only release scope.** Official distribution artifacts for version
   0.24.0 deliver the desktop PyQt6 application and supported headless CLI
   commands only. There is no standalone web release.

2. **Packaging and frozen bundle exclusion boundary.** Built wheels and source
   distributions (sdist) exclude browser adapter modules
   (`chemvas.bootstrap.web_adapter`, `chemvas.bootstrap.web_drafts`) and web
   assets (`chemvas/web/`). The frozen application spec declares the same
   exclusions while preserving Qt, optional RDKit, icons, and license data.

3. **Packaging and bundle implementation.** `setup.py` provides a custom
   `BuildPyWithoutBrowserEditor` command that drops the browser adapter
   modules from the build. `MANIFEST.in` prunes `app/chemvas/web` and
   excludes the modules, while including `setup.py` so that wheels rebuilt
   from the sdist enforce the exact same boundary. `pyproject.toml` omits
   web assets from `package-data`. The PyInstaller spec (`packaging/chemvas.spec`)
   excludes `chemvas.bootstrap.web_adapter` and `chemvas.bootstrap.web_drafts`
   via `excludes=SOURCE_CHECKOUT_ONLY_MODULES` and leaves web assets out of
   datas, declaring the same boundary for frozen desktop bundles.

4. **Source repository retention.** The browser adapter source code remains
   in the repository and is available for development and Leaf integration
   from a source checkout (`pip install -e .` or developer venvs). GitHub
   release tag archives provide repository snapshots at a tag, not a released
   web product.

5. **Packaging verification gate.** `scripts/verify_dist.py` validates built
   wheels and sdists against explicit inclusion and exclusion patterns prior
   to publication. Any leak of browser adapter modules or assets fails the
   distribution gate.

6. **Packaged CLI behavior.** When invoked with `--ui web` in an installed
   package environment where the browser adapter is absent, `chemvas` exits
   with an explicit error stating that the web editor is not included in the
   installation and runs from a source checkout only.

## Verification and limits

- `scripts/verify_dist.py` inventories and byte-binds built distribution
  artifacts against reviewed build inputs, validating that both wheels and
  sdist contain all required desktop files and none of the excluded browser
  files; it does not execute rebuilds itself.
- `python -m build` first builds the sdist, then builds the wheel from that
  sdist. Packaging unit tests exercise the `setup.py` custom build hook and
  synthetic archives.
- Spec analysis tests (`tests/test_windows_bundle.py`) verify the frozen-bundle
  exclusion declarations and metadata preservation using a spec harness.
  CI builds the wheel and sdist and verifies installed CLI behavior; its Windows
  job also exercises the native installer compiler. These checks do not build
  and launch the full PyInstaller app. A frozen application needs separate
  verification before that bundle is distributed.
- Releases require passing exact-`main` CI and platform tests on macOS and
  Windows before tagging.
- This decision explicitly excludes the browser adapter from release stability
  guarantees; web features remain experimental until separate integration.
