from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.features.rendering import (
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    dotted_bond_path_from_trimmed_segment,
    hash_segments_from_segment,
    normalized_plain_double_style,
    offset_segment,
    trim_segment,
    trimmed_line_segment,
    wedge_polygon_from_segment,
)
from chemvas.ui.bond_graphics_access import bond_offset_unit_3d_for, line_normal_for
from chemvas.ui.bond_label_geometry_access import (
    label_rect_for_atom_for,
    trim_line_for_labels_for,
)
from chemvas.ui.canvas_graph_state import graph_state_for
from chemvas.ui.canvas_model_access import atom_for_id, bond_for_id
from chemvas.ui.renderer_style_access import (
    bold_bond_pen_for,
    renderer_bond_line_width_for,
    renderer_bond_spacing_for,
    renderer_hash_spacing_for,
)

if TYPE_CHECKING:
    from PyQt6.QtGui import QPainterPath, QPolygonF


class BondLineGeometryService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.graph = graph_state_for(canvas)

    def _bond_line_width(self) -> float:
        return renderer_bond_line_width_for(self.canvas)

    def _bond_spacing(self) -> float:
        return renderer_bond_spacing_for(self.canvas)

    def _hash_spacing(self) -> float:
        return renderer_hash_spacing_for(self.canvas)

    def _dotted_dot_radius(self) -> float:
        return max(0.4, self._bond_line_width() * 0.58)

    def _dotted_target_spacing(self) -> float:
        radius = self._dotted_dot_radius()
        return max(self._hash_spacing() * 0.95, radius * 4.0)

    def _junction_trim_for_atom(
        self, atom_id: int | None, other_id: int | None
    ) -> float:
        if atom_id is None:
            return 0.0
        bond_ids = set(self.graph.atom_bond_ids.get(atom_id, ()))
        if other_id is not None:
            for bond_id in list(bond_ids):
                bond = bond_for_id(self.canvas, bond_id)
                if bond is None:
                    continue
                if {bond.a, bond.b} == {atom_id, other_id}:
                    bond_ids.discard(bond_id)
        if not bond_ids:
            return 0.0
        return max(self._hash_spacing() * 0.4, self._dotted_dot_radius() * 1.75)

    def dotted_bond_path(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> QPainterPath:
        radius = self._dotted_dot_radius()
        return dotted_bond_path_from_trimmed_segment(
            x1,
            y1,
            x2,
            y2,
            start_trim=self._junction_trim_for_atom(a_id, b_id),
            end_trim=self._junction_trim_for_atom(b_id, a_id),
            dot_radius=radius,
            target_spacing=self._dotted_target_spacing(),
        )

    def parallel_bond_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list[tuple[float, float, float, float]]:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        offset_unit = None
        if a_id is not None and b_id is not None:
            offset_unit = bond_offset_unit_3d_for(self.canvas, a_id, b_id)
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
        else:
            nx = -dy / length
            ny = dx / length
        spacing = self._bond_spacing()
        if count == 2:
            offsets = [-spacing / 2, spacing / 2]
        elif count == 3:
            offsets = [-spacing, 0.0, spacing]
        else:
            offsets = [0.0]
        t0, t1 = trim_line_for_labels_for(self.canvas, a_id, b_id, x1, y1, x2, y2)
        base_x1 = x1 + dx * t0
        base_y1 = y1 + dy * t0
        base_x2 = x1 + dx * t1
        base_y2 = y1 + dy * t1
        segments = []
        for offset in offsets:
            ox = nx * offset
            oy = ny * offset
            segments.append((base_x1 + ox, base_y1 + oy, base_x2 + ox, base_y2 + oy))
        return segments

    @staticmethod
    def _double_short_trim(
        length: float,
        *,
        has_label: bool,
    ) -> float:
        if has_label:
            return max(0.6, length * 0.08)
        return max(1.0, length * 0.12)

    def _plain_double_offsets(self) -> tuple[float, float]:
        side_offset = self._bond_spacing() * 1.1
        return side_offset, side_offset * 0.5

    def _double_neighbor_target(
        self,
        a_id: int | None,
        b_id: int | None,
    ) -> QPointF | None:
        if a_id is None or b_id is None:
            return None
        points: list[tuple[float, float]] = []
        candidate_bond_ids = set(self.graph.atom_bond_ids.get(a_id, ())) | set(
            self.graph.atom_bond_ids.get(b_id, ())
        )
        for bond_id in candidate_bond_ids:
            bond = bond_for_id(self.canvas, bond_id)
            if bond is None:
                continue
            if bond.a == a_id and bond.b != b_id:
                other = atom_for_id(self.canvas, bond.b)
            elif bond.b == a_id and bond.a != b_id:
                other = atom_for_id(self.canvas, bond.a)
            elif bond.a == b_id and bond.b != a_id:
                other = atom_for_id(self.canvas, bond.b)
            elif bond.b == b_id and bond.a != a_id:
                other = atom_for_id(self.canvas, bond.a)
            else:
                other = None
            if other is None:
                continue
            points.append((other.x, other.y))
        if not points:
            return None
        return QPointF(
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )

    def _plain_double_normal(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> tuple[float, float]:
        target = self._double_neighbor_target(a_id, b_id)
        if target is not None:
            return line_normal_for(self.canvas, x1, y1, x2, y2, target)
        if a_id is not None and b_id is not None:
            offset_unit = bond_offset_unit_3d_for(self.canvas, a_id, b_id)
            if offset_unit is not None:
                return offset_unit[0], offset_unit[1]
        return line_normal_for(self.canvas, x1, y1, x2, y2, None)

    def plain_double_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        style: str,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float],
    ]:
        dx = x2 - x1
        dy = y2 - y1
        t0, t1 = trim_line_for_labels_for(self.canvas, a_id, b_id, x1, y1, x2, y2)
        base_segment = (
            x1 + dx * t0,
            y1 + dy * t0,
            x1 + dx * t1,
            y1 + dy * t1,
        )
        inner_nx, inner_ny = self._plain_double_normal(*base_segment, a_id, b_id)
        side_offset, center_offset = self._plain_double_offsets()
        outer_full_seg = offset_segment(base_segment, inner_nx, inner_ny, -side_offset)
        inner_full_seg = offset_segment(base_segment, inner_nx, inner_ny, side_offset)
        outer_center_seg = offset_segment(
            base_segment, inner_nx, inner_ny, -center_offset
        )
        inner_center_seg = offset_segment(
            base_segment, inner_nx, inner_ny, center_offset
        )
        base_length = (
            math.hypot(
                base_segment[2] - base_segment[0], base_segment[3] - base_segment[1]
            )
            or 1.0
        )
        has_label = False
        if a_id is not None and label_rect_for_atom_for(self.canvas, a_id) is not None:
            has_label = True
        if b_id is not None and label_rect_for_atom_for(self.canvas, b_id) is not None:
            has_label = True
        trim = self._double_short_trim(base_length, has_label=has_label)
        variant = normalized_plain_double_style(style, 2)
        if variant == DOUBLE_STYLE_DEFAULT:
            return (
                base_segment,
                trim_segment(inner_full_seg, trim),
                (inner_nx, inner_ny),
            )
        if variant == DOUBLE_STYLE_OUTER:
            return (
                base_segment,
                trim_segment(outer_full_seg, trim),
                (inner_nx, inner_ny),
            )
        return outer_center_seg, inner_center_seg, (inner_nx, inner_ny)

    def wedge_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> QPolygonF:
        t0, t1 = trim_line_for_labels_for(self.canvas, a_id, b_id, x1, y1, x2, y2)
        return wedge_polygon_from_segment(
            trimmed_line_segment(x1, y1, x2, y2, t0=t0, t1=t1),
            max_width=bold_bond_pen_for(self.canvas).widthF(),
        )

    def hash_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list[tuple[float, float, float, float]]:
        t0, t1 = trim_line_for_labels_for(self.canvas, a_id, b_id, x1, y1, x2, y2)
        return hash_segments_from_segment(
            trimmed_line_segment(x1, y1, x2, y2, t0=t0, t1=t1),
            count=count,
            max_size=bold_bond_pen_for(self.canvas).widthF(),
        )


__all__ = ["BondLineGeometryService"]
