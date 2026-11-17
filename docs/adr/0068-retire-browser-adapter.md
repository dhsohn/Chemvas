# ADR 0068: Retire the browser adapter

- Status: Accepted
- Date: 2026-11-03
- Supersedes: [ADR 0029](0029-browser-adapter.md), [ADR 0032](0032-browser-clipboard-and-drafts.md)
- Partly supersedes: [ADR 0034](0034-qt-only-distribution.md)

## Problem

The browser presentation adapter (`chemvas --ui web`,
[ADR 0029](0029-browser-adapter.md)) and its clipboard and recovery drafts
([ADR 0032](0032-browser-clipboard-and-drafts.md)) were kept in the repository
for one stated purpose: future Leaf integration
([ADR 0034](0034-qt-only-distribution.md),
[ADR 0055](0055-retire-rdkit-chemistry-provider.md),
`docs/WEB_ADAPTER.md`). They were never distributed: wheels, the sdist and frozen
bundles excluded them through a `setup.py` build hook, `MANIFEST.in`, the
PyInstaller spec excludes and `scripts/verify_dist.py` leak checks.

The maintainer decided, in the pull request that records this ADR, that Leaf
opens a drawn `.cdxml` document in the desktop application instead (double-click
through the operating system's `.cdxml` association, which the Windows installer
and the macOS bundle's `CFBundleDocumentTypes` register). The repository does not
contain Leaf's side of that integration, so this ADR records the decision rather
than evidence from Leaf.

Without that purpose the adapter is about 27,000 lines of unshipped code and tests
that every shared editing change still had to keep working: the browser module,
its drafts store, the `app/chemvas/web/` assets, a Node test suite, the
distribution-exclusion machinery, and shared-service seams whose only second
caller was the browser.

## Decision

Remove the browser adapter and everything that existed only for it:

- `chemvas/bootstrap/web_adapter.py`, `chemvas/bootstrap/web_drafts.py`,
  `app/chemvas/web/`, their Python and Node tests, and `docs/WEB_ADAPTER*.md`.
- `chemvas --ui web` now exits with status 2 and says the browser editor has been
  retired. `--ui qt` stays accepted for existing launchers; help no longer
  mentions `--ui`.
- The distribution-exclusion machinery: `setup.py` (whose only job was dropping
  the browser modules), its `MANIFEST.in` lines, the PyInstaller `excludes`, the
  browser leak patterns in `scripts/verify_dist.py` and the CI wheel-smoke
  assertions about them. The sdist's reviewed build input is `pyproject.toml`
  alone.
- Shared code used only by the browser: `capture_record_links` and
  `rebind_record_links` in `domain/document/cdxml_source.py`, and the generic
  bond geometry primitives, which return to their Qt types (`QPolygonF`,
  `QPainterPath`) now that the desktop renderer is their only producer.

Kept: the desktop-facing results of the browser work remain in effect, including
the explicit ports of `StructureBuildCommitter`, `AtomLabelService` and
`CanvasMoveController` (built with `for_canvas`), `ChemdrawTextShortcuts`, the
shared `PointLike` protocol and the CDXML binding validation. They are used by the
desktop and its tests. Qt-only distribution from ADR 0034 stays in effect; only
its browser-exclusion parts are superseded. Statements about the browser in
[ADR 0046](0046-common-native-bond-rendering.md) no longer apply.

## Verification and limits

- `make check` runs the full suite without the browser tests.
  `tests/test_application_cli.py` checks that help offers no `--ui` and that
  `--ui web` fails with the retirement message, both from the source checkout and
  from an installed layout; the CI wheel smoke checks the same on the built wheel.
- `tests/test_verify_dist.py` keeps the package-inventory, required-desktop-file
  and build-input checks; `tests/test_windows_bundle.py` checks the bundle
  analysis without excludes.
- Desktop tests that used the browser only to build a document now build it on
  the desktop canvas (`tests/test_cdxml_working_documents.py`); a browser parity
  test file was reduced to its desktop ring regression
  (`tests/test_native_ring_regressions.py`).
- Linux has no `.cdxml` desktop-file or MIME registration in this repository, so
  opening a document from Leaf by double-click there depends on the user's system
  association. This ADR does not add one.
