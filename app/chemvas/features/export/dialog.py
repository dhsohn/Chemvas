"""Pure helpers for the figure-export dialog.

Format specs, DPI choices, file-filter strings and path normalization live here
(Qt-free) so they can be unit-tested; the QDialog widget assembly stays in the
document dialog module.
"""

from __future__ import annotations

import errno
from pathlib import Path

from chemvas.features.export.errors import MaximumHeightError, MinimumFontSizeError

# (label, fmt key, default suffix)
EXPORT_FORMATS: tuple[tuple[str, str, str], ...] = (
    ("Plain SVG - vector", "svg", ".svg"),
    ("PDF - vector", "pdf", ".pdf"),
    ("PNG - raster", "png", ".png"),
    ("TIFF - raster", "tiff", ".tiff"),
)

DPI_OPTIONS: tuple[int, ...] = (150, 300, 600, 1200)
DEFAULT_DPI = 300

EXPORT_SCOPES: tuple[tuple[str, str], ...] = (
    ("Whole canvas", "sheet"),
    ("Selection only", "selection"),
)

EXPORT_BACKGROUNDS: tuple[tuple[str, str], ...] = (
    ("Transparent", "transparent"),
    ("White", "white"),
)

# Physical sizing modes (see CanvasView.export_figure / build_export_plan).
EXPORT_SIZES: tuple[tuple[str, str], ...] = (
    ("Preset bond length", "bond"),
    ("Fit 1-column (84 mm)", "col1"),
    ("Fit 2-column (174 mm)", "col2"),
    ("Screen (1:1)", "screen"),
    ("Custom width (mm)", "custom"),
)

_RASTER_FORMATS = frozenset({"png", "tiff"})
_SUFFIX = {"svg": ".svg", "pdf": ".pdf", "png": ".png", "tiff": ".tiff"}
_FILTER = {
    "svg": "SVG (*.svg)",
    "pdf": "PDF (*.pdf)",
    "png": "PNG (*.png)",
    "tiff": "TIFF (*.tif *.tiff)",
}

# Every suffix this dialog can write. A typed suffix from this set names a
# format, so it is retargeted when it contradicts the chosen one; an unknown
# suffix ("scheme.v2") is a filename the user chose and is left alone.
_FORMAT_SUFFIXES: dict[str, frozenset[str]] = {
    "svg": frozenset({".svg"}),
    "pdf": frozenset({".pdf"}),
    "png": frozenset({".png"}),
    "tiff": frozenset({".tif", ".tiff"}),
}
_KNOWN_SUFFIXES = frozenset(
    suffix for suffixes in _FORMAT_SUFFIXES.values() for suffix in suffixes
)


def is_raster_format(fmt: str) -> bool:
    return fmt.lower() in _RASTER_FORMATS


def is_dpi_relevant(fmt: str) -> bool:
    """DPI affects raster size and PDF rasterization resolution; SVG ignores it."""
    fmt = fmt.lower()
    return fmt in _RASTER_FORMATS or fmt == "pdf"


def supports_minimum_font_check(fmt: str, scope: str) -> bool:
    """The native font proof currently covers whole-canvas SVG and PNG only."""
    return fmt.lower() in {"svg", "png"} and scope == "sheet"


def suffix_for_format(fmt: str) -> str:
    return _SUFFIX.get(fmt.lower(), "")


def file_filter_for_format(fmt: str) -> str:
    return f"{_FILTER.get(fmt.lower(), 'All Files (*)')};;All Files (*)"


def normalize_export_path(dialog_path: str | None, fmt: str) -> str | None:
    """Give the exported file a suffix that matches the format being written.

    A name typed with another format's suffix ("figure.pdf" while the dialog is
    on SVG) otherwise produced SVG bytes in a file every other program reads by
    its extension. Retargeting keeps the written format and the name in step;
    the caller confirms the retargeted name before replacing an existing file.
    """
    if not dialog_path:
        return None
    path = Path(dialog_path)
    suffix = suffix_for_format(fmt)
    if not suffix:
        return str(path)
    current = path.suffix.lower()
    if current in _FORMAT_SUFFIXES.get(fmt.lower(), frozenset()):
        return str(path)
    if current and current not in _KNOWN_SUFFIXES:
        return str(path)
    return str(path.with_suffix(suffix))


def default_export_path(current_file_path: str | None, fmt: str) -> str:
    if not current_file_path:
        return ""
    suffix = suffix_for_format(fmt) or ".svg"
    return str(Path(current_file_path).with_suffix(suffix))


def export_error_message(error: Exception) -> str:
    """Describe failed export limits using the controls available in the dialog."""
    if isinstance(error, MaximumHeightError):
        return (
            f"The exported figure is {error.height_mm:.2f} mm high; "
            f"the maximum is {error.maximum_mm:g} mm.\n\n"
            "Reduce the export width, or raise or turn off "
            "Limit exported height in Export Figure. "
            "No file was written or resized."
        )
    if isinstance(error, MinimumFontSizeError):
        return (
            f"The smallest visible text is {error.minimum_pt:.2f} pt; "
            f"the required minimum is {error.required_pt:g} pt.\n\n"
            "Increase the export width or the drawing's text size, or lower "
            "Minimum font size in Export Figure. "
            "No file was written or resized."
        )
    if isinstance(error, OSError):
        return _filesystem_error_message(error)
    return str(error)


def _filesystem_error_message(error: OSError) -> str:
    """Explain a failed write without the staging path the user never chose.

    Exports are staged through a temporary file next to the destination, so the
    raw OSError names a path that does not exist once the export unwinds.
    """
    if error.errno == errno.ENOENT:
        detail = "The destination folder does not exist."
    elif error.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
        detail = "You do not have permission to write there."
    elif error.errno == errno.ENOSPC:
        detail = "The disk is full."
    else:
        # An OSError raised without an errno still carries its own message, and
        # dropping it would tell the user less than the unhandled path did.
        reason = error.strerror or str(error) or "The file could not be written."
        detail = reason if reason.endswith(".") else f"{reason}."
    return f"{detail}\n\nChoose another location. No file was written."


__all__ = [
    "DEFAULT_DPI",
    "DPI_OPTIONS",
    "EXPORT_BACKGROUNDS",
    "EXPORT_FORMATS",
    "EXPORT_SCOPES",
    "EXPORT_SIZES",
    "default_export_path",
    "export_error_message",
    "file_filter_for_format",
    "is_dpi_relevant",
    "is_raster_format",
    "normalize_export_path",
    "suffix_for_format",
    "supports_minimum_font_check",
]
