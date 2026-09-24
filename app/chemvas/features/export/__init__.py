"""Public API for deterministic figure export.

Callers outside this feature import from this package, while renderer-specific
details remain private implementation modules.
"""

from .dialog import (
    DEFAULT_DPI,
    DPI_OPTIONS,
    EXPORT_BACKGROUNDS,
    EXPORT_FORMATS,
    EXPORT_SCOPES,
    EXPORT_SIZES,
    default_export_path,
    export_error_message,
    file_filter_for_format,
    is_dpi_relevant,
    is_raster_format,
    normalize_export_path,
    suffix_for_format,
    supports_minimum_font_check,
)
from .errors import MaximumHeightError, MinimumFontSizeError
from .plan import (
    POINTS_PER_INCH,
    ExportPlan,
    build_export_plan,
    points_for_mm,
    svg_viewport_size_points,
)

__all__ = [
    "DEFAULT_DPI",
    "DPI_OPTIONS",
    "EXPORT_BACKGROUNDS",
    "EXPORT_FORMATS",
    "EXPORT_SCOPES",
    "EXPORT_SIZES",
    "POINTS_PER_INCH",
    "ExportPlan",
    "MaximumHeightError",
    "MinimumFontSizeError",
    "build_export_plan",
    "default_export_path",
    "export_error_message",
    "file_filter_for_format",
    "is_dpi_relevant",
    "is_raster_format",
    "normalize_export_path",
    "points_for_mm",
    "suffix_for_format",
    "supports_minimum_font_check",
    "svg_viewport_size_points",
]
