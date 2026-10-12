from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chemvas.features.rendering import (
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    dotted_bond_dot_centers,
    double_position_for_style,
    hash_segments_from_segment,
    is_positionable_double_bond_style,
    normalized_plain_double_style,
    offset_segment,
    trimmed_line_segment,
    wedge_triangle_from_segment,
)

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF

    from chemvas.ui.scene.scene_render_context import SceneRenderContext


class BondLineGeometryService:
    def __init__(self, context: SceneRenderContext, *, point_factory=None) -> None:
        self._point_factory = point_factory
        self.context = context
        self.graph = context.state.graph_state

    def _dotted_dot_radius(self) -> float:
        return max(0.4, self.context.renderer.bond_line_width() * 0.58)

    def _dotted_target_spacing(self) -> float:
        radius = self._dotted_dot_radius()
        return max(self.context.renderer.hash_spacing() * 0.95, radius * 4.0)

    def _junction_trim_for_atom(
        self, atom_id: int | None, other_id: int | None
    ) -> float:
        if atom_id is None:
            return 0.0
        bond_ids = set(self.graph.atom_bond_ids.get(atom_id, ()))
        if other_id is not None:
            for bond_id in list(bond_ids):
                bond = self.context.model.bond_for_id(bond_id)
                if bond is None:
                    continue
                if {bond.a, bond.b} == {atom_id, other_id}:
                    bond_ids.discard(bond_id)
        if not bond_ids:
            return 0.0
        return max(
            self.context.renderer.hash_spacing() * 0.4, self._dotted_dot_radius() * 1.75
        )

    def dotted_bond_dots(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> tuple[list[tuple[float, float]], float]:
        """Dot centres plus the radius to draw each of them at."""
        # Label trimming can consume the entire visible segment. Keep the
        # path primitive, but do not turn its collapsed span into a painted dot.
        if x1 == x2 and y1 == y2 and (a_id is not None or b_id is not None):
            return [], self._dotted_dot_radius()
        centers = dotted_bond_dot_centers(
            x1,
            y1,
            x2,
            y2,
            start_trim=self._junction_trim_for_atom(a_id, b_id),
            end_trim=self._junction_trim_for_atom(b_id, a_id),
            target_spacing=self._dotted_target_spacing(),
        )
        return centers, self._dotted_dot_radius()

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
            offset_unit = self.context.geometry.bond_offset_unit_3d(a_id, b_id)
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
        else:
            nx = -dy / length
            ny = dx / length
        spacing = self.context.renderer.bond_spacing()
        if count == 2:
            offsets = [-spacing / 2, spacing / 2]
        elif count == 3:
            offsets = [-spacing, 0.0, spacing]
        else:
            offsets = [0.0]
        t0, t1 = self.context.geometry.trim_line_for_labels(
            a_id,
            b_id,
            x1,
            y1,
            x2,
            y2,
            tuple((nx * offset, ny * offset) for offset in offsets),
        )
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

    def _plain_double_offsets(self) -> tuple[float, float]:
        side_offset = self.context.renderer.bond_spacing() * 1.1
        return side_offset, side_offset * 0.5

    def _native_double_distances(self, style: str) -> tuple[float, float]:
        side, center = self._plain_double_offsets()
        variant = normalized_plain_double_style(style, 2)
        if variant == DOUBLE_STYLE_DEFAULT:
            return 0.0, side
        if variant == DOUBLE_STYLE_OUTER:
            return 0.0, -side
        return -center, center

    def terminal_label_offset(self, atom_id: int) -> tuple[float, float]:
        """Center a terminal label between the same two painted bond axes."""
        bond_ids = self.graph.atom_bond_ids.get(atom_id, ())
        if len(bond_ids) != 1:
            return 0.0, 0.0
        bond = self.context.model.bond_for_id(next(iter(bond_ids)))
        if bond is None or not is_positionable_double_bond_style(
            bond.style, bond.order
        ):
            return 0.0, 0.0
        a, b = self.context.model.atoms[bond.a], self.context.model.atoms[bond.b]
        nx, ny = self._plain_double_normal(a.x, a.y, b.x, b.y, bond.a, bond.b)
        distances = self._native_double_distances(
            double_position_for_style(bond.style, bond.order)
        )
        shift = sum(distances) / 2.0
        return nx * shift, ny * shift

    def _double_neighbor_target(
        self,
        a_id: int | None,
        b_id: int | None,
        origin_x: float,
        origin_y: float,
    ) -> QPointF | None:
        if a_id is None or b_id is None:
            return None
        points: list[tuple[float, float]] = []
        candidate_bond_ids = set(self.graph.atom_bond_ids.get(a_id, ())) | set(
            self.graph.atom_bond_ids.get(b_id, ())
        )
        for bond_id in candidate_bond_ids:
            bond = self.context.model.bond_for_id(bond_id)
            if bond is None:
                continue
            if bond.a == a_id and bond.b != b_id:
                other = self.context.model.atoms.get(bond.b)
            elif bond.b == a_id and bond.a != b_id:
                other = self.context.model.atoms.get(bond.a)
            elif bond.a == b_id and bond.b != a_id:
                other = self.context.model.atoms.get(bond.b)
            elif bond.b == b_id and bond.a != a_id:
                other = self.context.model.atoms.get(bond.a)
            else:
                other = None
            if other is None:
                continue
            points.append((other.x - origin_x, other.y - origin_y))
        if not points:
            return None
        point_factory = self._point_factory
        if point_factory is None:
            from PyQt6.QtCore import QPointF

            point_factory = QPointF
        return point_factory(
            math.fsum(point[0] for point in points) / len(points),
            math.fsum(point[1] for point in points) / len(points),
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
        target = self._double_neighbor_target(a_id, b_id, x1, y1)
        if target is not None:
            return self.context.geometry.line_normal(0, 0, x2 - x1, y2 - y1, target)
        if a_id is not None and b_id is not None:
            offset_unit = self.context.geometry.bond_offset_unit_3d(a_id, b_id)
            if offset_unit is not None:
                return offset_unit[0], offset_unit[1]
        return self.context.geometry.line_normal(x1, y1, x2, y2, None)

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
        inner_nx, inner_ny = self._plain_double_normal(x1, y1, x2, y2, a_id, b_id)
        return self.native_double_segments(
            x1,
            y1,
            x2,
            y2,
            style=style,
            normal=(inner_nx, inner_ny),
            a_id=a_id,
            b_id=b_id,
        )

    def _double_endpoint_cotangent(
        self, atom_id, other_id, dx, dy, nx, ny
    ) -> float | None:
        """Intersect the inset with an adjacent bond's angular bisector.

        Only neighbors on the inset side shorten that line. No neighbor means
        a square full-length end. Chemical coordinates are never adjusted.
        """
        if (
            atom_id is None
            or self.context.geometry.label_rect_for_atom(atom_id) is not None
        ):
            return None
        atom = self.context.model.atoms.get(atom_id)
        length = math.hypot(dx, dy)
        if atom is None or length <= 1e-9:
            return None
        values = []
        for bond_id in self.graph.atom_bond_ids.get(atom_id, ()):
            bond = self.context.model.bond_for_id(bond_id)
            if bond is None:
                continue
            peer_id = bond.b if bond.a == atom_id else bond.a
            if peer_id == other_id:
                continue
            peer = self.context.model.atoms.get(peer_id)
            if peer is None:
                continue
            vx, vy = peer.x - atom.x, peer.y - atom.y
            distance = math.hypot(vx, vy)
            if distance <= 1e-9 or vx * nx + vy * ny <= 1e-9:
                continue
            cosine = max(-1.0, min(1.0, (dx * vx + dy * vy) / (length * distance)))
            if cosine >= 1.0 - 1e-9:
                continue
            values.append(math.sqrt((1.0 + cosine) / (1.0 - cosine)))
        return max(values) if values else None

    def native_double_segments(
        self, x1, y1, x2, y2, *, style, normal, a_id=None, b_id=None
    ):
        """Shared native axis/side placement for rings, chains and previews."""
        dx, dy = x2 - x1, y2 - y1
        inner_nx, inner_ny = normal
        distances = self._native_double_distances(style)
        offsets = tuple((inner_nx * d, inner_ny * d) for d in distances)
        t0, t1 = self.context.geometry.trim_line_for_labels(
            a_id, b_id, x1, y1, x2, y2, offsets
        )
        base_segment = (
            x1 + dx * t0,
            y1 + dy * t0,
            x1 + dx * t1,
            y1 + dy * t1,
        )
        length = math.hypot(dx, dy) or 1.0
        visible_length = math.hypot(
            base_segment[2] - base_segment[0], base_segment[3] - base_segment[1]
        )
        segments = []
        for offset in distances:
            segment = offset_segment(base_segment, inner_nx, inner_ny, offset)
            if abs(offset) > 1e-9:
                sign = 1 if offset > 0 else -1
                nx, ny = inner_nx * sign, inner_ny * sign
                left = (
                    self._double_endpoint_cotangent(a_id, b_id, dx, dy, nx, ny) or 0.0
                )
                right = (
                    self._double_endpoint_cotangent(b_id, a_id, -dx, -dy, nx, ny) or 0.0
                )
                start = min(visible_length * 0.45, abs(offset) * left)
                end = min(visible_length * 0.45, abs(offset) * right)
                segment = (
                    segment[0] + dx / length * start,
                    segment[1] + dy / length * start,
                    segment[2] - dx / length * end,
                    segment[3] - dy / length * end,
                )
            segments.append(segment)
        return segments[0], segments[1], normal

    def bond_stroke_corners(self, segment, a, b, a_id, b_id):
        """Paint the native flat inset and bounded primary-axis end mitres."""
        x1, y1, x2, y2 = segment
        dx, dy = b.x - a.x, b.y - a.y
        length = math.hypot(dx, dy) or 1.0
        stroke_dx, stroke_dy = x2 - x1, y2 - y1
        stroke_length = math.hypot(stroke_dx, stroke_dy)
        nx, ny = (
            (-stroke_dy / stroke_length, stroke_dx / stroke_length)
            if stroke_length > 1e-9
            else (-dy / length, dx / length)
        )
        half = self.context.renderer.bond_line_width() / 2.0
        on_axis = abs((x1 - a.x) * nx + (y1 - a.y) * ny) < 1e-7

        def endpoint(x, y, atom, first, second, vx, vy, off):
            shift = 0.0
            if on_axis and math.hypot(x - atom.x, y - atom.y) < 1e-7:
                cot = self._double_endpoint_cotangent(first, second, vx, vy, nx, ny)
                if cot is None:
                    opposite = self._double_endpoint_cotangent(
                        first, second, vx, vy, -nx, -ny
                    )
                    cot = -opposite if opposite is not None else 0.0
                shift = off * cot
                if abs(shift) > 6 * half:
                    shift = 0.0
            return (
                x + nx * off + vx / length * shift,
                y + ny * off + vy / length * shift,
            )

        return [
            endpoint(x1, y1, a, a_id, b_id, dx, dy, -half),
            endpoint(x2, y2, b, b_id, a_id, -dx, -dy, -half),
            endpoint(x2, y2, b, b_id, a_id, -dx, -dy, half),
            endpoint(x1, y1, a, a_id, b_id, dx, dy, half),
        ]

    def _stereo_label_trim(self, a_id, b_id, x1, y1, x2, y2):
        length = math.hypot(x2 - x1, y2 - y1) or 1.0
        half_width = self.context.renderer.bold_bond_pen().widthF() / 2.0
        ox = -(y2 - y1) / length * half_width
        oy = (x2 - x1) / length * half_width
        return self.context.geometry.trim_line_for_labels(
            a_id, b_id, x1, y1, x2, y2, ((-ox, -oy), (ox, oy))
        )

    def wedge_triangle(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ]:
        t0, t1 = self._stereo_label_trim(a_id, b_id, x1, y1, x2, y2)
        return wedge_triangle_from_segment(
            trimmed_line_segment(x1, y1, x2, y2, t0=t0, t1=t1),
            max_width=self.context.renderer.bold_bond_pen().widthF(),
        )

    def hash_topology_count(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> int:
        """Choose fresh hatch topology from the label-trimmed visible stem.

        Counting the full bond compresses too many strokes between large atom
        labels. Keep the established minimum of three items, including a fully
        clipped stem; in-place gesture updates deliberately retain their count.
        """
        t0, t1 = self._stereo_label_trim(a_id, b_id, x1, y1, x2, y2)
        start_x, start_y, end_x, end_y = trimmed_line_segment(
            x1, y1, x2, y2, t0=t0, t1=t1
        )
        length = math.hypot(end_x - start_x, end_y - start_y)
        return max(3, int(length / max(self.context.renderer.hash_spacing(), 1e-6)))

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
        t0, t1 = self._stereo_label_trim(a_id, b_id, x1, y1, x2, y2)
        return hash_segments_from_segment(
            trimmed_line_segment(x1, y1, x2, y2, t0=t0, t1=t1),
            count=count,
            max_size=self.context.renderer.bold_bond_pen().widthF(),
        )


def double_short_trim(
    length: float,
    *,
    has_label: bool,
) -> float:
    if has_label:
        return max(0.6, length * 0.08)
    return max(1.0, length * 0.12)


__all__ = ["BondLineGeometryService"]
