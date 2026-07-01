from __future__ import annotations

from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPathItem, QGraphicsPolygonItem

from ui.bond_style_logic import (
    DOUBLE_STYLE_OUTER,
    base_plain_double_style_for_dotted_variant,
    is_dotted_double_bond_style,
    is_plain_double_bond_style,
    normalized_plain_double_style,
)
from ui.canvas_bond_graphics_state import bond_items_for_id
from ui.canvas_model_access import atom_for_id, bond_for_id
from ui.renderer_style_access import (
    renderer_bold_bond_width_for,
    renderer_bond_line_width_for,
)


class BondGeometryUpdateService:
    def __init__(self, canvas, *, renderer) -> None:
        self.canvas = canvas
        self.renderer = renderer

    @staticmethod
    def _reset_item_origin(item) -> None:
        if item is None:
            return
        pos = item.pos()
        if abs(pos.x()) <= 1e-6 and abs(pos.y()) <= 1e-6:
            return
        item.setPos(0.0, 0.0)

    def _bond_line_width(self) -> float:
        return renderer_bond_line_width_for(self.canvas)

    def _bold_bond_width(self) -> float:
        return renderer_bold_bond_width_for(self.canvas)

    def _update_wedge_geometry(self, bond, items, a, b) -> None:
        polygon = self.renderer.wedge_polygon(a.x, a.y, b.x, b.y, bond.a, bond.b)
        if isinstance(items[0], QGraphicsPolygonItem):
            items[0].setPolygon(polygon)

    def _update_hash_geometry(self, bond, items, a, b) -> None:
        count = len(items)
        segments = self.renderer.hash_segments(a.x, a.y, b.x, b.y, count, bond.a, bond.b)
        for item, seg in zip(items, segments, strict=False):
            if isinstance(item, QGraphicsLineItem):
                item.setLine(*seg)

    def _update_dotted_geometry(self, bond, items, a, b) -> None:
        t0, t1 = self.renderer.trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
        start_x = a.x + (b.x - a.x) * t0
        start_y = a.y + (b.y - a.y) * t0
        end_x = a.x + (b.x - a.x) * t1
        end_y = a.y + (b.y - a.y) * t1
        if len(items) == 1 and isinstance(items[0], QGraphicsPathItem):
            items[0].setPath(self.renderer.dotted_bond_path(start_x, start_y, end_x, end_y, bond.a, bond.b))

    def _dotted_double_segments(self, bond, items, a, b):
        base_style = base_plain_double_style_for_dotted_variant(bond.style, bond.order)
        ring_center = self.renderer.ring_center_for_bond(bond)
        if ring_center is not None and len(items) >= 2:
            ring_center_3d = self.renderer.ring_center_3d_for_bond(bond)
            outer_seg, inner_seg, _ = self.renderer.ring_double_segments(
                a,
                b,
                ring_center,
                bond.a,
                bond.b,
                center_3d=ring_center_3d,
                style=base_style,
            )
        else:
            outer_seg, inner_seg, _ = self.renderer.plain_double_segments(
                a.x,
                a.y,
                b.x,
                b.y,
                style=base_style,
                a_id=bond.a,
                b_id=bond.b,
            )
        return base_style, outer_seg, inner_seg

    def _update_dotted_double_geometry(self, bond, items, a, b) -> None:
        base_style, outer_seg, inner_seg = self._dotted_double_segments(bond, items, a, b)
        if len(items) < 2:
            return
        outer_dotted = base_style == DOUBLE_STYLE_OUTER
        if outer_dotted:
            if isinstance(items[0], QGraphicsPathItem):
                items[0].setPath(self.renderer.dotted_bond_path(*outer_seg, bond.a, bond.b))
            if isinstance(items[1], QGraphicsLineItem):
                items[1].setLine(*inner_seg)
            return
        if isinstance(items[0], QGraphicsLineItem):
            items[0].setLine(*outer_seg)
        if isinstance(items[1], QGraphicsPathItem):
            items[1].setPath(self.renderer.dotted_bond_path(*inner_seg, bond.a, bond.b))

    def _update_ring_bold_double_geometry(self, bond, items, a, b, ring_center, bold_outward: bool) -> None:
        ring_center_3d = self.renderer.ring_center_3d_for_bond(bond)
        outer_seg, inner_seg, (nx, ny) = self.renderer.ring_double_segments(
            a,
            b,
            ring_center,
            bond.a,
            bond.b,
            center_3d=ring_center_3d,
        )
        use_nx, use_ny = (nx, ny) if not bold_outward else (-nx, -ny)
        outer_item = items[0]
        if isinstance(outer_item, QGraphicsPolygonItem):
            polygon = self.renderer.graphics_drawer.bold_strip_polygon(
                *outer_seg,
                use_nx,
                use_ny,
                self._bond_line_width(),
                self._bold_bond_width(),
                bond.a,
                bond.b,
            )
            outer_item.setPolygon(polygon)
        elif isinstance(outer_item, QGraphicsLineItem):
            outer_item.setLine(*outer_seg)
        inner_item = items[1]
        if isinstance(inner_item, QGraphicsLineItem):
            inner_item.setLine(*inner_seg)

    def _update_bold_multi_geometry(self, bond, items, a, b, bold_outward: bool) -> None:
        ring_center = self.renderer.ring_center_for_bond(bond) if bond.order == 2 else None
        if bond.order == 2 and ring_center is not None and len(items) >= 2:
            self._update_ring_bold_double_geometry(bond, items, a, b, ring_center, bold_outward)
            return
        segments = self.renderer.parallel_bond_segments(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
        if not segments:
            return
        if isinstance(items[0], QGraphicsPolygonItem):
            x1, y1, x2, y2 = segments[0]
            nx, ny = self.renderer.line_normal(x1, y1, x2, y2, None)
            if bold_outward:
                nx, ny = -nx, -ny
            polygon = self.renderer.strip_polygon(
                x1,
                y1,
                x2,
                y2,
                nx,
                ny,
                self._bond_line_width(),
                self._bold_bond_width(),
            )
            items[0].setPolygon(polygon)
        elif isinstance(items[0], QGraphicsLineItem):
            items[0].setLine(*segments[0])
        for item, seg in zip(items[1:], segments[1:], strict=False):
            if isinstance(item, QGraphicsLineItem):
                item.setLine(*seg)

    def _update_bold_single_geometry(self, bond, items, a, b, bold_outward: bool) -> None:
        # Mirror the build path (_bold_single_items): draw straight between the
        # atoms and mitre against bold neighbours, so a drag keeps the smooth
        # junction instead of reverting to the old square/overshot strip.
        ring_center = self.renderer.ring_center_for_bond(bond)
        nx, ny = self.renderer.line_normal(a.x, a.y, b.x, b.y, ring_center)
        if bold_outward:
            nx, ny = -nx, -ny
        if isinstance(items[0], QGraphicsPolygonItem):
            polygon = self.renderer.graphics_drawer.bold_strip_polygon(
                a.x,
                a.y,
                b.x,
                b.y,
                nx,
                ny,
                self._bond_line_width(),
                self._bold_bond_width(),
                bond.a,
                bond.b,
            )
            items[0].setPolygon(polygon)
        elif isinstance(items[0], QGraphicsLineItem):
            items[0].setLine(a.x, a.y, b.x, b.y)

    def _update_bold_geometry(self, bond, items, a, b) -> None:
        bold_outward = bond.style == "bold_out"
        if bond.order >= 2:
            self._update_bold_multi_geometry(bond, items, a, b, bold_outward)
            return
        self._update_bold_single_geometry(bond, items, a, b, bold_outward)

    def _update_plain_double_geometry(self, bond, items, a, b) -> None:
        variant = normalized_plain_double_style(bond.style, bond.order)
        ring_center = self.renderer.ring_center_for_bond(bond)
        if ring_center is not None and len(items) >= 2:
            ring_center_3d = self.renderer.ring_center_3d_for_bond(bond)
            outer_seg, inner_seg, _ = self.renderer.ring_double_segments(
                a,
                b,
                ring_center,
                bond.a,
                bond.b,
                center_3d=ring_center_3d,
                style=variant,
            )
        else:
            outer_seg, inner_seg, _ = self.renderer.plain_double_segments(
                a.x,
                a.y,
                b.x,
                b.y,
                style=variant,
                a_id=bond.a,
                b_id=bond.b,
            )
        if len(items) >= 2 and isinstance(items[0], QGraphicsLineItem) and isinstance(items[1], QGraphicsLineItem):
            items[0].setLine(*outer_seg)
            items[1].setLine(*inner_seg)

    def _update_parallel_geometry(self, bond, items, a, b) -> None:
        segments = self.renderer.parallel_bond_segments(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
        for item, seg in zip(items, segments, strict=False):
            if isinstance(item, QGraphicsLineItem):
                item.setLine(*seg)

    def _update_single_geometry(self, bond, items, a, b) -> None:
        t0, t1 = self.renderer.trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
        x1 = a.x + (b.x - a.x) * t0
        y1 = a.y + (b.y - a.y) * t0
        x2 = a.x + (b.x - a.x) * t1
        y2 = a.y + (b.y - a.y) * t1
        if isinstance(items[0], QGraphicsLineItem):
            items[0].setLine(x1, y1, x2, y2)

    def update_bond_geometry(self, bond_id: int) -> None:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return
        items = bond_items_for_id(self.canvas, bond_id)
        if not items:
            return
        for item in items:
            self._reset_item_origin(item)
        a = atom_for_id(self.canvas, bond.a)
        b = atom_for_id(self.canvas, bond.b)
        if a is None or b is None:
            return

        if bond.style == "wedge":
            self._update_wedge_geometry(bond, items, a, b)
        elif bond.style == "hash":
            self._update_hash_geometry(bond, items, a, b)
        elif bond.style == "dotted":
            self._update_dotted_geometry(bond, items, a, b)
        elif is_dotted_double_bond_style(bond.style, bond.order):
            self._update_dotted_double_geometry(bond, items, a, b)
        elif bond.style in {"bold", "bold_in", "bold_out"}:
            self._update_bold_geometry(bond, items, a, b)
        elif is_plain_double_bond_style(bond.style, bond.order):
            self._update_plain_double_geometry(bond, items, a, b)
        elif bond.order >= 2:
            self._update_parallel_geometry(bond, items, a, b)
        else:
            self._update_single_geometry(bond, items, a, b)


__all__ = ["BondGeometryUpdateService"]
