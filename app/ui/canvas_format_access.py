from __future__ import annotations

from typing import Any


def file_format_version_for(canvas: Any) -> int:
    return int(canvas.FILE_FORMAT_VERSION)


def clipboard_selection_mime_for(canvas: Any) -> str:
    return str(canvas.CLIPBOARD_SELECTION_MIME)


def clipboard_selection_version_for(canvas: Any) -> int:
    return int(canvas.CLIPBOARD_SELECTION_VERSION)


__all__ = [
    "clipboard_selection_mime_for",
    "clipboard_selection_version_for",
    "file_format_version_for",
]
