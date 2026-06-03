"""Render the canvas scene to a figure file (SVG / PDF / PNG / TIFF).

All formats share one path: pick the content items, hide everything transient,
switch atom labels into outline mode, then render the scene region onto a paint
device. Outlining (see ``AtomLabelItem.set_outline_mode``) means the figure does
not depend on the viewer having the label font installed, and that screen, SVG,
PDF and raster output all show identical glyphs.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Sequence

from PyQt6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QMarginsF,
    QRectF,
    QSize,
    QSizeF,
    Qt,
)
from PyQt6.QtGui import QImage, QPageSize, QPainter, QPdfWriter
from PyQt6.QtSvg import QSvgGenerator
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from ui.export_plan_logic import ExportPlan, build_export_plan

# Transient overlays that must never appear in an exported figure. Mirrors the
# exclusion set used by the clipboard copy path (``_selection_items_for_copy``).
EXPORT_EXCLUDED_KINDS = frozenset({"handle", "note_select", "selection_outline"})

POINTS_PER_INCH = 72.0
_METERS_PER_INCH = 0.0254


def collect_export_items(scene: QGraphicsScene) -> list[QGraphicsItem]:
    """Visible content items only: real content always carries a role, while
    transient overlays are either role-less (hover/preview) or in the exclusion
    set, so both are dropped."""
    items: list[QGraphicsItem] = []
    for item in scene.items():
        if not item.isVisible():
            continue
        role = item.data(0)
        if role is None or role in EXPORT_EXCLUDED_KINDS:
            continue
        items.append(item)
    return items


def item_export_bounds(item: QGraphicsItem) -> QRectF:
    bounds_getter = getattr(item, "export_scene_bounding_rect", None)
    if callable(bounds_getter):
        rect = bounds_getter()
        if isinstance(rect, QRectF):
            return QRectF(rect)
    return item.sceneBoundingRect()


def content_bounds(items: Sequence[QGraphicsItem]) -> QRectF | None:
    rect = QRectF()
    for item in items:
        item_rect = item_export_bounds(item)
        if item_rect.isNull():
            continue
        rect = QRectF(item_rect) if rect.isNull() else rect.united(item_rect)
    if rect.isNull() or rect.width() <= 0.0 or rect.height() <= 0.0:
        return None
    return rect


def _set_label_outline_mode(items: Sequence[QGraphicsItem], enabled: bool) -> list[QGraphicsItem]:
    changed: list[QGraphicsItem] = []
    for item in items:
        setter = getattr(item, "set_outline_mode", None)
        if callable(setter):
            setter(enabled)
            changed.append(item)
    return changed


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


@contextmanager
def _exported_scene(scene: QGraphicsScene, export_items: Sequence[QGraphicsItem]):
    export_set = set(export_items)
    hidden = [item for item in scene.items() if item.isVisible() and item not in export_set]
    outlined = _set_label_outline_mode(export_items, True)
    for item in hidden:
        item.setVisible(False)
    try:
        yield
    finally:
        for item in hidden:
            item.setVisible(True)
        _set_label_outline_mode(outlined, False)


def _paint_region(
    painter: QPainter,
    scene: QGraphicsScene,
    plan: ExportPlan,
    target_w: float,
    target_h: float,
    background: str,
) -> None:
    target = QRectF(0.0, 0.0, float(target_w), float(target_h))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    if background == "white":
        painter.fillRect(target, Qt.GlobalColor.white)
    source = QRectF(plan.source_x, plan.source_y, plan.source_w, plan.source_h)
    scene.render(painter, target, source)


def _export_svg(scene, path, export_items, plan, background, title) -> None:
    with _exported_scene(scene, export_items):
        generator = QSvgGenerator()
        generator.setFileName(path)
        # Render at 72 dpi so 1 SVG user unit = 1 point => physical size = out_pt.
        generator.setResolution(int(POINTS_PER_INCH))
        generator.setSize(QSize(max(1, round(plan.out_w_pt)), max(1, round(plan.out_h_pt))))
        generator.setViewBox(QRectF(0.0, 0.0, plan.out_w_pt, plan.out_h_pt))
        if title:
            generator.setTitle(title)
        generator.setDescription("Generated by Chemvas")
        painter = QPainter()
        if not painter.begin(generator):
            raise ValueError("Failed to open SVG output for writing.")
        try:
            _paint_region(painter, scene, plan, plan.out_w_pt, plan.out_h_pt, background)
        finally:
            painter.end()


def _render_svg_bytes(scene, export_items, plan, background, title) -> bytes:
    buffer_data = QByteArray()
    buffer = QBuffer(buffer_data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise ValueError("Failed to open SVG clipboard buffer.")
    try:
        with _exported_scene(scene, export_items):
            generator = QSvgGenerator()
            generator.setOutputDevice(buffer)
            generator.setResolution(int(POINTS_PER_INCH))
            generator.setSize(QSize(max(1, round(plan.out_w_pt)), max(1, round(plan.out_h_pt))))
            generator.setViewBox(QRectF(0.0, 0.0, plan.out_w_pt, plan.out_h_pt))
            if title:
                generator.setTitle(title)
            generator.setDescription("Generated by Chemvas")
            painter = QPainter()
            if not painter.begin(generator):
                raise ValueError("Failed to render SVG clipboard data.")
            try:
                _paint_region(painter, scene, plan, plan.out_w_pt, plan.out_h_pt, background)
            finally:
                painter.end()
    finally:
        buffer.close()
    return bytes(buffer_data)


def _export_pdf(scene, path, export_items, plan, resolution, background, title) -> None:
    with _exported_scene(scene, export_items):
        writer = QPdfWriter(path)
        writer.setResolution(int(resolution))
        writer.setPageSize(QPageSize(QSizeF(plan.out_w_pt, plan.out_h_pt), QPageSize.Unit.Point))
        writer.setPageMargins(QMarginsF(0.0, 0.0, 0.0, 0.0))
        if title:
            writer.setTitle(title)
        target_w = plan.out_w_pt / POINTS_PER_INCH * resolution
        target_h = plan.out_h_pt / POINTS_PER_INCH * resolution
        painter = QPainter()
        if not painter.begin(writer):
            raise ValueError("Failed to open PDF output for writing.")
        try:
            _paint_region(painter, scene, plan, target_w, target_h, background)
        finally:
            painter.end()


def _render_pdf_bytes(scene, export_items, plan, background, title) -> bytes:
    buffer_data = QByteArray()
    buffer = QBuffer(buffer_data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise ValueError("Failed to open PDF clipboard buffer.")
    try:
        with _exported_scene(scene, export_items):
            writer = QPdfWriter(buffer)
            writer.setResolution(int(POINTS_PER_INCH))
            writer.setPageSize(QPageSize(QSizeF(plan.out_w_pt, plan.out_h_pt), QPageSize.Unit.Point))
            writer.setPageMargins(QMarginsF(0.0, 0.0, 0.0, 0.0))
            if title:
                writer.setTitle(title)
            painter = QPainter()
            if not painter.begin(writer):
                raise ValueError("Failed to render PDF clipboard data.")
            try:
                _paint_region(painter, scene, plan, plan.out_w_pt, plan.out_h_pt, background)
            finally:
                painter.end()
    finally:
        buffer.close()
    return bytes(buffer_data)


def _save_tiff_with_pillow(image: QImage, path: str, dpi: int) -> None:
    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise ValueError("Pillow is required to write TIFF files.") from exc

    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width = rgba.width()
    height = rgba.height()
    data = rgba.bits()
    data.setsize(rgba.sizeInBytes())
    pil_image = Image.frombytes(
        "RGBA",
        (width, height),
        bytes(data),
        "raw",
        "RGBA",
        rgba.bytesPerLine(),
        1,
    )
    pil_image.save(path, format="TIFF", dpi=(dpi, dpi))


def _export_raster(scene, path, export_items, plan, image_format, dpi, background) -> None:
    width_px = max(1, round(plan.out_w_pt / POINTS_PER_INCH * dpi))
    height_px = max(1, round(plan.out_h_pt / POINTS_PER_INCH * dpi))
    with _exported_scene(scene, export_items):
        image = QImage(width_px, height_px, QImage.Format.Format_ARGB32_Premultiplied)
        dots_per_meter = int(round(dpi / _METERS_PER_INCH))
        image.setDotsPerMeterX(dots_per_meter)
        image.setDotsPerMeterY(dots_per_meter)
        image.fill(Qt.GlobalColor.white if background == "white" else Qt.GlobalColor.transparent)
        painter = QPainter()
        if not painter.begin(image):
            raise ValueError("Failed to render image.")
        try:
            _paint_region(painter, scene, plan, width_px, height_px, background)
        finally:
            painter.end()
        if image_format == "TIFF":
            _save_tiff_with_pillow(image, path, dpi)
            return
        if not image.save(path, image_format):
            raise ValueError(f"Failed to write {image_format} to {path}.")


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
    export_items, plan = _resolve_plan(scene, items, margin, unit_scale, target_width_pt)
    if fmt == "svg":
        _export_svg(scene, path, export_items, plan, background, title)
    elif fmt == "pdf":
        _export_pdf(scene, path, export_items, plan, dpi, background, title)
    elif fmt in ("png", "tiff"):
        _export_raster(
            scene, path, export_items, plan, "PNG" if fmt == "png" else "TIFF", dpi, background
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
    if source.isNull() or source.width() <= 0.0 or source.height() <= 0.0:
        raise ValueError("There is nothing to copy.")
    plan = ExportPlan(
        source_x=source.x(),
        source_y=source.y(),
        source_w=source.width(),
        source_h=source.height(),
        out_w_pt=source.width(),
        out_h_pt=source.height(),
    )
    return _render_svg_bytes(scene, list(items), plan, background, title)


def render_scene_to_pdf_bytes(
    scene: QGraphicsScene,
    *,
    source: QRectF,
    items: Sequence[QGraphicsItem],
    background: str = "transparent",
    title: str | None = None,
) -> bytes:
    if source.isNull() or source.width() <= 0.0 or source.height() <= 0.0:
        raise ValueError("There is nothing to copy.")
    plan = ExportPlan(
        source_x=source.x(),
        source_y=source.y(),
        source_w=source.width(),
        source_h=source.height(),
        out_w_pt=source.width(),
        out_h_pt=source.height(),
    )
    return _render_pdf_bytes(scene, list(items), plan, background, title)


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
    "render_scene_to_svg_bytes",
    "render_scene_to_svg",
]
