from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

from ui.bond_geometry_primitives import strip_polygon
from ui.bond_style_logic import (
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    base_plain_double_style_for_dotted_variant,
)
from ui.renderer_style_access import (
    bond_pen_for,
    renderer_bold_bond_width_for,
    renderer_bond_line_width_for,
    renderer_hash_spacing_for,
)


class BondGraphicsDrawService:
    def __init__(self, canvas, *, renderer) -> None:
        self.canvas = canvas
        self.renderer = renderer

    def _line_item(self, x1: float, y1: float, x2: float, y2: float, *, dotted: bool = False):
        return self.renderer.graphics.line(x1, y1, x2, y2, dotted=dotted)

    def _bond_line_width(self) -> float:
        return renderer_bond_line_width_for(self.canvas)

    def _bold_bond_width(self) -> float:
        return renderer_bold_bond_width_for(self.canvas)

    def draw_ring_double_bond(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        outer_style: str = "normal",
        center_3d: tuple[float, float, float] | None = None,
        style: str = DOUBLE_STYLE_DEFAULT,
    ):
        outer_seg, inner_seg, (nx, ny) = self.renderer.ring_double_segments(
            a,
            b,
            center,
            a_id,
            b_id,
            center_3d=center_3d,
            style=style,
        )
        if outer_style in {"bold_inward", "bold_outward"}:
            use_nx, use_ny = (nx, ny) if outer_style == "bold_inward" else (-nx, -ny)
            outer_item = self.one_sided_bond_strip(
                *outer_seg,
                use_nx,
                use_ny,
                self._bond_line_width(),
                self._bold_bond_width(),
            )
        else:
            outer_item = self._line_item(*outer_seg)
        inner_line = self._line_item(*inner_seg)
        return [outer_item, inner_line]

    def one_sided_bond_strip(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        nx: float,
        ny: float,
        base_width: float,
        bold_width: float,
    ):
        if bold_width <= base_width + 1e-6:
            return self._line_item(x1, y1, x2, y2)
        polygon = strip_polygon(x1, y1, x2, y2, nx, ny, base_width, bold_width)
        return self.renderer.graphics.filled_polygon(polygon)

    def draw_parallel_bonds(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        segments = self.renderer.parallel_bond_segments(x1, y1, x2, y2, count, a_id, b_id)
        return [self._line_item(*segment) for segment in segments]

    def draw_dotted_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        t0, t1 = self.renderer.trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        start_x = x1 + (x2 - x1) * t0
        start_y = y1 + (y2 - y1) * t0
        end_x = x1 + (x2 - x1) * t1
        end_y = y1 + (y2 - y1) * t1
        path = self.renderer.dotted_bond_path(start_x, start_y, end_x, end_y, a_id, b_id)
        return [self.renderer.graphics.path_fill(path)]

    def draw_dotted_double_bond(
        self,
        a,
        b,
        *,
        style: str,
        a_id: int | None = None,
        b_id: int | None = None,
        ring_center: QPointF | None = None,
        center_3d: tuple[float, float, float] | None = None,
    ):
        base_style = base_plain_double_style_for_dotted_variant(style, 2)
        if ring_center is not None:
            outer_seg, inner_seg, _ = self.renderer.ring_double_segments(
                a,
                b,
                ring_center,
                a_id,
                b_id,
                center_3d=center_3d,
                style=base_style,
            )
        else:
            outer_seg, inner_seg, _ = self.renderer.plain_double_segments(
                a.x,
                a.y,
                b.x,
                b.y,
                style=base_style,
                a_id=a_id,
                b_id=b_id,
            )
        dotted_outer = base_style == DOUBLE_STYLE_OUTER
        outer_item = (
            self.renderer.graphics.path_fill(self.renderer.dotted_bond_path(*outer_seg, a_id, b_id))
            if dotted_outer
            else self._line_item(*outer_seg)
        )
        inner_item = (
            self.renderer.graphics.path_fill(self.renderer.dotted_bond_path(*inner_seg, a_id, b_id))
            if not dotted_outer
            else self._line_item(*inner_seg)
        )
        return [outer_item, inner_item]

    def draw_wedge_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        polygon = self.renderer.wedge_polygon(x1, y1, x2, y2, a_id, b_id)
        return [self.renderer.graphics.filled_polygon(polygon, pen=bond_pen_for(self.canvas))]

    def draw_hash_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        count = max(3, int(length / max(renderer_hash_spacing_for(self.canvas), 1e-6)))
        segments = self.renderer.hash_segments(x1, y1, x2, y2, count, a_id, b_id)
        return [self._line_item(*segment) for segment in segments]


__all__ = ["BondGraphicsDrawService"]
