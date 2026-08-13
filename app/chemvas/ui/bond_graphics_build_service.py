from __future__ import annotations

from PyQt6.QtGui import QColor

from chemvas.ui.bond_geometry_plan_service import (
    BondLinePrimitive,
    BondPathPrimitive,
    BondPolygonPrimitive,
)
from chemvas.ui.bond_graphics_access import apply_color_to_bond_item_for
from chemvas.ui.canvas_bond_graphics_state import set_bond_items_for_id
from chemvas.ui.canvas_model_access import atom_for_id, bond_for_id
from chemvas.ui.renderer_style_access import bond_color_for, bond_pen_for
from chemvas.ui.scene_item_access import add_item_to_canvas_scene
from chemvas.ui.scene_selectability import make_item_selectable


class BondGraphicsBuildService:
    def __init__(self, canvas, *, renderer, planner) -> None:
        self.canvas = canvas
        self.renderer = renderer
        self.planner = planner

    def _item_for_primitive(self, primitive):
        if isinstance(primitive, BondLinePrimitive):
            return self.renderer.graphics.line(*primitive.segment)
        if isinstance(primitive, BondPathPrimitive):
            return self.renderer.graphics.path_fill(primitive.path)
        if isinstance(primitive, BondPolygonPrimitive):
            pen = bond_pen_for(self.canvas) if primitive.outlined else None
            return self.renderer.graphics.filled_polygon(
                primitive.polygon,
                pen=pen,
            )
        raise TypeError(f"unsupported bond primitive: {type(primitive).__name__}")

    def add_bond_graphics(self, bond_id: int) -> None:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return
        a = atom_for_id(self.canvas, bond.a)
        b = atom_for_id(self.canvas, bond.b)
        if a is None or b is None:
            return

        color = QColor(bond.color or bond_color_for(self.canvas))
        primitives = self.planner.primitives_for_bond(bond, a, b)
        items = [self._item_for_primitive(primitive) for primitive in primitives]
        for item in items:
            item.setData(0, "bond")
            item.setData(1, bond_id)
            make_item_selectable(item)
            apply_color_to_bond_item_for(self.canvas, item, color)
            add_item_to_canvas_scene(self.canvas, item)
        set_bond_items_for_id(self.canvas, bond_id, items)


__all__ = ["BondGraphicsBuildService"]
