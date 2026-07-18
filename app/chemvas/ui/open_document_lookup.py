"""Find whether a file is already open in some window.

Chemvas opens each document in its own window; without a check, opening the
same file twice would spawn a second, independent copy that could silently
diverge. This locates the existing (window, canvas) so callers can switch to it
instead. Paths are compared by absolute, case-folded key so different spellings
of the same file still match.
"""

from __future__ import annotations

import os
import sys

from chemvas.bootstrap.window_registry import open_windows
from chemvas.ui.canvas_document_metadata_state import document_file_path_for


def normalized_path_key(path: str) -> str:
    # os.path.normcase already case-folds on Windows; on macOS it is a no-op even
    # though the default volume is case-insensitive, so fold explicitly there.
    # Linux is case-sensitive and left as-is.
    key = os.path.normcase(os.path.abspath(path))
    if sys.platform == "darwin":
        key = key.casefold()
    return key


def find_open_document(
    target_path: str, *, windows=None, path_of=document_file_path_for
):
    """Return ``(window, canvas)`` already showing ``target_path``, or ``None``.

    ``windows``/``path_of`` are injectable for testing; by default it scans the
    live window registry and reads each canvas's bound file path.
    """
    target = normalized_path_key(target_path)
    for window in open_windows() if windows is None else windows:
        tab_references = getattr(window, "tab_references", None)
        if tab_references is None:
            continue
        for canvas in tab_references.all_canvases():
            path = path_of(canvas)
            if path and normalized_path_key(path) == target:
                return window, canvas
    return None


__all__ = ["find_open_document", "normalized_path_key"]
