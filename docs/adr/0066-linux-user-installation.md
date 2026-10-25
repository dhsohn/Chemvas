# ADR 0066: Linux per-user frozen installation

- Status: Accepted
- Date: 2026-10-25

## Problem

[ADR 0065](0065-three-platform-release-acceptance.md) requires a standalone Linux
package with desktop integration. The previous tar contained only a frozen
binary tree; manual desktop registration assumed an executable already on PATH.
The shared spec also copied upstream distribution notices only on Windows.

## Decision

Copy PyQt6/Pillow distribution metadata recursively on every platform. Build the
Linux archive using standalone CPython; a Conda candidate failed document parsing
because its pyexpat required a symbol absent from the bundled expat library.

Ship one Bash installer with the frozen bundle and desktop assets. It owns a
reserved `$XDG_DATA_HOME/chemvas` directory, a user-bin symlink and three desktop
integration files. It refuses existing paths, retains a removal entry point and
receipt, and serializes install/remove operations using a directory lock.
Removal deletes only the owned payload and unchanged integration entries; it
preserves documents and settings outside that reserved directory. Updating means
closing the app, removing the owned installation and installing the new package.
It does not change default MIME handlers or require sudo/Python at installation.

## Verification and limits

`tests/test_linux_install.py` exercises isolated installation, executable launch,
removal after the downloaded package is gone, conflicting files, symlink-root
refusal, replaced registration preservation, path quoting and reinstall. The
bundle contract tests require metadata on macOS and Linux as well as Windows.
Real rebuilt artifacts require separate notice inventory and CLI probes.

The installer depends on Bash, core utilities, shared-mime-info and
desktop-file-utils. A stale lock after forced termination requires checking for
an active installer and removing the empty lock. This is not an atomic updater.
The application directory is reserved; it is not a document storage location.
WSL tests do not establish Ubuntu GNOME Wayland/X11 acceptance. License file
inclusion does not establish redistribution permission, signing or notarization.
