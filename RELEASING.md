# Releasing Chemvas

[한국어](RELEASING.ko.md)

Chemvas publishes to [PyPI](https://pypi.org/project/chemvas/) from GitHub
Actions using **Trusted Publishing** (OIDC) — no API tokens are stored. Pushing a
`v*` tag runs [`.github/workflows/release.yml`](.github/workflows/release.yml),
which builds the sdist + wheel and uploads them.

The version is single-sourced from `chemvas.__version__`
([`app/chemvas/__init__.py`](app/chemvas/__init__.py)); `pyproject.toml` reads it
via `dynamic = ["version"]`.

## One-time setup (PyPI Trusted Publisher)

Do this once, before the first release, while the `chemvas` project does not yet
exist on PyPI:

1. Sign in to PyPI → **Your account ▸ Publishing ▸ Add a pending publisher**.
2. Fill in:
   - **PyPI Project Name:** `chemvas`
   - **Owner:** `dhsohn`
   - **Repository name:** `Chemvas`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
3. (Recommended) In the GitHub repo, create an **Environment** named `pypi`
   (Settings ▸ Environments) and add protection rules — e.g. require a reviewer,
   or restrict to the `main` branch and `v*` tags.

The `environment: pypi` and `permissions: id-token: write` in `release.yml` must
match the pending publisher above.

## Cutting a release

1. Bump `__version__` in `app/chemvas/__init__.py` (e.g. `0.1.0`).
2. In [`CHANGELOG.md`](CHANGELOG.md), rename the `## [Unreleased]` heading to
   `## [0.1.0] - YYYY-MM-DD`, start a fresh empty `## [Unreleased]` above it, and
   update the link references at the bottom.
3. Open a PR with those changes; merge once CI is green. Wait for the CI run
   triggered by the push to `main` to pass on that exact merge commit before
   tagging it. The release provenance check requires successful `main` push CI;
   the PR's CI result alone does not satisfy it.
4. Tag the merge commit on `main` and push the tag:
   ```bash
   git checkout main && git pull
   git tag -a v0.1.0 -m "Chemvas 0.1.0"
   git push origin v0.1.0
   ```
5. Watch the **Release** workflow. On success, verify the published version in a
   fresh virtual environment, from an empty directory outside the source checkout.
   Replace `0.1.0` below with the version just released; do not reuse an existing
   environment, where an unpinned install can leave an older version in place.
   ```bash
   python -m venv .release-check
   .release-check/bin/python -m pip install "chemvas==0.1.0"
   .release-check/bin/chemvas --version
   .release-check/bin/chemvas
   ```
   Confirm that the printed version matches the tag and the app opens. On
   Windows, use `.release-check\Scripts\python.exe` and
   `.release-check\Scripts\chemvas.exe`. Install `chemvas[rdkit]==0.1.0` when
   checking optional chemistry conversions as well. Upgrading ordinary user
   installations is a separate operation.

## Notes

- The tag version (`v0.1.0`) should match `__version__` (`0.1.0`). PyPI rejects
  re-uploading an existing version, so bump `__version__` for every release.
- Desktop binaries (`.app`/`.exe`/AppImage via PyInstaller — see
  [`packaging/`](packaging/)) are not published here yet; attaching them to the
  GitHub Release is a planned follow-up.
- The [Windows preparation guide](packaging/windows/README.md) provides a local
  x64 installer build and acceptance checklist. Local builds are unsigned;
  signing, clean-machine acceptance, and bundled-dependency distribution review
  must precede publishing installers.
