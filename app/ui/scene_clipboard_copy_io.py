from __future__ import annotations

import logging
from collections.abc import Sequence

from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QGraphicsItem

from ui.export_render_service import content_bounds
from ui.scene_clipboard_access import (
    render_canvas_scene_region,
    render_canvas_selection_vector_bytes,
)
from ui.scene_clipboard_transaction_logic import ClipboardCopyPlan

logger = logging.getLogger(__name__)

CLIPBOARD_SVG_MIME = "image/svg+xml"
CLIPBOARD_PDF_MIME = "application/pdf"


def render_clipboard_raster_image(canvas, plan: ClipboardCopyPlan) -> QImage:
    image = QImage(plan.image_width, plan.image_height, QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(plan.scale)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    try:
        render_canvas_scene_region(canvas, painter, source=plan.source)
    finally:
        painter.end()
    return image


def set_vector_clipboard_data(
    mime_data: QMimeData,
    *,
    canvas,
    items: Sequence[QGraphicsItem],
    bond_line_width: float,
) -> None:
    source = content_bounds(items)
    if source is None or source.width() <= 0.0 or source.height() <= 0.0:
        return
    pad = max(2.0, bond_line_width * 2.0)
    source = source.adjusted(-pad, -pad, pad, pad)
    try:
        svg_data, pdf_data = render_canvas_selection_vector_bytes(
            canvas,
            source=source,
            items=items,
            title="Chemvas selection",
        )
    except Exception:
        # The raster image is already on the clipboard; vector flavors are a
        # best-effort enhancement for Illustrator/Office. Log for debugging
        # paste-fidelity issues rather than failing the whole copy.
        logger.debug("Vector clipboard rendering (SVG/PDF) failed; raster only.", exc_info=True)
        return
    if svg_data:
        mime_data.setData(CLIPBOARD_SVG_MIME, svg_data)
    if pdf_data:
        mime_data.setData(CLIPBOARD_PDF_MIME, pdf_data)


def build_clipboard_mime_data(
    canvas,
    *,
    items: Sequence[QGraphicsItem],
    plan: ClipboardCopyPlan,
    payload_mime_type: str,
    bond_line_width: float,
) -> QMimeData:
    mime_data = QMimeData()
    mime_data.setImageData(render_clipboard_raster_image(canvas, plan))
    set_vector_clipboard_data(
        mime_data,
        canvas=canvas,
        items=items,
        bond_line_width=bond_line_width,
    )
    if plan.payload_json is not None:
        mime_data.setData(payload_mime_type, plan.payload_json.encode("utf-8"))
    return mime_data


__all__ = [
    "CLIPBOARD_PDF_MIME",
    "CLIPBOARD_SVG_MIME",
    "build_clipboard_mime_data",
    "render_clipboard_raster_image",
    "set_vector_clipboard_data",
]
