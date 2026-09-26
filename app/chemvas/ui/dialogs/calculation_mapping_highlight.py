from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas.graphics_items import AtomLabelItem
from chemvas.ui.canvas.pick_radius_access import atom_pick_radius_for
from chemvas.ui.selection.selection_style_access import atom_center_point_for

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Set

_REACTANT_COLOR = QColor("#0072B2")
_PRODUCT_COLOR = QColor("#D55E00")
# Palette text_faint: atoms that are not part of the mapping (unmapped, or in a
# component that sits out of the step) label in a muted gray.
_EXCLUDED_COLOR = QColor("#9B9B96")
_LABEL_Z = 39.0
# Small offset from the atom's own anchor so the id sits just above-right of the
# glyph, hugging it rather than floating out at the pick-circle corner.
_LABEL_OFFSET = 2.5


class CalculationMappingHighlighter:
    """Own the persistent atom-id labels on the canvas.

    ``show_atom_labels`` draws the stable Chemvas atom id next to every atom so
    a reader can match a table row to a spot on the drawing: reactant-tinted and
    product-tinted ids mark mapped atoms, gray ids everything else. The labels
    are non-selectable overlays; ``clear_all`` removes them when the dialog
    closes.
    """

    def __init__(self, canvas: Any) -> None:
        self._canvas = canvas
        self._label_items: list[QGraphicsItem] = []

    @property
    def canvas(self) -> Any:
        return self._canvas

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
            # Atoms outside the mapping (unmapped, or in unused or locked-out
            # components) keep a gray id label, so "not taking part" is visible
            # instead of just unlabeled.
            if atom_id in reactant_ids or atom_id in product_ids:
                continue
            self._add_id_label(scene, atom_id=atom_id, color=_EXCLUDED_COLOR)

    def show_correspondence(
        self,
        pairs: Mapping[int, int],
        reactant_ids: Set[int],
        product_ids: Set[int],
        changed_bonds: Iterable[tuple[int, int]],
        selected: int | None,
    ) -> None:
        self.clear_all()
        scene = self._scene()
        if scene is None:
            return
        # Only the inspected pair gets badges. Dense structures must remain
        # readable without a permanent label and palette entry on every atom.
        focused = selected
        if focused is None:
            return
        reverse = {product: reactant for reactant, product in pairs.items()}
        reactant = focused if focused in reactant_ids else reverse.get(focused)
        product = pairs.get(reactant) if reactant is not None else None
        number = (
            sorted(pairs).index(reactant) + 1
            if reactant is not None and reactant in pairs
            else None
        )
        labels = {}
        if reactant is not None:
            labels[reactant] = f"R {number}" if number is not None else "R ?"
        if product is not None:
            labels[product] = f"R/P {number}" if product == reactant else f"P {number}"
        elif focused in product_ids and focused not in reactant_ids:
            labels[focused] = "P ?"
        for atom_id, label in labels.items():
            color = _REACTANT_COLOR
            self._add_id_label(scene, atom_id=atom_id, color=color, label=label)
            center = atom_center_point_for(self._canvas, atom_id)
            if center is not None:
                radius = atom_pick_radius_for(self._canvas)
                ring = QGraphicsEllipseItem(
                    center.x() - radius, center.y() - radius, 2 * radius, 2 * radius
                )
                ring.setPen(QPen(color, 2.0))
                self._prepare_item(ring, z_value=_LABEL_Z - 1)
                ring.setData(0, "calculation_atom_id_label")
                scene.addItem(ring)
                self._label_items.append(ring)
        for a, b in changed_bonds:
            if a not in labels and b not in labels:
                continue
            start = atom_center_point_for(self._canvas, a)
            end = atom_center_point_for(self._canvas, b)
            if start is not None and end is not None:
                line = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
                line.setPen(QPen(QColor("#ed8a23"), 3.0))
                line.setOpacity(0.55)
                self._prepare_item(line, z_value=_LABEL_Z - 2)
                line.setData(0, "calculation_atom_id_label")
                scene.addItem(line)
                self._label_items.append(line)

    def clear_all(self) -> None:
        self._remove_items(self._label_items)

    def _remove_items(self, items: list[QGraphicsItem]) -> None:
        if not items:
            return
        scene = self._scene()
        for item in items:
            with contextlib.suppress(RuntimeError):
                if scene is not None and item.scene() is scene:
                    scene.removeItem(item)
        items.clear()

    def _add_id_label(
        self,
        scene: QGraphicsScene,
        *,
        atom_id: int,
        color: QColor,
        label: str | None = None,
        line_offset: int = 0,
    ) -> None:
        center = atom_center_point_for(self._canvas, atom_id)
        if center is None:
            return
        text = QGraphicsSimpleTextItem(str(atom_id) if label is None else label)
        text.setData(0, "calculation_atom_id_label")
        text.setData(1, atom_id)
        text.setBrush(QBrush(color))
        font = QFont()
        font.setPointSizeF(7.0)
        font.setBold(True)
        text.setFont(font)
        # Scale with the canvas so this scene-coordinate clearance remains
        # valid when the user changes zoom while the mapping dialog is open.
        clearance_top = center.y() - atom_pick_radius_for(self._canvas)
        atom_item = visible_atom_item_for(self._canvas, atom_id)
        if atom_item is not None:
            # Keep ID placement independent of output-only glyph fitting.
            bounds_getter = (
                atom_item.layout_scene_bounding_rect
                if isinstance(atom_item, AtomLabelItem)
                else getattr(atom_item, "export_scene_bounding_rect", None)
            )
            try:
                visible_bounds = bounds_getter() if callable(bounds_getter) else None
            except RuntimeError:
                visible_bounds = None
            if isinstance(visible_bounds, QRectF) and not visible_bounds.isEmpty():
                clearance_top = min(clearance_top, visible_bounds.top())
        text_bounds = text.boundingRect()
        # Horizontal placement stays tied to the atom center rather than a long
        # alias's widened hit rectangle. Vertically, clear both the painted
        # glyph and the ordinary atom pick radius.
        text.setPos(
            center.x() + _LABEL_OFFSET - text_bounds.left(),
            clearance_top
            - _LABEL_OFFSET
            - text_bounds.bottom()
            - line_offset * (text_bounds.height() + 1),
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
