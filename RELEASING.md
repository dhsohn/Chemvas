# Releasing Chemvas

[한국어](RELEASING.ko.md)

Chemvas packages are published to [PyPI](https://pypi.org/project/chemvas/) via GitHub Actions using Trusted Publishing (OIDC). Pushing a `v*` tag triggers [`.github/workflows/release.yml`](.github/workflows/release.yml) to build and upload wheels and sdist.

Built distribution artifacts (wheels and sdist) contain the desktop Qt application and headless CLI only. The frozen application spec declares the same Qt-only boundary. Experimental browser editor files are excluded from packages by `setup.py` and `MANIFEST.in`, and from frozen bundles by `packaging/chemvas.spec` (`chemvas.bootstrap.web_adapter` and `chemvas.bootstrap.web_drafts` excluded), while preserving Qt, optional RDKit, icons, and license data. GitHub release tag source archives retain repository files for development, but do not constitute a released web product.

Version number is sourced from `chemvas.__version__` in [`app/chemvas/__init__.py`](app/chemvas/__init__.py).

## Release Steps

1. Update `__version__` in `app/chemvas/__init__.py`.
2. Update [`CHANGELOG.md`](CHANGELOG.md) by moving unreleased items to the new version section.
3. Open a PR, merge it into `main`, and ensure CI passes on exact `main`. Then
   run the **Platform tests** workflow on `main` (Actions → Platform tests → Run workflow)
   and ensure macOS and Windows suites pass; pull request CI does not run them.
   Verify distribution artifacts locally:
   ```bash
   python -m build
   python scripts/verify_dist.py dist/*
   ```
   `python -m build` first builds the sdist, then builds the wheel from that sdist. `scripts/verify_dist.py` checks the artifact inventory and packaged build inputs; it does not itself execute a rebuild. CI checks real distribution artifacts and installed CLI behavior. The Windows job tests the bundle spec and native installer compiler; it does not build and launch the full PyInstaller application. Verify a frozen application separately before distributing that bundle.
4. Tag and push the release from exact `main`:

```bash
git checkout main && git pull
git tag -a v0.24.0 -m "Chemvas 0.24.0"
git push origin v0.24.0
```

5. Verify the published package in a clean environment:

```bash
python -m venv .release-check
.release-check/bin/python -m pip install "chemvas==0.24.0"
.release-check/bin/chemvas --version
.release-check/bin/chemvas
```
