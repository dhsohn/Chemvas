from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtGui import QPainterPath, QPolygonF

from chemvas.features.rendering import (
    BOLD_BOND_STYLES,
    DOUBLE_STYLE_OUTER,
    LineSegment,
    base_plain_double_style_for_dotted_variant,
    double_position_for_style,
    is_dotted_double_bond_style,
    is_plain_double_bond_style,
    normal_away_from_parallel_segment,
    normalized_plain_double_style,
)
from chemvas.ui.renderer_style_access import (
    renderer_bold_bond_width_for,
    renderer_bond_line_width_for,
    renderer_hash_spacing_for,
)


@dataclass(frozen=True, slots=True)
class BondLinePrimitive:
    segment: LineSegment


@dataclass(frozen=True, slots=True)
class BondPathPrimitive:
    path: QPainterPath


@dataclass(frozen=True, slots=True)
class BondPolygonPrimitive:
    polygon: QPolygonF
    outlined: bool = False


BondPrimitive = BondLinePrimitive | BondPathPrimitive | BondPolygonPrimitive


class BondGeometryPlanService:
    """Compute the ordered graphics primitives for one model bond.

    Build materializes this plan as scene items. In-place updates apply a new
    plan to those same item objects, so style/ring dispatch and geometry cannot
    drift between the two paths.
    """

    def __init__(self, canvas, *, renderer) -> None:
        self.canvas = canvas
        self.renderer = renderer

    def _bond_line_width(self) -> float:
        return renderer_bond_line_width_for(self.canvas)

    def _bold_bond_width(self) -> float:
        return renderer_bold_bond_width_for(self.canvas)

    def _line(self, segment: LineSegment) -> BondLinePrimitive:
        return BondLinePrimitive(segment)

    def _bold_strip(
        self,
        segment: LineSegment,
        normal: tuple[float, float],
        *,
        endpoint_ids: tuple[int, int] | None = None,
    ) -> BondPrimitive:
        base_width = self._bond_line_width()
        bold_width = self._bold_bond_width()
        if bold_width <= base_width + 1e-6:
            return self._line(segment)
        a_id, b_id = endpoint_ids if endpoint_ids is not None else (None, None)
        return BondPolygonPrimitive(
            self.renderer.graphics_drawer.bold_strip_polygon(
                *segment,
                *normal,
                base_width,
                bold_width,
                a_id,
                b_id,
            )
        )

    def _double_segments(self, bond, a, b, *, style: str):
        ring_center = self.renderer.ring_center_for_bond(bond)
        if ring_center is not None:
            ring_center_3d = self.renderer.ring_center_3d_for_bond(bond)
            segments = self.renderer.ring_double_segments(
                a,
                b,
                ring_center,
                bond.a,
                bond.b,
                center_3d=ring_center_3d,
                style=style,
            )
        else:
            segments = self.renderer.plain_double_segments(
                a.x,
                a.y,
                b.x,
                b.y,
                style=style,
                a_id=bond.a,
                b_id=bond.b,
            )
        return ring_center, segments

    def _wedge_primitives(self, bond, a, b) -> tuple[BondPrimitive, ...]:
        polygon = self.renderer.wedge_polygon(a.x, a.y, b.x, b.y, bond.a, bond.b)
        return (BondPolygonPrimitive(polygon, outlined=True),)

    def _hash_primitives(
        self,
        bond,
        a,
        b,
        *,
        topology_count: int | None,
    ) -> tuple[BondPrimitive, ...]:
        if topology_count is None:
            length = math.hypot(b.x - a.x, b.y - a.y) or 1.0
            topology_count = max(
                3,
                int(length / max(renderer_hash_spacing_for(self.canvas), 1e-6)),
            )
        elif topology_count < 3:
            raise ValueError("hash bond graphics topology requires at least 3 items")
        segments = self.renderer.hash_segments(
            a.x,
            a.y,
            b.x,
            b.y,
            topology_count,
            bond.a,
            bond.b,
        )
        return tuple(self._line(segment) for segment in segments)

    def _dotted_primitives(self, bond, a, b) -> tuple[BondPrimitive, ...]:
        t0, t1 = self.renderer.trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
        segment = (
            a.x + (b.x - a.x) * t0,
            a.y + (b.y - a.y) * t0,
            a.x + (b.x - a.x) * t1,
            a.y + (b.y - a.y) * t1,
        )
        return (
            BondPathPrimitive(self.renderer.dotted_bond_path(*segment, bond.a, bond.b)),
        )

    def _dotted_double_primitives(self, bond, a, b) -> tuple[BondPrimitive, ...]:
        base_style = base_plain_double_style_for_dotted_variant(bond.style, bond.order)
        _, (outer_segment, inner_segment, _) = self._double_segments(
            bond, a, b, style=base_style
        )
        if base_style == DOUBLE_STYLE_OUTER:
            return (
                BondPathPrimitive(
                    self.renderer.dotted_bond_path(*outer_segment, bond.a, bond.b)
                ),
                self._line(inner_segment),
            )
        return (
            self._line(outer_segment),
            BondPathPrimitive(
                self.renderer.dotted_bond_path(*inner_segment, bond.a, bond.b)
            ),
        )

    def _bold_double_primitives(self, bond, a, b) -> tuple[BondPrimitive, ...]:
        variant = double_position_for_style(bond.style, bond.order)
        ring_center, (outer_segment, inner_segment, normal) = self._double_segments(
            bond, a, b, style=variant
        )
        segments = (outer_segment, inner_segment)
        # Ring Outward makes the inward segment full length. Keep the bold
        # primitive in slot zero while assigning it that second segment so ring
        # attach/removal never has to replace or reorder scene items.
        bold_index = (
            1 if ring_center is not None and variant == DOUBLE_STYLE_OUTER else 0
        )
        bold_segment = segments[bold_index]
        other_segment = segments[1 - bold_index]
        bold_normal = normal_away_from_parallel_segment(
            bold_segment, other_segment, *normal
        )
        endpoint_ids = (
            (bond.a, bond.b) if ring_center is not None and bold_index == 0 else None
        )
        return (
            self._bold_strip(
                bold_segment,
                bold_normal,
                endpoint_ids=endpoint_ids,
            ),
            self._line(other_segment),
        )

    def _bold_primitives(self, bond, a, b) -> tuple[BondPrimitive, ...]:
        bold_outward = bond.style == "bold_out"
        if bond.order == 2:
            return self._bold_double_primitives(bond, a, b)
        if bond.order >= 2:
            segments = self.renderer.parallel_bond_segments(
                a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b
            )
            first_segment = segments[0]
            normal = self.renderer.line_normal(*first_segment, None)
            if bold_outward:
                normal = (-normal[0], -normal[1])
            return (
                self._bold_strip(first_segment, normal),
                *(self._line(segment) for segment in segments[1:]),
            )

        segment = (a.x, a.y, b.x, b.y)
        ring_center = self.renderer.ring_center_for_bond(bond)
        normal = self.renderer.line_normal(*segment, ring_center)
        if bold_outward:
            normal = (-normal[0], -normal[1])
        return (
            self._bold_strip(
                segment,
                normal,
                endpoint_ids=(bond.a, bond.b),
            ),
        )

    def _plain_double_primitives(self, bond, a, b) -> tuple[BondPrimitive, ...]:
        variant = normalized_plain_double_style(bond.style, bond.order)
        _, (outer_segment, inner_segment, _) = self._double_segments(
            bond, a, b, style=variant
        )
        return self._line(outer_segment), self._line(inner_segment)

    def _parallel_primitives(self, bond, a, b) -> tuple[BondPrimitive, ...]:
        segments = self.renderer.parallel_bond_segments(
            a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b
        )
        return tuple(self._line(segment) for segment in segments)

    def _single_primitives(self, bond, a, b) -> tuple[BondPrimitive, ...]:
        t0, t1 = self.renderer.trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
        return (
            self._line(
                (
                    a.x + (b.x - a.x) * t0,
                    a.y + (b.y - a.y) * t0,
                    a.x + (b.x - a.x) * t1,
                    a.y + (b.y - a.y) * t1,
                )
            ),
        )

    def primitives_for_bond(
        self,
        bond,
        a,
        b,
        *,
        topology_count: int | None = None,
    ) -> tuple[BondPrimitive, ...]:
        if bond.style == "wedge":
            return self._wedge_primitives(bond, a, b)
        if bond.style == "hash":
            return self._hash_primitives(
                bond,
                a,
                b,
                topology_count=topology_count,
            )
        if bond.style == "dotted":
            return self._dotted_primitives(bond, a, b)
        if is_dotted_double_bond_style(bond.style, bond.order):
            return self._dotted_double_primitives(bond, a, b)
        if bond.style in BOLD_BOND_STYLES:
            return self._bold_primitives(bond, a, b)
        if is_plain_double_bond_style(bond.style, bond.order):
            return self._plain_double_primitives(bond, a, b)
        if bond.order >= 2:
            return self._parallel_primitives(bond, a, b)
        return self._single_primitives(bond, a, b)


__all__ = [
    "BondGeometryPlanService",
    "BondLinePrimitive",
    "BondPathPrimitive",
    "BondPolygonPrimitive",
    "BondPrimitive",
]
