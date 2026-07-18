from __future__ import annotations

from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem

from chemvas.features.insertion import SmilesPreviewGeometry, TemplatePreviewGeometry
from chemvas.ui.preview_scene_renderer import (
    apply_smiles_preview_geometry as apply_smiles_preview_geometry_helper,
)
from chemvas.ui.preview_scene_renderer import (
    apply_template_preview_geometry as apply_template_preview_geometry_helper,
)
from chemvas.ui.preview_scene_renderer import (
    clear_smiles_preview as clear_smiles_preview_helper,
)
from chemvas.ui.preview_scene_renderer import (
    clear_template_preview as clear_template_preview_helper,
)
from chemvas.ui.scene_item_access import canvas_scene_for


def clear_smiles_preview_for(
    canvas,
    items: list[QGraphicsItem],
) -> tuple[
    list[QGraphicsItem], dict[int, list[QGraphicsItem]], dict[int, QGraphicsEllipseItem]
]:
    return clear_smiles_preview_helper(canvas_scene_for(canvas), items)


def apply_smiles_preview_geometry_for(
    canvas,
    geometry: SmilesPreviewGeometry,
    *,
    base_pen: QPen,
    existing_items: list[QGraphicsItem],
    existing_bond_items: dict[int, list[QGraphicsItem]],
    existing_atom_items: dict[int, QGraphicsEllipseItem],
    action: str,
) -> tuple[
    list[QGraphicsItem], dict[int, list[QGraphicsItem]], dict[int, QGraphicsEllipseItem]
]:
    return apply_smiles_preview_geometry_helper(
        canvas_scene_for(canvas),
        geometry,
        base_pen=base_pen,
        existing_items=existing_items,
        existing_bond_items=existing_bond_items,
        existing_atom_items=existing_atom_items,
        action=action,
    )


def clear_template_preview_for(
    canvas,
    items: list[QGraphicsItem],
) -> tuple[list[QGraphicsItem], list[QGraphicsLineItem], list[QGraphicsEllipseItem]]:
    return clear_template_preview_helper(canvas_scene_for(canvas), items)


def apply_template_preview_geometry_for(
    canvas,
    geometry: TemplatePreviewGeometry,
    *,
    base_pen: QPen,
    existing_items: list[QGraphicsItem],
    existing_lines: list[QGraphicsLineItem],
    existing_dots: list[QGraphicsEllipseItem],
    action: str,
) -> tuple[list[QGraphicsItem], list[QGraphicsLineItem], list[QGraphicsEllipseItem]]:
    return apply_template_preview_geometry_helper(
        canvas_scene_for(canvas),
        geometry,
        base_pen=base_pen,
        existing_items=existing_items,
        existing_lines=existing_lines,
        existing_dots=existing_dots,
        action=action,
    )


__all__ = [
    "apply_smiles_preview_geometry_for",
    "apply_template_preview_geometry_for",
    "clear_smiles_preview_for",
    "clear_template_preview_for",
]
