from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from chemvas.ui.selection_style_access import (
    atom_center_point_for,
    selection_indicator_rect_for_atom_for,
)

_REACTANT_COLOR = QColor("#0072B2")
_PRODUCT_COLOR = QColor("#D55E00")
# Palette text_faint: atoms of components that sit out of the step (unused, or
# locked out by the opposite endpoint's reactive role) label in a muted gray.
_EXCLUDED_COLOR = QColor("#9B9B96")
_HIGHLIGHT_Z = 40.0
_LABEL_Z = 39.0
# Small offset from the atom's own anchor so the id sits just above-right of the
# glyph, hugging it rather than floating out at the pick-circle corner.
_LABEL_OFFSET = 2.5


class CalculationMappingHighlighter:
    """Own transient mapping markers and persistent atom-id labels on the canvas.

    Two independent layers: ``show_mapping`` draws the R/P markers for one
    selected correspondence (cleared by ``clear``), while ``show_atom_labels``
    draws the stable Chemvas atom id next to every mappable atom so a reader can
    match a table row to a spot on the drawing. Both are non-selectable overlays;
    ``clear_all`` removes everything when the dialog closes.
    """

    def __init__(self, canvas: Any) -> None:
        self._canvas = canvas
        self._mapping_items: list[QGraphicsItem] = []
        self._label_items: list[QGraphicsItem] = []

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
        )

    def show_atom_labels(
        self,
        reactant_atom_ids: Iterable[int],
        product_atom_ids: Iterable[int],
        excluded_atom_ids: Iterable[int] = (),
    ) -> None:
        self._remove_items(self._label_items)
        scene = self._scene()
        if scene is None:
            return
        reactant_ids = set(reactant_atom_ids)
        product_ids = set(product_atom_ids)
        for atom_id in sorted(reactant_ids):
            self._add_id_label(scene, atom_id=atom_id, color=_REACTANT_COLOR)
        for atom_id in sorted(product_ids):
            # A component reused on both endpoints keeps a single reactant-tinted
            # label; only product-exclusive atoms get the product tint.
            if atom_id in reactant_ids:
                continue
            self._add_id_label(scene, atom_id=atom_id, color=_PRODUCT_COLOR)
        for atom_id in sorted(set(excluded_atom_ids)):
            # Atoms sitting out of the step (unused or locked-out components)
            # keep a gray id label, so "not participating" is visible instead of
            # just unlabeled.
            if atom_id in reactant_ids or atom_id in product_ids:
                continue
            self._add_id_label(scene, atom_id=atom_id, color=_EXCLUDED_COLOR)

    def clear(self) -> None:
        self._remove_items(self._mapping_items)

    def clear_all(self) -> None:
        self._remove_items(self._mapping_items)
        self._remove_items(self._label_items)

    def _remove_items(self, items: list[QGraphicsItem]) -> None:
        if not items:
            return
        scene = self._scene()
        for item in items:
            try:
                if scene is not None and item.scene() is scene:
                    scene.removeItem(item)
            except RuntimeError:
                pass
        items.clear()

    def _add_marker(
        self,
        scene: QGraphicsScene,
        *,
        atom_id: int,
        label: str,
        color: QColor,
        pen_style: Qt.PenStyle,
        padding: float,
    ) -> None:
        # The role is carried by color and pen style alone (solid blue =
        # reactant, dashed orange = product); a floating R/P letter next to the
        # atom proved visually distracting. The label survives as an item data
        # tag for tests and tooling.
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
        self._mapping_items.append(marker)

    def _add_id_label(
        self, scene: QGraphicsScene, *, atom_id: int, color: QColor
    ) -> None:
        center = atom_center_point_for(self._canvas, atom_id)
        if center is None:
            return
        text = QGraphicsSimpleTextItem(str(atom_id))
        text.setData(0, "calculation_atom_id_label")
        text.setData(1, atom_id)
        text.setBrush(QBrush(color))
        font = QFont()
        font.setPointSizeF(7.0)
        font.setBold(True)
        text.setFont(font)
        text.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        # Anchor to the atom itself (not the pick circle, which widens to cover a
        # long label like OTs or PPh3), just above-right so the id hugs the glyph.
        text.setPos(
            center.x() + _LABEL_OFFSET,
            center.y() - text.boundingRect().height() - _LABEL_OFFSET,
        )
        self._prepare_item(text, z_value=_LABEL_Z)
        scene.addItem(text)
        self._label_items.append(text)

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
