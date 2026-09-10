from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTransform
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
)

from chemvas.ui.graphics_items import NoSelectLineItem

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PyQt6.QtGui import QPicture

    from chemvas.features.insertion import TemplatePreviewGeometry

# Every preview ghost paints at half strength so the existing drawing stays
# readable underneath it.
PREVIEW_OPACITY = 0.5

# Above atom labels (z 3) and ring fills so the ghost is never hidden by the
# drawing it is about to join.
SMILES_PREVIEW_Z_VALUE = 10.0


def clear_scene_items(scene: QGraphicsScene, items: Sequence[QGraphicsItem]) -> None:
    # The one scene-scoped pool reset in `ui`; `ui.hover_rendering` and
    # `ui.bond_preview_renderer` delegate here and compose the empty pool
    # their own caller reassigns, as `clear_smiles_preview` below does.
    for item in items:
        with contextlib.suppress(RuntimeError):
            if item.scene() is scene:
                scene.removeItem(item)


class SmilesPreviewItem(QGraphicsItem):
    """The structure about to be inserted, replayed from the real renderer.

    The picture holds the same painter commands the canvas will issue once the
    structure is committed, so ring double bonds, atom labels and trimmed
    bonds preview exactly as they will land. Moving the ghost only moves this
    one item.
    """

    def __init__(self, picture: QPicture) -> None:
        super().__init__()
        self._picture = picture
        # One unit of slack keeps antialiased edges inside the repaint region.
        self._bounds = QRectF(picture.boundingRect()).adjusted(-1.0, -1.0, 1.0, 1.0)
        self.setZValue(SMILES_PREVIEW_Z_VALUE)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)

    def picture(self) -> QPicture:
        return self._picture

    @override
    def boundingRect(self) -> QRectF:
        return QRectF(self._bounds)

    @override
    def shape(self) -> QPainterPath:
        # Never picked: hover and click hit-testing look through the ghost
        # to the drawing underneath, as the old line-and-dot preview allowed.
        return QPainterPath()

    @override
    def paint(self, painter, option, widget=None) -> None:
        if painter is None:
            return
        # Item opacity is applied per primitive, so every bond junction and
        # label overlap would paint darker than the rest. Replay the picture
        # at full strength into a device-resolution layer and blend that once.
        world = painter.worldTransform()
        device_rect = world.mapRect(self._bounds).toAlignedRect()
        if device_rect.isEmpty():
            return
        ratio = painter.device().devicePixelRatioF()
        layer = QImage(
            device_rect.size() * ratio, QImage.Format.Format_ARGB32_Premultiplied
        )
        layer.setDevicePixelRatio(ratio)
        layer.fill(Qt.GlobalColor.transparent)
        layer_painter = QPainter(layer)
        try:
            layer_painter.setRenderHints(painter.renderHints())
            layer_painter.setWorldTransform(
                world * QTransform.fromTranslate(-device_rect.x(), -device_rect.y())
            )
            layer_painter.drawPicture(QPointF(0.0, 0.0), self._picture)
        finally:
            layer_painter.end()
        painter.save()
        try:
            painter.resetTransform()
            painter.setOpacity(painter.opacity() * PREVIEW_OPACITY)
            painter.drawImage(device_rect.topLeft(), layer)
        finally:
            painter.restore()


def add_smiles_preview_item(
    scene: QGraphicsScene, picture: QPicture
) -> SmilesPreviewItem:
    item = SmilesPreviewItem(picture)
    scene.addItem(item)
    return item


def clear_smiles_preview(
    scene: QGraphicsScene,
    items: list[QGraphicsItem],
) -> list[QGraphicsItem]:
    clear_scene_items(scene, items)
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
    return QColor(120, 120, 120, 140)
