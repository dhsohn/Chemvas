from __future__ import annotations


DEFAULT_SHEET_SIZE = "A4"
DEFAULT_SHEET_ORIENTATION = "landscape"
SHEET_MARGIN_PX = 80.0

SHEET_SIZE_SPECS: dict[str, tuple[float, float]] = {
    "A4": (595.0, 842.0),
}

SHEET_ORIENTATION_OPTIONS: tuple[tuple[str, str], ...] = (
    ("landscape", "Landscape"),
    ("portrait", "Portrait"),
)


def supported_sheet_sizes() -> tuple[str, ...]:
    return tuple(SHEET_SIZE_SPECS)


def supported_sheet_orientations() -> tuple[str, ...]:
    return tuple(value for value, _label in SHEET_ORIENTATION_OPTIONS)


def normalize_sheet_size(value: object) -> str:
    text = str(value or "").strip().upper()
    return text if text in SHEET_SIZE_SPECS else DEFAULT_SHEET_SIZE


def normalize_sheet_orientation(value: object) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "landscape": "landscape",
        "horizontal": "landscape",
        "portrait": "portrait",
        "vertical": "portrait",
    }
    return aliases.get(text, DEFAULT_SHEET_ORIENTATION)


def normalize_sheet_setup(size_name: object, orientation: object) -> tuple[str, str]:
    return normalize_sheet_size(size_name), normalize_sheet_orientation(orientation)


def sheet_dimensions_px(size_name: object, orientation: object) -> tuple[float, float]:
    normalized_size, normalized_orientation = normalize_sheet_setup(size_name, orientation)
    portrait_width, portrait_height = SHEET_SIZE_SPECS[normalized_size]
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
    "supported_sheet_orientations",
    "supported_sheet_sizes",
]
