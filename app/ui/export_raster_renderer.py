from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from ui.export_painting import METERS_PER_INCH, POINTS_PER_INCH, paint_scene_region
from ui.export_plan_logic import ExportPlan
from ui.export_scene_scope import exported_scene


def save_tiff_with_pillow(image: QImage, path: str, dpi: int) -> None:
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
        bytes(cast(Any, data)),
        "raw",
        "RGBA",
        rgba.bytesPerLine(),
        1,
    )
    pil_image.save(path, format="TIFF", dpi=(dpi, dpi))


def export_raster_file(
    scene: QGraphicsScene,
    path: str,
    export_items: Sequence[QGraphicsItem],
    plan: ExportPlan,
    image_format: str,
    dpi: int,
    background: str,
) -> None:
    width_px = max(1, round(plan.out_w_pt / POINTS_PER_INCH * dpi))
    height_px = max(1, round(plan.out_h_pt / POINTS_PER_INCH * dpi))
    with exported_scene(scene, export_items):
        image = QImage(width_px, height_px, QImage.Format.Format_ARGB32_Premultiplied)
        dots_per_meter = round(dpi / METERS_PER_INCH)
        image.setDotsPerMeterX(dots_per_meter)
        image.setDotsPerMeterY(dots_per_meter)
        image.fill(Qt.GlobalColor.white if background == "white" else Qt.GlobalColor.transparent)
        painter = QPainter()
        if not painter.begin(image):
            raise ValueError("Failed to render image.")
        try:
            paint_scene_region(painter, scene, plan, width_px, height_px, background)
        finally:
            painter.end()
        if image_format == "TIFF":
            save_tiff_with_pillow(image, path, dpi)
            return
        if not image.save(path, image_format):
            raise ValueError(f"Failed to write {image_format} to {path}.")


__all__ = ["export_raster_file", "save_tiff_with_pillow"]
