from __future__ import annotations

from chemvas.domain.document.sheet import (
    CUSTOM_SHEET_SIZE,
    POINTS_PER_MM,
    SHEET_SIZES_MM,
    validate_custom_sheet_size,
)

DEFAULT_SHEET_SIZE = "A4"
DEFAULT_SHEET_ORIENTATION = "landscape"
SHEET_MARGIN_PX = 80.0

SHEET_ORIENTATION_OPTIONS: tuple[tuple[str, str], ...] = (
    ("landscape", "Landscape"),
    ("portrait", "Portrait"),
)


def supported_sheet_sizes() -> tuple[str, ...]:
    return (*SHEET_SIZES_MM, CUSTOM_SHEET_SIZE)


def normalize_sheet_size(value: object) -> str:
    text = str(value or "").strip().upper()
    return next(
        (name for name in supported_sheet_sizes() if name.upper() == text),
        DEFAULT_SHEET_SIZE,
    )


def normalize_sheet_orientation(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in ("landscape", "portrait") else DEFAULT_SHEET_ORIENTATION


def normalize_sheet_setup(
    size_name: object,
    orientation: object,
    custom_size_mm: object = None,
) -> tuple[str, str, tuple[float, float] | None]:
    size = normalize_sheet_size(size_name)
    custom = (
        validate_custom_sheet_size(custom_size_mm)
        if size == CUSTOM_SHEET_SIZE
        else None
    )
    return size, normalize_sheet_orientation(orientation), custom


def sheet_dimensions_px(
    size_name: object,
    orientation: object,
    custom_size_mm: tuple[float, float] | None = None,
) -> tuple[float, float]:
    normalized_size, normalized_orientation, custom = normalize_sheet_setup(
        size_name, orientation, custom_size_mm
    )
    if custom is not None:
        width, height = custom
        return width * POINTS_PER_MM, height * POINTS_PER_MM
    width_mm, height_mm = SHEET_SIZES_MM[normalized_size]
    portrait_width, portrait_height = (
        round(width_mm * POINTS_PER_MM),
        round(height_mm * POINTS_PER_MM),
    )
    if normalized_orientation == "landscape":
        return portrait_height, portrait_width
    return portrait_width, portrait_height


__all__ = [
    "DEFAULT_SHEET_ORIENTATION",
    "DEFAULT_SHEET_SIZE",
    "SHEET_MARGIN_PX",
    "SHEET_ORIENTATION_OPTIONS",
    "normalize_sheet_orientation",
    "normalize_sheet_setup",
    "normalize_sheet_size",
    "sheet_dimensions_px",
    "supported_sheet_sizes",
]
