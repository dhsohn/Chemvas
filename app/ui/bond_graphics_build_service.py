from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsLineItem

from ui.bond_graphics_access import apply_color_to_bond_item_for
from ui.bond_style_logic import (
    is_dotted_double_bond_style,
    is_plain_double_bond_style,
    normalized_plain_double_style,
)
from ui.canvas_bond_graphics_state import set_bond_items_for_id
from ui.canvas_model_access import atom_for_id, bond_for_id
from ui.renderer_style_access import (
    bond_color_for,
    renderer_bold_bond_width_for,
    renderer_bond_line_width_for,
)
from ui.scene_item_access import add_item_to_canvas_scene
from ui.scene_selectability import make_item_selectable


class BondGraphicsBuildService:
    def __init__(self, canvas, *, renderer, drawer=None) -> None:
        self.canvas = canvas
        self.renderer = renderer
        self.drawer = renderer if drawer is None else drawer

    def _line_item(self, x1: float, y1: float, x2: float, y2: float):
        return self.renderer.graphics.line(x1, y1, x2, y2)

    def _bond_line_width(self) -> float:
        return renderer_bond_line_width_for(self.canvas)

    def _bold_bond_width(self) -> float:
        return renderer_bold_bond_width_for(self.canvas)

    def _bold_multi_items(self, bond, a, b, *, bold_outward: bool) -> list:
        if bond.order == 2:
            ring_center = self.renderer.ring_center_for_bond(bond)
            if ring_center is not None:
                ring_center_3d = self.renderer.ring_center_3d_for_bond(bond)
                outer_style = "bold_outward" if bold_outward else "bold_inward"
                return self.drawer.draw_ring_double_bond(
                    a,
                    b,
                    ring_center,
                    bond.a,
                    bond.b,
                    outer_style=outer_style,
                    center_3d=ring_center_3d,
                )

        items = self.drawer.draw_parallel_bonds(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
        if items and isinstance(items[0], QGraphicsLineItem):
            x1, y1, x2, y2 = (
                items[0].line().x1(),
                items[0].line().y1(),
                items[0].line().x2(),
                items[0].line().y2(),
            )
            nx, ny = self.renderer.line_normal(x1, y1, x2, y2, None)
            if bold_outward:
                nx, ny = -nx, -ny
            items[0] = self.drawer.one_sided_bond_strip(
                x1,
                y1,
                x2,
                y2,
                nx,
                ny,
                self._bond_line_width(),
                self._bold_bond_width(),
            )
        return items

    def _bold_single_items(self, bond, a, b, *, bold_outward: bool) -> list:
        # Draw the strip straight between the atoms; the mitre in
        # one_sided_bond_strip joins it to its bold neighbours at each vertex, so
        # no manual overshoot/pad is needed (that only produced spikes).
        ring_center = self.renderer.ring_center_for_bond(bond)
        nx, ny = self.renderer.line_normal(a.x, a.y, b.x, b.y, ring_center)
        if bold_outward:
            nx, ny = -nx, -ny
        return [
            self.drawer.one_sided_bond_strip(
                a.x,
                a.y,
                b.x,
                b.y,
                nx,
                ny,
                self._bond_line_width(),
                self._bold_bond_width(),
                a_id=bond.a,
                b_id=bond.b,
            )
        ]

    def _bold_items(self, bond, a, b) -> list:
        bold_outward = bond.style == "bold_out"
        if bond.order >= 2:
            return self._bold_multi_items(bond, a, b, bold_outward=bold_outward)
        return self._bold_single_items(bond, a, b, bold_outward=bold_outward)

    def _dotted_double_items(self, bond, a, b) -> list:
        ring_center = self.renderer.ring_center_for_bond(bond)
        ring_center_3d = self.renderer.ring_center_3d_for_bond(bond) if ring_center is not None else None
        return self.drawer.draw_dotted_double_bond(
            a,
            b,
            style=bond.style,
            a_id=bond.a,
            b_id=bond.b,
            ring_center=ring_center,
            center_3d=ring_center_3d,
        )

    def _plain_double_items(self, bond, a, b) -> list:
        variant = normalized_plain_double_style(bond.style, bond.order)
        ring_center = self.renderer.ring_center_for_bond(bond)
        if ring_center is not None:
            ring_center_3d = self.renderer.ring_center_3d_for_bond(bond)
            return self.drawer.draw_ring_double_bond(
                a,
                b,
                ring_center,
                bond.a,
                bond.b,
                center_3d=ring_center_3d,
                style=variant,
            )

        outer_seg, inner_seg, _ = self.renderer.plain_double_segments(
            a.x,
            a.y,
            b.x,
            b.y,
            style=variant,
            a_id=bond.a,
            b_id=bond.b,
        )
        return [self._line_item(*outer_seg), self._line_item(*inner_seg)]

    def _single_items(self, bond, a, b) -> list:
        t0, t1 = self.renderer.trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
        x1 = a.x + (b.x - a.x) * t0
        y1 = a.y + (b.y - a.y) * t0
        x2 = a.x + (b.x - a.x) * t1
        y2 = a.y + (b.y - a.y) * t1
        return [self._line_item(x1, y1, x2, y2)]

    def _items_for_bond(self, bond, a, b) -> list:
        if bond.style == "wedge":
            return self.drawer.draw_wedge_bond(a.x, a.y, b.x, b.y, bond.a, bond.b)
        if bond.style == "hash":
            return self.drawer.draw_hash_bond(a.x, a.y, b.x, b.y, bond.a, bond.b)
        if bond.style == "dotted":
            return self.drawer.draw_dotted_bond(a.x, a.y, b.x, b.y, bond.a, bond.b)
        if is_dotted_double_bond_style(bond.style, bond.order):
            return self._dotted_double_items(bond, a, b)
        if bond.style in {"bold", "bold_in", "bold_out"}:
            return self._bold_items(bond, a, b)
        if is_plain_double_bond_style(bond.style, bond.order):
            return self._plain_double_items(bond, a, b)
        if bond.order >= 2:
            return self.drawer.draw_parallel_bonds(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
        return self._single_items(bond, a, b)

    def add_bond_graphics(self, bond_id: int) -> None:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return
        a = atom_for_id(self.canvas, bond.a)
        b = atom_for_id(self.canvas, bond.b)
        if a is None or b is None:
            return

        color = QColor(bond.color or bond_color_for(self.canvas))
        items = self._items_for_bond(bond, a, b)
        for item in items:
            item.setData(0, "bond")
            item.setData(1, bond_id)
            make_item_selectable(item)
            apply_color_to_bond_item_for(self.canvas, item, color)
            add_item_to_canvas_scene(self.canvas, item)
        set_bond_items_for_id(self.canvas, bond_id, items)


__all__ = ["BondGraphicsBuildService"]
