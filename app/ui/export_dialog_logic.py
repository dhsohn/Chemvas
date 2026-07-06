"""Pure helpers for the figure-export dialog.

Format specs, DPI choices, file-filter strings and path normalization live here
(Qt-free) so they can be unit-tested; the QDialog widget assembly stays in the
document dialog module.
"""

from __future__ import annotations

from pathlib import Path

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
)

_RASTER_FORMATS = frozenset({"png", "tiff"})
_SUFFIX = {"svg": ".svg", "pdf": ".pdf", "png": ".png", "tiff": ".tiff"}
_FILTER = {
    "svg": "SVG (*.svg)",
    "pdf": "PDF (*.pdf)",
    "png": "PNG (*.png)",
    "tiff": "TIFF (*.tif *.tiff)",
}


def is_raster_format(fmt: str) -> bool:
    return fmt.lower() in _RASTER_FORMATS


def is_dpi_relevant(fmt: str) -> bool:
    """DPI affects raster size and PDF rasterization resolution; SVG ignores it."""
    fmt = fmt.lower()
    return fmt in _RASTER_FORMATS or fmt == "pdf"


def suffix_for_format(fmt: str) -> str:
    return _SUFFIX.get(fmt.lower(), "")


def file_filter_for_format(fmt: str) -> str:
    return f"{_FILTER.get(fmt.lower(), 'All Files (*)')};;All Files (*)"


def normalize_export_path(dialog_path: str | None, fmt: str) -> str | None:
    if not dialog_path:
        return None
    path = Path(dialog_path)
    if path.suffix:
        return str(path)
    suffix = suffix_for_format(fmt)
    return str(path.with_suffix(suffix)) if suffix else str(path)


def default_export_path(current_file_path: str | None, fmt: str) -> str:
    if not current_file_path:
        return ""
    suffix = suffix_for_format(fmt) or ".svg"
    return str(Path(current_file_path).with_suffix(suffix))


__all__ = [
    "DEFAULT_DPI",
    "DPI_OPTIONS",
    "EXPORT_BACKGROUNDS",
    "EXPORT_FORMATS",
    "EXPORT_SCOPES",
    "EXPORT_SIZES",
    "default_export_path",
    "file_filter_for_format",
    "is_dpi_relevant",
    "is_raster_format",
    "normalize_export_path",
    "suffix_for_format",
]
