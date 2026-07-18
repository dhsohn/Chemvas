"""Render the canvas scene to a figure file (SVG / PDF / PNG / TIFF).

All formats share one path: pick the content items, hide everything transient,
switch atom labels into outline mode, then render the scene region onto a paint
device. Outlining (see ``AtomLabelItem.set_outline_mode``) means the figure does
not depend on the viewer having the label font installed, and that screen, SVG,
PDF and raster output all show identical glyphs.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from .plan import ExportPlan, build_export_plan
from .raster import export_raster_file
from .scope import (
    EXPORT_EXCLUDED_KINDS,
    collect_export_items,
    content_bounds,
    item_export_bounds,
)
from .vector import (
    export_pdf_file,
    export_svg_file,
    render_pdf_bytes,
    render_svg_bytes,
)


def _resolve_plan(
    scene: QGraphicsScene,
    items: Sequence[QGraphicsItem] | None,
    margin: float,
    unit_scale: float,
    target_width_pt: float | None,
) -> tuple[list[QGraphicsItem], ExportPlan]:
    export_items = list(items) if items is not None else collect_export_items(scene)
    bounds = content_bounds(export_items)
    if bounds is None:
        raise ValueError("There is nothing to export.")
    plan = build_export_plan(
        bounds.x(),
        bounds.y(),
        bounds.width(),
        bounds.height(),
        margin=margin,
        unit_scale=unit_scale,
        target_width_pt=target_width_pt,
    )
    if plan is None:
        raise ValueError("There is nothing to export.")
    return export_items, plan


def _plan_for_copy_source(source: QRectF) -> ExportPlan:
    if source.isNull() or source.width() <= 0.0 or source.height() <= 0.0:
        raise ValueError("There is nothing to copy.")
    return ExportPlan(
        source_x=source.x(),
        source_y=source.y(),
        source_w=source.width(),
        source_h=source.height(),
        out_w_pt=source.width(),
        out_h_pt=source.height(),
    )


def export_scene(
    scene: QGraphicsScene,
    path: str,
    *,
    fmt: str,
    items: Sequence[QGraphicsItem] | None = None,
    margin: float,
    dpi: int = 300,
    background: str = "transparent",
    title: str | None = None,
    unit_scale: float = 1.0,
    target_width_pt: float | None = None,
) -> ExportPlan:
    """Export the scene content to ``path`` in ``fmt`` (svg/pdf/png/tiff).

    ``unit_scale`` (points per scene unit) or ``target_width_pt`` (fit the figure
    to a physical width) set the deterministic output size. Raises ``ValueError``
    for empty content, an unsupported format, or an output device that cannot be
    opened.
    """
    fmt = (fmt or "").lower()
    export_items, plan = _resolve_plan(
        scene, items, margin, unit_scale, target_width_pt
    )
    if fmt == "svg":
        export_svg_file(scene, path, export_items, plan, background, title)
    elif fmt == "pdf":
        export_pdf_file(scene, path, export_items, plan, dpi, background, title)
    elif fmt in ("png", "tiff"):
        image_format = "PNG" if fmt == "png" else "TIFF"
        export_raster_file(
            scene, path, export_items, plan, image_format, dpi, background
        )
    else:
        raise ValueError(f"Unsupported export format: {fmt!r}")
    return plan


def render_scene_to_svg_bytes(
    scene: QGraphicsScene,
    *,
    source: QRectF,
    items: Sequence[QGraphicsItem],
    background: str = "transparent",
    title: str | None = None,
) -> bytes:
    return render_svg_bytes(
        scene, list(items), _plan_for_copy_source(source), background, title
    )


def render_scene_to_pdf_bytes(
    scene: QGraphicsScene,
    *,
    source: QRectF,
    items: Sequence[QGraphicsItem],
    background: str = "transparent",
    title: str | None = None,
) -> bytes:
    return render_pdf_bytes(
        scene, list(items), _plan_for_copy_source(source), background, title
    )


def render_scene_to_svg(
    scene: QGraphicsScene,
    path: str,
    *,
    margin: float,
    title: str | None = None,
    items: Sequence[QGraphicsItem] | None = None,
    background: str = "transparent",
    unit_scale: float = 1.0,
    target_width_pt: float | None = None,
) -> ExportPlan:
    """Backwards-compatible SVG entry point used by tests and callers."""
    return export_scene(
        scene,
        path,
        fmt="svg",
        items=items,
        margin=margin,
        background=background,
        title=title,
        unit_scale=unit_scale,
        target_width_pt=target_width_pt,
    )


__all__ = [
    "EXPORT_EXCLUDED_KINDS",
    "collect_export_items",
    "content_bounds",
    "export_scene",
    "item_export_bounds",
    "render_scene_to_pdf_bytes",
    "render_scene_to_svg",
    "render_scene_to_svg_bytes",
]
