"""Paper dimensions shared by document authoring and desktop rendering."""

from __future__ import annotations

from decimal import Decimal

POINTS_PER_MM = 72.0 / 25.4
MIN_SHEET_MM = 10.0
MAX_SHEET_MM = 2000.0
SHEET_SIZES_MM: dict[str, tuple[float, float]] = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
    "Tabloid": (279.4, 431.8),
}
CUSTOM_SHEET_SIZE = "Custom"


def validate_custom_sheet_size(value: object) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("sheet_custom_size_mm must contain width and height in mm.")
    for dimension in value:
        if (
            isinstance(dimension, bool)
            or not isinstance(dimension, (int, float, Decimal))
            or not Decimal(str(dimension)).is_finite()
            or not MIN_SHEET_MM <= Decimal(str(dimension)) <= MAX_SHEET_MM
        ):
            raise ValueError(
                f"Custom sheet dimensions must be finite numbers from {MIN_SHEET_MM:g} to {MAX_SHEET_MM:g} mm."
            )
    return float(value[0]), float(value[1])
