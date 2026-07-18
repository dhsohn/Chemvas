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
    file_filter_for_format,
    is_dpi_relevant,
    is_raster_format,
    normalize_export_path,
    suffix_for_format,
)
from .plan import (
    MM_PER_INCH,
    POINTS_PER_INCH,
    ExportPlan,
    build_export_plan,
    points_for_mm,
)
from .scope import (
    EXPORT_EXCLUDED_KINDS,
    collect_export_items,
    content_bounds,
    export_item_closure,
    exported_scene,
    item_export_bounds,
    set_label_outline_mode,
)
from .service import (
    export_scene,
    render_scene_to_pdf_bytes,
    render_scene_to_svg,
    render_scene_to_svg_bytes,
)

__all__ = [
    "DEFAULT_DPI",
    "DPI_OPTIONS",
    "EXPORT_BACKGROUNDS",
    "EXPORT_EXCLUDED_KINDS",
    "EXPORT_FORMATS",
    "EXPORT_SCOPES",
    "EXPORT_SIZES",
    "MM_PER_INCH",
    "POINTS_PER_INCH",
    "ExportPlan",
    "build_export_plan",
    "collect_export_items",
    "content_bounds",
    "default_export_path",
    "export_item_closure",
    "export_scene",
    "exported_scene",
    "file_filter_for_format",
    "is_dpi_relevant",
    "is_raster_format",
    "item_export_bounds",
    "normalize_export_path",
    "points_for_mm",
    "render_scene_to_pdf_bytes",
    "render_scene_to_svg",
    "render_scene_to_svg_bytes",
    "set_label_outline_mode",
    "suffix_for_format",
]
