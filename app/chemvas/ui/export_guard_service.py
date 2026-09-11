"""Shared pre-render dimension limits for GUI and public CLI export."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.features.export import ExportPlan

MAX_VECTOR_DIMENSION_POINTS = 14_400.0
MAX_RASTER_DIMENSION_PIXELS = 10_000
MAX_RASTER_PIXELS = 25_000_000


def _rendered_height_points(plan: ExportPlan, output_format: str, dpi: int) -> float:
    from chemvas.features.export import (
        POINTS_PER_INCH,
        pdf_page_size,
        svg_viewport_size_points,
    )

    if output_format == "pdf":
        return float(pdf_page_size(plan).sizePoints().height())
    if output_format == "svg":
        return float(svg_viewport_size_points(plan)[1])
    if output_format in {"png", "tiff"}:
        if isinstance(dpi, bool) or not math.isfinite(dpi) or dpi <= 0:
            raise ValueError("resolution must be a positive finite number")
        return (
            max(1, round(plan.out_h_pt / POINTS_PER_INCH * dpi)) / dpi * POINTS_PER_INCH
        )
    return plan.out_h_pt


def validate_export_budget(
    plan: ExportPlan,
    *,
    output_format: str,
    dpi: int,
    max_height_mm: float | None = None,
) -> tuple[int | None, int | None]:
    """Reject over-budget output without resizing; resolve native raster dimensions."""
    from chemvas.features.export import (
        POINTS_PER_INCH,
        MaximumHeightError,
        points_for_mm,
    )

    width_points = float(plan.out_w_pt)
    height_points = float(plan.out_h_pt)
    if (
        not math.isfinite(width_points)
        or not math.isfinite(height_points)
        or width_points <= 0.0
        or height_points <= 0.0
        or width_points > math.nextafter(MAX_VECTOR_DIMENSION_POINTS, math.inf)
        or height_points > math.nextafter(MAX_VECTOR_DIMENSION_POINTS, math.inf)
    ):
        raise ValueError(
            "rendered dimensions must be positive and no larger than "
            f"{MAX_VECTOR_DIMENSION_POINTS:g} points per side"
        )
    if max_height_mm is not None:
        if (
            isinstance(max_height_mm, bool)
            or not math.isfinite(max_height_mm)
            or max_height_mm <= 0.0
        ):
            raise ValueError("maximum height must be a positive finite number")
        rendered_height = _rendered_height_points(plan, output_format, dpi)
        if rendered_height > math.nextafter(points_for_mm(max_height_mm), math.inf):
            raise MaximumHeightError(
                rendered_height / points_for_mm(1.0), max_height_mm
            )
    if output_format not in {"png", "tiff"}:
        return None, None

    if isinstance(dpi, bool) or not math.isfinite(dpi) or dpi <= 0:
        raise ValueError("resolution must be a positive finite number")
    width_pixels = max(1, round(width_points / POINTS_PER_INCH * dpi))
    height_pixels = max(1, round(height_points / POINTS_PER_INCH * dpi))
    if (
        width_pixels > MAX_RASTER_DIMENSION_PIXELS
        or height_pixels > MAX_RASTER_DIMENSION_PIXELS
        or width_pixels * height_pixels > MAX_RASTER_PIXELS
    ):
        raise ValueError(
            f"{output_format.upper()} render exceeds the "
            f"{MAX_RASTER_DIMENSION_PIXELS}-pixel side or "
            f"{MAX_RASTER_PIXELS}-pixel area limit"
        )
    return width_pixels, height_pixels


__all__ = ["validate_export_budget"]
