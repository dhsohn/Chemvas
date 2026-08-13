from __future__ import annotations

from typing import Any


def file_format_version_for(canvas: Any) -> int:
    version = canvas.FILE_FORMAT_VERSION
    if type(version) is not int:
        raise TypeError("Canvas file format version must be an integer.")
    return version


def clipboard_selection_mime_for(canvas: Any) -> str:
    return str(canvas.CLIPBOARD_SELECTION_MIME)


def clipboard_selection_version_for(canvas: Any) -> int:
    version = canvas.CLIPBOARD_SELECTION_VERSION
    if type(version) is not int:
        raise TypeError("Clipboard selection version must be an integer.")
    return version


__all__ = [
    "clipboard_selection_mime_for",
    "clipboard_selection_version_for",
    "file_format_version_for",
]
