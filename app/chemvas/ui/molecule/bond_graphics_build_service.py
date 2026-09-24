from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from chemvas.ui.molecule.bond_geometry_plan_service import (
    BondLinePrimitive,
    BondPathPrimitive,
    BondPolygonPrimitive,
)
from chemvas.ui.scene.scene_selectability import make_item_selectable


def apply_color_to_bond_item(item, color) -> None:
    if hasattr(item, "setPen"):
        pen = item.pen()
        pen.setColor(color)
        item.setPen(pen)
    if hasattr(item, "setBrush") and item.brush().style() != Qt.BrushStyle.NoBrush:
        item.setBrush(color)


if TYPE_CHECKING:
    from chemvas.ui.scene.scene_render_context import SceneRenderContext


class BondGraphicsBuildService:
    def __init__(self, context: SceneRenderContext, *, renderer, planner) -> None:
        self.context = context
        self.renderer = renderer
        self.planner = planner

    def _item_for_primitive(self, primitive):
        if isinstance(primitive, BondLinePrimitive):
            return self.renderer.graphics.line(*primitive.segment)
        if isinstance(primitive, BondPathPrimitive):
            return self.renderer.graphics.path_fill(primitive.path)
        if isinstance(primitive, BondPolygonPrimitive):
            pen = self.context.renderer.bond_pen() if primitive.outlined else None
            return self.renderer.graphics.filled_polygon(
                primitive.polygon,
                pen=pen,
            )
        raise TypeError(f"unsupported bond primitive: {type(primitive).__name__}")

    def add_bond_graphics(self, bond_id: int) -> None:
        bond = self.context.model.bond_for_id(bond_id)
        if bond is None:
            return
        a = self.context.model.atoms.get(bond.a)
        b = self.context.model.atoms.get(bond.b)
        if a is None or b is None:
            return

        color = QColor(bond.color or self.context.renderer.style.bond_color)
        primitives = self.planner.primitives_for_bond(bond, a, b)
        items = [self._item_for_primitive(primitive) for primitive in primitives]
        for item in items:
            item.setData(0, "bond")
            item.setData(1, bond_id)
            make_item_selectable(item)
            apply_color_to_bond_item(item, color)
            self.context.scene.addItem(item)
        self.context.state.bond_graphics_state.bond_items[bond_id] = items


__all__ = ["BondGraphicsBuildService"]
