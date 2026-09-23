# Releasing Chemvas

[한국어](RELEASING.ko.md)

Chemvas packages are published to [PyPI](https://pypi.org/project/chemvas/) via GitHub Actions using Trusted Publishing (OIDC). Pushing a `v*` tag triggers [`.github/workflows/release.yml`](.github/workflows/release.yml) to build and upload wheels and sdist.

Version number is sourced from `chemvas.__version__` in [`app/chemvas/__init__.py`](app/chemvas/__init__.py).

## Release Steps

1. Update `__version__` in `app/chemvas/__init__.py`.
2. Update [`CHANGELOG.md`](CHANGELOG.md) by moving unreleased items to the new version section.
3. Open a PR, merge it into `main`, and ensure `main` CI passes.
4. Tag and push the release:

```bash
git checkout main && git pull
git tag -a v0.1.0 -m "Chemvas 0.1.0"
git push origin v0.1.0
```

5. Verify the published package in a clean environment:

```bash
python -m venv .release-check
.release-check/bin/python -m pip install "chemvas==0.1.0"
.release-check/bin/chemvas --version
.release-check/bin/chemvas
```
