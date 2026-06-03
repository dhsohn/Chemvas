from __future__ import annotations

from collections.abc import Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
)

from ui.graphics_items import NoSelectLineItem
from ui.smiles_insert_logic import SmilesPreviewGeometry, build_smiles_preview_snapshot
from ui.template_preview_logic import TemplatePreviewGeometry


def clear_scene_items(scene: QGraphicsScene, items: list[QGraphicsItem]) -> None:
    for item in items:
        try:
            if item.scene() is scene:
                scene.removeItem(item)
        except RuntimeError:
            pass


def clear_smiles_preview(
    scene: QGraphicsScene,
    items: list[QGraphicsItem],
) -> tuple[list[QGraphicsItem], dict[int, list[QGraphicsItem]], dict[int, QGraphicsEllipseItem]]:
    clear_scene_items(scene, items)
    return [], {}, {}


def smiles_preview_snapshot(
    bond_items: Mapping[int, list[QGraphicsItem]],
    atom_items: Mapping[int, QGraphicsEllipseItem],
):
    return build_smiles_preview_snapshot(
        {bond_id: len(items) for bond_id, items in bond_items.items()},
        atom_items.keys(),
    )


def apply_smiles_preview_geometry(
    scene: QGraphicsScene,
    geometry: SmilesPreviewGeometry,
    *,
    base_pen: QPen,
    existing_items: list[QGraphicsItem],
    existing_bond_items: dict[int, list[QGraphicsItem]],
    existing_atom_items: dict[int, QGraphicsEllipseItem],
    action: str,
) -> tuple[list[QGraphicsItem], dict[int, list[QGraphicsItem]], dict[int, QGraphicsEllipseItem]]:
    if action == "update" and _update_smiles_preview_geometry(geometry, existing_bond_items, existing_atom_items):
        return existing_items, existing_bond_items, existing_atom_items
    empty_items, _, _ = clear_smiles_preview(scene, existing_items)
    return _build_smiles_preview_geometry(scene, geometry, base_pen=base_pen, existing_items=empty_items)


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
    if action == "update" and _update_template_preview_geometry(geometry, existing_lines, existing_dots):
        return existing_items, existing_lines, existing_dots
    empty_items, _, _ = clear_template_preview(scene, existing_items)
    return _build_template_preview_geometry(scene, geometry, base_pen=base_pen, existing_items=empty_items)


def _build_smiles_preview_geometry(
    scene: QGraphicsScene,
    geometry: SmilesPreviewGeometry,
    *,
    base_pen: QPen,
    existing_items: list[QGraphicsItem],
) -> tuple[list[QGraphicsItem], dict[int, list[QGraphicsItem]], dict[int, QGraphicsEllipseItem]]:
    preview_color = _preview_color()
    bond_items: dict[int, list[QGraphicsItem]] = {}
    atom_items: dict[int, QGraphicsEllipseItem] = {}
    items = list(existing_items)
    for bond_id, segments in geometry.bond_segments.items():
        created_items: list[QGraphicsItem] = []
        for segment in segments:
            line = NoSelectLineItem(*segment)
            line.setPen(_preview_pen(base_pen, preview_color))
            line.setOpacity(0.5)
            scene.addItem(line)
            items.append(line)
            created_items.append(line)
        bond_items[bond_id] = created_items
    for atom_id, rect in geometry.atom_rects.items():
        dot = QGraphicsEllipseItem(*rect)
        dot.setBrush(preview_color)
        dot.setPen(QPen(Qt.PenStyle.NoPen))
        dot.setOpacity(0.5)
        scene.addItem(dot)
        items.append(dot)
        atom_items[atom_id] = dot
    return items, bond_items, atom_items


def _update_smiles_preview_geometry(
    geometry: SmilesPreviewGeometry,
    bond_items: dict[int, list[QGraphicsItem]],
    atom_items: dict[int, QGraphicsEllipseItem],
) -> bool:
    for bond_id, segments in geometry.bond_segments.items():
        items = bond_items.get(bond_id)
        if not items or len(items) != len(segments):
            return False
        for item, segment in zip(items, segments, strict=False):
            if not isinstance(item, QGraphicsLineItem):
                return False
            item.setLine(*segment)
    for atom_id, rect in geometry.atom_rects.items():
        dot = atom_items.get(atom_id)
        if dot is None:
            return False
        dot.setRect(*rect)
    return True


def _build_template_preview_geometry(
    scene: QGraphicsScene,
    geometry: TemplatePreviewGeometry,
    *,
    base_pen: QPen,
    existing_items: list[QGraphicsItem],
) -> tuple[list[QGraphicsItem], list[QGraphicsLineItem], list[QGraphicsEllipseItem]]:
    preview_color = _preview_color()
    items = list(existing_items)
    lines: list[QGraphicsLineItem] = []
    dots: list[QGraphicsEllipseItem] = []
    for x1, y1, x2, y2 in geometry.line_segments:
        line = NoSelectLineItem(x1, y1, x2, y2)
        line.setPen(_preview_pen(base_pen, preview_color))
        line.setOpacity(0.5)
        scene.addItem(line)
        lines.append(line)
        items.append(line)
    for x, y, width, height in geometry.dot_rects:
        dot = QGraphicsEllipseItem(x, y, width, height)
        dot.setBrush(preview_color)
        dot.setPen(QPen(Qt.PenStyle.NoPen))
        dot.setOpacity(0.5)
        scene.addItem(dot)
        dots.append(dot)
        items.append(dot)
    return items, lines, dots


def _update_template_preview_geometry(
    geometry: TemplatePreviewGeometry,
    lines: list[QGraphicsLineItem],
    dots: list[QGraphicsEllipseItem],
) -> bool:
    if len(lines) != len(geometry.line_segments) or len(dots) != len(geometry.dot_rects):
        return False
    for line, segment in zip(lines, geometry.line_segments, strict=False):
        line.setLine(*segment)
    for dot, rect in zip(dots, geometry.dot_rects, strict=False):
        dot.setRect(*rect)
    return True


def _preview_pen(base_pen: QPen, color: QColor) -> QPen:
    pen = QPen(base_pen)
    pen.setColor(color)
    return pen


def _preview_color() -> QColor:
    return QColor(120, 120, 120, 140)

