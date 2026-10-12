from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
)

from chemvas.features.hover import PREVIEW_COLOR_RGBA, PREVIEW_OPACITY
from chemvas.ui.canvas.graphics_items import NoSelectLineItem

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chemvas.features.insertion import TemplatePreviewGeometry

# Every preview ghost paints at half strength so the existing drawing stays
# readable underneath it.


def clear_scene_items(
    scene: QGraphicsScene, items: Sequence[QGraphicsItem]
) -> list[QGraphicsItem]:
    """The one scene-scoped pool reset; returns the empty pool to reassign."""
    for item in items:
        with contextlib.suppress(RuntimeError):
            if item.scene() is scene:
                scene.removeItem(item)
    return []


def clear_template_preview(
    scene: QGraphicsScene,
    items: list[QGraphicsItem],
) -> tuple[list[QGraphicsItem], list[QGraphicsLineItem], list[QGraphicsEllipseItem]]:
    clear_scene_items(scene, items)
    return [], [], []


def apply_template_preview_geometry(
    scene: QGraphicsScene,
    geometry: TemplatePreviewGeometry,
    *,
    base_pen: QPen,
    existing_items: list[QGraphicsItem],
    existing_lines: list[QGraphicsLineItem],
    existing_dots: list[QGraphicsEllipseItem],
    action: str,
) -> tuple[list[QGraphicsItem], list[QGraphicsLineItem], list[QGraphicsEllipseItem]]:
    if action == "update" and _update_template_preview_geometry(
        geometry, existing_lines, existing_dots
    ):
        return existing_items, existing_lines, existing_dots
    empty_items, _, _ = clear_template_preview(scene, existing_items)
    return _build_template_preview_geometry(
        scene, geometry, base_pen=base_pen, existing_items=empty_items
    )


def _build_template_preview_geometry(
    scene: QGraphicsScene,
    geometry: TemplatePreviewGeometry,
    *,
    base_pen: QPen,
    existing_items: list[QGraphicsItem],
) -> tuple[list[QGraphicsItem], list[QGraphicsLineItem], list[QGraphicsEllipseItem]]:
    color = preview_color()
    items = list(existing_items)
    lines: list[QGraphicsLineItem] = []
    dots: list[QGraphicsEllipseItem] = []
    for x1, y1, x2, y2 in geometry.line_segments:
        line = NoSelectLineItem(x1, y1, x2, y2)
        line.setPen(preview_pen(base_pen, color))
        line.setOpacity(PREVIEW_OPACITY)
        scene.addItem(line)
        lines.append(line)
        items.append(line)
    for x, y, width, height in geometry.dot_rects:
        dot = QGraphicsEllipseItem(x, y, width, height)
        dot.setBrush(color)
        dot.setPen(QPen(Qt.PenStyle.NoPen))
        dot.setOpacity(PREVIEW_OPACITY)
        scene.addItem(dot)
        dots.append(dot)
        items.append(dot)
    return items, lines, dots


def _update_template_preview_geometry(
    geometry: TemplatePreviewGeometry,
    lines: list[QGraphicsLineItem],
    dots: list[QGraphicsEllipseItem],
) -> bool:
    if len(lines) != len(geometry.line_segments) or len(dots) != len(
        geometry.dot_rects
    ):
        return False
    for line, segment in zip(lines, geometry.line_segments, strict=False):
        line.setLine(*segment)
    for dot, rect in zip(dots, geometry.dot_rects, strict=False):
        dot.setRect(*rect)
    return True


def preview_pen(base_pen: QPen, color: QColor) -> QPen:
    pen = QPen(base_pen)
    pen.setColor(color)
    return pen


def preview_color() -> QColor:
    return QColor(*PREVIEW_COLOR_RGBA)
