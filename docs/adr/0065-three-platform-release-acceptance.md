# ADR 0065: Three-platform desktop release acceptance

- Status: Accepted
- Date: 2026-10-25
- Extends: [ADR 0061](0061-local-platform-validation.md)

## Problem

The [0.27.1 release](https://github.com/dhsohn/Chemvas/releases/tag/v0.27.1)
offers a Python installation and reports macOS checks, but leaves native
Windows/Linux GUI and frozen bundles untested. Existing
[packaging inputs](../../packaging/README.md) are build preparation, not evidence
that another researcher can install and use the application.

## Decision

The first stable desktop release uses one acceptance standard across three OS
families. [Desktop release acceptance](../RELEASE_ACCEPTANCE.md) owns the target
versions, architectures, deliverable formats and required checks. Each named
Windows version and Linux display session must pass. A missing platform result
cannot be replaced by headless tests or a result from another OS.

The initial targets are Windows 11 25H2 and 26H2 x64 (per-user EXE), macOS 26
arm64 (an application in a DMG), and Ubuntu 24.04 LTS x86-64 with GNOME Wayland
and X11 (a standalone tar.gz with user desktop integration). These are release
targets; this decision does not certify an artifact or change runtime checks,
the Python 3.12 minimum, or the existing PyPI installation path.

The bounded matrix keeps native validation achievable. Other OS releases,
architectures and Linux distributions remain outside this release's certification
matrix, without being actively blocked. Expanding the matrix requires its own
native acceptance evidence. Qt's [platform documentation](https://doc.qt.io/qt-6/supported-platforms.html)
is a dependency reference, not a substitute for testing Chemvas's resolved bundle.

[Public synthetic documents](../../examples/release-validation/README.md) supply
repeatable drawing cases with explicit expected results. Hand-authored native
CDXML exercises the native reader; it does not claim ChemDraw provenance. Actual
external-editor exchange remains a separate recorded check.

## Verification and limits

Local `make check`, installed-bundle GUI checks and fresh-user installation tests
serve different purposes. The existing quick GitHub CI stays unchanged. Each
release records its commit, artifact hashes, environment, results and limitations;
only tested artifacts are published.

The fixture tests check required content and save/reopen preservation. Manual
checks cover input, Undo/Redo, recovery, original-file retention, manuscript
insertion and installation/update/removal. Native release acceptance is pending
until those results exist for every target. No new application features, automatic
updater, chemistry backend or additional file format are part of this decision.
