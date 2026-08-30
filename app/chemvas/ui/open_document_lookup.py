"""Find whether a file is already open in some window.

Chemvas opens each document in its own window; without a check, opening the
same file twice would spawn a second, independent copy that could silently
diverge. This locates the existing (window, canvas) so callers can switch to it
instead. Existing paths are compared by filesystem identity, so symlink and
hard-link aliases still resolve to the same live document. Paths that do not
exist yet fall back to resolved, platform-normalized keys for Save As checks.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from chemvas.bootstrap.window_registry import open_windows
from chemvas.ui.canvas_document_metadata_state import document_file_path_for


def resolved_document_path(path: str) -> str:
    """Return an absolute path with symlinked parents and leafs resolved.

    ``realpath`` also gives a stable destination for a not-yet-created Save As
    file whose parent directory is reached through a symlink.
    """
    return os.path.realpath(os.path.abspath(path))


def normalized_path_key(path: str) -> str:
    """Return the lexical fallback key used when a path does not exist."""
    key = os.path.normcase(resolved_document_path(path))
    if sys.platform == "darwin" and _path_is_on_case_insensitive_volume(key):
        return key.casefold()
    return key


def _path_is_on_case_insensitive_volume(path: str) -> bool:
    """Probe the nearest existing ancestor without assuming all macOS volumes."""
    current = Path(path)
    while not current.exists() and current != current.parent:
        current = current.parent
    try:
        device = current.stat().st_dev
    except OSError:
        return False
    while current != current.parent:
        parent = current.parent
        try:
            if parent.stat().st_dev != device:
                # Testing the mount-point spelling would measure the parent
                # filesystem, not the volume that will hold ``path``.
                return False
        except OSError:
            return False
        variant = _case_variant(current.name)
        if variant is not None:
            try:
                return os.path.samefile(current, current.with_name(variant))
            except OSError:
                # A missing variant proves case sensitivity; every other error
                # is unknown and must not collapse two possible document names.
                return False
        current = parent
    return False


def _case_variant(name: str) -> str | None:
    for index, char in enumerate(name):
        if "a" <= char <= "z":
            return f"{name[:index]}{char.upper()}{name[index + 1 :]}"
        if "A" <= char <= "Z":
            return f"{name[:index]}{char.lower()}{name[index + 1 :]}"
    return None


def document_path_has_multiple_links(path: str) -> bool:
    """Whether atomic replacement would split an existing hard-link identity."""
    try:
        return os.stat(resolved_document_path(path)).st_nlink > 1
    except OSError:
        return False


def paths_refer_to_same_document(left: str, right: str) -> bool:
    """Compare physical identity when possible, with a creation-path fallback."""
    try:
        return os.path.samefile(left, right)
    except (OSError, ValueError):
        return normalized_path_key(left) == normalized_path_key(right)


def find_open_document(
    target_path: str,
    *,
    windows=None,
    path_of=document_file_path_for,
    exclude_canvas=None,
):
    """Return ``(window, canvas)`` already showing ``target_path``, or ``None``.

    ``windows``/``path_of`` are injectable for testing; by default it scans the
    live window registry and reads each canvas's bound file path.
    """
    for window in open_windows() if windows is None else windows:
        tab_references = getattr(window, "tab_references", None)
        if tab_references is None:
            continue
        for canvas in tab_references.all_canvases():
            if canvas is exclude_canvas:
                continue
            path = path_of(canvas)
            if path and paths_refer_to_same_document(path, target_path):
                return window, canvas
    return None


__all__ = [
    "document_path_has_multiple_links",
    "find_open_document",
    "normalized_path_key",
    "paths_refer_to_same_document",
    "resolved_document_path",
]
