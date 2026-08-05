from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from chemvas.ui.selection_style_access import selection_indicator_rect_for_atom_for

_REACTANT_COLOR = QColor("#0072B2")
_PRODUCT_COLOR = QColor("#D55E00")
_HIGHLIGHT_Z = 40.0


class CalculationMappingHighlighter:
    """Own transient, non-selectable canvas markers for one atom mapping."""

    def __init__(self, canvas: Any) -> None:
        self._canvas = canvas
        self._items: list[QGraphicsItem] = []

    @property
    def canvas(self) -> Any:
        return self._canvas

    def show_mapping(
        self,
        reactant_atom_id: int,
        product_atom_id: int | None,
    ) -> None:
        self.clear()
        scene = self._scene()
        if scene is None:
            return
        same_atom = product_atom_id == reactant_atom_id
        self._add_marker(
            scene,
            atom_id=reactant_atom_id,
            label="R",
            color=_REACTANT_COLOR,
            pen_style=Qt.PenStyle.SolidLine,
            padding=2.0,
            label_side="left",
        )
        if product_atom_id is None:
            return
        self._add_marker(
            scene,
            atom_id=product_atom_id,
            label="P",
            color=_PRODUCT_COLOR,
            pen_style=Qt.PenStyle.DashLine,
            padding=5.0 if same_atom else 2.0,
            label_side="right" if same_atom else "left",
        )

    def clear(self) -> None:
        if not self._items:
            return
        scene = self._scene()
        for item in self._items:
            try:
                if scene is not None and item.scene() is scene:
                    scene.removeItem(item)
            except RuntimeError:
                pass
        self._items.clear()

    def _add_marker(
        self,
        scene: QGraphicsScene,
        *,
        atom_id: int,
        label: str,
        color: QColor,
        pen_style: Qt.PenStyle,
        padding: float,
        label_side: str,
    ) -> None:
        rect = selection_indicator_rect_for_atom_for(self._canvas, atom_id)
        if rect is None:
            return
        marker_rect = rect.adjusted(-padding, -padding, padding, padding)
        path = QPainterPath()
        corner_radius = min(marker_rect.width(), marker_rect.height()) / 2.0
        path.addRoundedRect(marker_rect, corner_radius, corner_radius)
        marker = QGraphicsPathItem(path)
        marker.setData(0, "calculation_mapping_highlight")
        marker.setData(1, label)
        pen = QPen(color)
        pen.setStyle(pen_style)
        pen.setWidthF(2.0)
        pen.setCosmetic(True)
        marker.setPen(pen)
        marker.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._prepare_item(marker, z_value=_HIGHLIGHT_Z)
        scene.addItem(marker)
        self._items.append(marker)

        text = QGraphicsSimpleTextItem(label)
        text.setData(0, "calculation_mapping_highlight")
        text.setData(1, label)
        text.setBrush(QBrush(color))
        font = QFont()
        font.setPointSizeF(8.0)
        font.setBold(True)
        text.setFont(font)
        text.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        text_rect = text.boundingRect()
        label_x = (
            marker_rect.right() - text_rect.width()
            if label_side == "right"
            else marker_rect.left()
        )
        text.setPos(label_x, marker_rect.top() - text_rect.height())
        self._prepare_item(text, z_value=_HIGHLIGHT_Z + 1.0)
        scene.addItem(text)
        self._items.append(text)

    @staticmethod
    def _prepare_item(item: QGraphicsItem, *, z_value: float) -> None:
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        item.setZValue(z_value)

    def _scene(self) -> QGraphicsScene | None:
        try:
            scene = self._canvas.scene()
        except (AttributeError, RuntimeError):
            return None
        return scene if isinstance(scene, QGraphicsScene) else None


__all__ = ["CalculationMappingHighlighter"]
