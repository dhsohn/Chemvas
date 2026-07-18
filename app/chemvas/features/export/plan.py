"""Pure geometry for figure export.

Given the bounding box of the content to export, compute the padded source
rectangle (in scene coordinates) and the physical output size in points.
``unit_scale`` is points-per-scene-unit: it maps the on-screen px geometry to a
deterministic physical size, independent of the current zoom. Kept Qt-free so
the sizing math is unit-testable without a QApplication.

The output is expressed in PostScript points (1/72 inch). Each sink turns that
into its own units: SVG renders at 72 dpi so 1 user unit = 1 pt; PDF uses a page
sized in points; raster multiplies by dpi/72 to get pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4


@dataclass(frozen=True)
class ExportPlan:
    # Source rectangle in scene coordinates (what scene.render reads).
    source_x: float
    source_y: float
    source_w: float
    source_h: float
    # Physical output size in points.
    out_w_pt: float
    out_h_pt: float


def points_for_mm(mm: float) -> float:
    return mm / MM_PER_INCH * POINTS_PER_INCH


def build_export_plan(
    content_x: float,
    content_y: float,
    content_w: float,
    content_h: float,
    *,
    margin: float,
    unit_scale: float = 1.0,
    target_width_pt: float | None = None,
) -> ExportPlan | None:
    """Return an :class:`ExportPlan`, or ``None`` when there is no content.

    ``margin`` is added symmetrically around the content (scene units).
    ``unit_scale`` is points per scene unit. ``target_width_pt``, when given,
    overrides ``unit_scale`` so the padded width maps exactly to that physical
    width (used for journal column fitting).
    """
    if content_w <= 0.0 or content_h <= 0.0:
        return None
    pad = max(0.0, float(margin))
    source_w = content_w + 2.0 * pad
    source_h = content_h + 2.0 * pad
    if target_width_pt is not None and target_width_pt > 0.0:
        scale = target_width_pt / source_w
    else:
        scale = max(1e-6, float(unit_scale))
    return ExportPlan(
        source_x=content_x - pad,
        source_y=content_y - pad,
        source_w=source_w,
        source_h=source_h,
        out_w_pt=source_w * scale,
        out_h_pt=source_h * scale,
    )


__all__ = [
    "MM_PER_INCH",
    "POINTS_PER_INCH",
    "ExportPlan",
    "build_export_plan",
    "points_for_mm",
]
