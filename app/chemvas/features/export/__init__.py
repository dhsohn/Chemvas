"""Public API for deterministic figure export.

Callers outside this feature import from this package, while renderer-specific
details remain private implementation modules.
"""

from .cdxml_label_bindings import (
    CDXML_LABEL_BINDINGS_VERSION_V2,
    MAX_CDXML_LABEL_BINDINGS_BYTES,
    CdxmlDocumentaryContact,
    CdxmlLabelBindings,
    authorize_documentary_contact_for_export,
    parse_cdxml_label_bindings,
    read_cdxml_label_bindings,
)
from .cdxml_roundtrip import inspect_cdxml_roundtrip, recover_native_cdxml_palette
from .cdxml_text_layout import (
    MAX_CDXML_CONSUMER_BYTES,
    CaptionGeometry,
    CdxmlTextLayoutReference,
    parse_cdxml_text_layout_reference,
    reflow_cdxml_captions,
)
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
    "CDXML_LABEL_BINDINGS_VERSION_V2",
    "DEFAULT_DPI",
    "DPI_OPTIONS",
    "EXPORT_BACKGROUNDS",
    "EXPORT_FORMATS",
    "EXPORT_SCOPES",
    "EXPORT_SIZES",
    "MAX_CDXML_CONSUMER_BYTES",
    "MAX_CDXML_LABEL_BINDINGS_BYTES",
    "POINTS_PER_INCH",
    "CaptionGeometry",
    "CdxmlDocumentaryContact",
    "CdxmlLabelBindings",
    "CdxmlTextLayoutReference",
    "ExportPlan",
    "MaximumHeightError",
    "MinimumFontSizeError",
    "authorize_documentary_contact_for_export",
    "build_export_plan",
    "default_export_path",
    "export_error_message",
    "file_filter_for_format",
    "inspect_cdxml_roundtrip",
    "is_dpi_relevant",
    "is_raster_format",
    "normalize_export_path",
    "parse_cdxml_label_bindings",
    "parse_cdxml_text_layout_reference",
    "points_for_mm",
    "read_cdxml_label_bindings",
    "recover_native_cdxml_palette",
    "reflow_cdxml_captions",
    "suffix_for_format",
    "supports_minimum_font_check",
    "svg_viewport_size_points",
]
