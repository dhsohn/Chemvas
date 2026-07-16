from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from ui.bond_geometry_primitives import (
    line_intersection,
    normal_away_from_parallel_segment,
    strip_polygon,
)
from ui.bond_style_logic import (
    BOLD_BOND_STYLES,
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    base_plain_double_style_for_dotted_variant,
    double_position_for_style,
    is_bold_double_bond_style,
)
from ui.canvas_graph_state import graph_state_for
from ui.canvas_model_access import atom_for_id, bond_for_id
from ui.renderer_style_access import (
    bond_pen_for,
    renderer_bold_bond_width_for,
    renderer_bond_line_width_for,
    renderer_hash_spacing_for,
)

# Cap the mitre extension so a very acute junction falls back to a flat end
# instead of shooting a long spike (Qt's "mitre limit" idea, in width units).
_MITER_LIMIT = 6.0


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
            ox1, oy1, ox2, oy2 = outer_seg
            outer_item = self.one_sided_bond_strip(
                ox1,
                oy1,
                ox2,
                oy2,
                use_nx,
                use_ny,
                self._bond_line_width(),
                self._bold_bond_width(),
                a_id=a_id,
                b_id=b_id,
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
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        if bold_width <= base_width + 1e-6:
            return self._line_item(x1, y1, x2, y2)
        polygon = self.bold_strip_polygon(x1, y1, x2, y2, nx, ny, base_width, bold_width, a_id, b_id)
        return self.renderer.graphics.filled_polygon(polygon)

    def bold_strip_polygon(self, x1, y1, x2, y2, nx, ny, base_width, bold_width, a_id, b_id):
        # A bold bond is a one-sided trapezoid on the atom centreline. On its own
        # its ends are cut square, so neighbouring bold strips leave spikes/gaps at
        # a shared vertex. Extend each end edge to meet the neighbour's matching
        # edge (a true mitre) so the run reads as one continuous outline.
        if a_id is None and b_id is None:
            return strip_polygon(x1, y1, x2, y2, nx, ny, base_width, bold_width)
        outer_off = -base_width / 2.0
        inner_off = bold_width - base_width / 2.0
        dx = x2 - x1
        dy = y2 - y1
        start_nb = self._bold_neighbor(a_id, b_id, dx, dy)
        end_nb = self._bold_neighbor(b_id, a_id, -dx, -dy)
        outer_start = self._miter_corner(x1, y1, nx, ny, outer_off, dx, dy, a_id, start_nb, bold_width)
        outer_end = self._miter_corner(x2, y2, nx, ny, outer_off, dx, dy, b_id, end_nb, bold_width)
        inner_end = self._miter_corner(x2, y2, nx, ny, inner_off, dx, dy, b_id, end_nb, bold_width)
        inner_start = self._miter_corner(x1, y1, nx, ny, inner_off, dx, dy, a_id, start_nb, bold_width)
        return QPolygonF([outer_start, outer_end, inner_end, inner_start])

    def _bold_strip_normal(self, bond, a, b) -> tuple[float, float]:
        if is_bold_double_bond_style(bond.style, bond.order):
            variant = double_position_for_style(bond.style, bond.order)
            ring_center = self.renderer.ring_center_for_bond(bond)
            if ring_center is not None:
                segments = self.renderer.ring_double_segments(
                    a,
                    b,
                    ring_center,
                    bond.a,
                    bond.b,
                    center_3d=self.renderer.ring_center_3d_for_bond(bond),
                    style=variant,
                )
            else:
                segments = self.renderer.plain_double_segments(
                    a.x,
                    a.y,
                    b.x,
                    b.y,
                    style=variant,
                    a_id=bond.a,
                    b_id=bond.b,
                )
            outer_seg, inner_seg, normal = segments
            bold_index = 1 if ring_center is not None and variant == DOUBLE_STYLE_OUTER else 0
            pair = (outer_seg, inner_seg)
            return normal_away_from_parallel_segment(pair[bold_index], pair[1 - bold_index], *normal)
        ring_center = self.renderer.ring_center_for_bond(bond)
        nx, ny = self.renderer.line_normal(a.x, a.y, b.x, b.y, ring_center)
        if bond.style == "bold_out":
            nx, ny = -nx, -ny
        return nx, ny

    def _bold_neighbor(self, vertex_id, other_id, away_dx, away_dy):
        # Among bold bonds sharing this vertex (excluding this bond), pick the one
        # whose direction most nearly continues this bond in a straight line — the
        # natural perimeter partner to mitre against at higher-degree junctions.
        if vertex_id is None:
            return None
        length = math.hypot(away_dx, away_dy) or 1.0
        ax = away_dx / length
        ay = away_dy / length
        vertex = atom_for_id(self.canvas, vertex_id)
        if vertex is None:
            return None
        best = None
        best_score = -2.0
        for bond_id in graph_state_for(self.canvas).atom_bond_ids.get(vertex_id, ()):
            neighbor = bond_for_id(self.canvas, bond_id)
            if neighbor is None or neighbor.style not in BOLD_BOND_STYLES:
                continue
            if {neighbor.a, neighbor.b} == {vertex_id, other_id}:
                continue
            far_id = neighbor.b if neighbor.a == vertex_id else neighbor.a
            far = atom_for_id(self.canvas, far_id)
            if far is None:
                continue
            fdx = far.x - vertex.x
            fdy = far.y - vertex.y
            flen = math.hypot(fdx, fdy) or 1.0
            score = -(ax * fdx / flen + ay * fdy / flen)
            if score > best_score:
                best_score = score
                best = neighbor
        return best

    def _miter_corner(self, vx, vy, nx, ny, off, dx, dy, vertex_id, neighbor, bold_width) -> QPointF:
        base = QPointF(vx + nx * off, vy + ny * off)
        if neighbor is None or vertex_id is None:
            return base
        nb_a = atom_for_id(self.canvas, neighbor.a)
        nb_b = atom_for_id(self.canvas, neighbor.b)
        if nb_a is None or nb_b is None:
            return base
        nbnx, nbny = self._bold_strip_normal(neighbor, nb_a, nb_b)
        far_id = neighbor.b if neighbor.a == vertex_id else neighbor.a
        far = atom_for_id(self.canvas, far_id)
        if far is None:
            return base
        point = line_intersection(
            vx + nx * off,
            vy + ny * off,
            dx,
            dy,
            vx + nbnx * off,
            vy + nbny * off,
            far.x - vx,
            far.y - vy,
        )
        if point is None:
            return base
        if math.hypot(point[0] - vx, point[1] - vy) > _MITER_LIMIT * bold_width:
            return base
        return QPointF(point[0], point[1])

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
