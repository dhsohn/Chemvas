from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chemvas.domain.document import Bond
from chemvas.features.rendering import (
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    normalize_3d,
    normalized_plain_double_style,
    trim_segment,
)
from chemvas.features.selection import translate_projected_point_3d
from chemvas.ui.molecule.bond_line_geometry_service import double_short_trim

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF

    from chemvas.ui.scene.scene_render_context import SceneRenderContext


class BondRingDoubleGeometryService:
    def __init__(self, context: SceneRenderContext, *, renderer) -> None:
        self.context = context
        self.renderer = renderer

    def _has_label(self, a_id: int | None, b_id: int | None) -> bool:
        return (
            a_id is not None and self.renderer.label_rect_for_atom(a_id) is not None
        ) or (b_id is not None and self.renderer.label_rect_for_atom(b_id) is not None)

    def _projected_3d_segments(
        self,
        a,
        b,
        *,
        center: QPointF,
        center_3d: tuple[float, float, float],
        a_id: int,
        b_id: int,
        style: str,
    ) -> (
        tuple[
            tuple[float, float, float, float],
            tuple[float, float, float, float],
            tuple[float, float],
        ]
        | None
    ):
        coords_a = self.renderer.current_atom_coords_3d(a_id)
        coords_b = self.renderer.current_atom_coords_3d(b_id)
        if coords_a is None or coords_b is None:
            return None

        # Screen translation shears stored 3D coordinates by depth. Remove that
        # translation before measuring normals/spacing, then put it back after
        # projection. Moving a ring must not change its inner bond geometry.
        rotation = self.context.state.rotation_state
        camera = rotation.projection_center_3d
        offset = (0.0, 0.0)
        if camera is not None:
            anchor = rotation.projection_anchor_2d or camera[:2]
            offset = (center.x() - anchor[0], center.y() - anchor[1])

            def centered(point):
                return translate_projected_point_3d(
                    point,
                    -offset[0],
                    -offset[1],
                    bond_length_px=self.context.renderer.style.bond_length_px,
                    center_3d=camera,
                )

            coords_a, coords_b = centered(coords_a), centered(coords_b)
            # Transform vertices before averaging: depth clamping makes the
            # inverse scale of an average differ from the average inverse scale.
            center_3d = self.context.geometry.ring_center_3d_for_bond(
                Bond(a_id, b_id), screen_delta=(-offset[0], -offset[1])
            ) or centered(center_3d)

        def project(point):
            x, y = self.renderer.project_point_3d(point)
            return x + offset[0], y + offset[1]

        ax3, ay3, az3 = coords_a
        bx3, by3, bz3 = coords_b
        bond_vec3 = (bx3 - ax3, by3 - ay3, bz3 - az3)
        bond_unit3 = normalize_3d(*bond_vec3)
        if bond_unit3 is None:
            return None

        t0, t1 = self.renderer.trim_line_for_labels(a_id, b_id, a.x, a.y, b.x, b.y)
        base_a3 = (
            ax3 + bond_vec3[0] * t0,
            ay3 + bond_vec3[1] * t0,
            az3 + bond_vec3[2] * t0,
        )
        base_b3 = (
            ax3 + bond_vec3[0] * t1,
            ay3 + bond_vec3[1] * t1,
            az3 + bond_vec3[2] * t1,
        )
        base_mid3 = (
            (base_a3[0] + base_b3[0]) * 0.5,
            (base_a3[1] + base_b3[1]) * 0.5,
            (base_a3[2] + base_b3[2]) * 0.5,
        )
        inward3 = (
            center_3d[0] - base_mid3[0],
            center_3d[1] - base_mid3[1],
            center_3d[2] - base_mid3[2],
        )
        dot = (
            inward3[0] * bond_unit3[0]
            + inward3[1] * bond_unit3[1]
            + inward3[2] * bond_unit3[2]
        )
        inward_perp3 = (
            inward3[0] - bond_unit3[0] * dot,
            inward3[1] - bond_unit3[1] * dot,
            inward3[2] - bond_unit3[2] * dot,
        )
        inward_unit3 = normalize_3d(*inward_perp3)
        if inward_unit3 is None:
            return None

        outer_a = project(base_a3)
        outer_b = project(base_b3)
        base_outer = (outer_a[0], outer_a[1], outer_b[0], outer_b[1])
        base_dx = base_outer[2] - base_outer[0]
        base_dy = base_outer[3] - base_outer[1]
        inner_length = math.hypot(base_dx, base_dy) or 1.0
        inner_trim = double_short_trim(
            inner_length, has_label=self._has_label(a_id, b_id)
        )
        trim_ratio = min(0.45, inner_trim / inner_length)
        trimmed_vec3 = (
            base_b3[0] - base_a3[0],
            base_b3[1] - base_a3[1],
            base_b3[2] - base_a3[2],
        )
        spacing = self.context.renderer.bond_spacing() * 1.1
        inner_full_a3 = (
            base_a3[0] + inward_unit3[0] * spacing,
            base_a3[1] + inward_unit3[1] * spacing,
            base_a3[2] + inward_unit3[2] * spacing,
        )
        inner_full_b3 = (
            base_b3[0] + inward_unit3[0] * spacing,
            base_b3[1] + inward_unit3[1] * spacing,
            base_b3[2] + inward_unit3[2] * spacing,
        )
        inner_a3 = (
            base_a3[0] + trimmed_vec3[0] * trim_ratio + inward_unit3[0] * spacing,
            base_a3[1] + trimmed_vec3[1] * trim_ratio + inward_unit3[1] * spacing,
            base_a3[2] + trimmed_vec3[2] * trim_ratio + inward_unit3[2] * spacing,
        )
        inner_b3 = (
            base_b3[0] - trimmed_vec3[0] * trim_ratio + inward_unit3[0] * spacing,
            base_b3[1] - trimmed_vec3[1] * trim_ratio + inward_unit3[1] * spacing,
            base_b3[2] - trimmed_vec3[2] * trim_ratio + inward_unit3[2] * spacing,
        )
        outer_a3 = (
            base_a3[0] + trimmed_vec3[0] * trim_ratio,
            base_a3[1] + trimmed_vec3[1] * trim_ratio,
            base_a3[2] + trimmed_vec3[2] * trim_ratio,
        )
        outer_b3 = (
            base_b3[0] - trimmed_vec3[0] * trim_ratio,
            base_b3[1] - trimmed_vec3[1] * trim_ratio,
            base_b3[2] - trimmed_vec3[2] * trim_ratio,
        )
        inner_full_a = project(inner_full_a3)
        inner_full_b = project(inner_full_b3)
        inner_a = project(inner_a3)
        inner_b = project(inner_b3)
        variant = normalized_plain_double_style(style, 2)
        outer_seg = base_outer
        inner_seg = (inner_a[0], inner_a[1], inner_b[0], inner_b[1])
        if variant == "double_center":
            inner_seg = (
                inner_full_a[0],
                inner_full_a[1],
                inner_full_b[0],
                inner_full_b[1],
            )
        elif variant == DOUBLE_STYLE_OUTER:
            outer_trim_a = project(outer_a3)
            outer_trim_b = project(outer_b3)
            outer_seg = (
                outer_trim_a[0],
                outer_trim_a[1],
                outer_trim_b[0],
                outer_trim_b[1],
            )
            inner_seg = (
                inner_full_a[0],
                inner_full_a[1],
                inner_full_b[0],
                inner_full_b[1],
            )
        # Foreshortening can make a nominal inset pass the nearest point to the
        # ring center. Limit that screen offset without changing line length or
        # direction, so narrow rings keep an inward second stroke.
        outer_mid = (
            (outer_seg[0] + outer_seg[2]) * 0.5,
            (outer_seg[1] + outer_seg[3]) * 0.5,
        )
        inset = (
            (inner_seg[0] + inner_seg[2]) * 0.5 - outer_mid[0],
            (inner_seg[1] + inner_seg[3]) * 0.5 - outer_mid[1],
        )
        squared = inset[0] ** 2 + inset[1] ** 2
        toward = (center.x() - outer_mid[0]) * inset[0] + (
            center.y() - outer_mid[1]
        ) * inset[1]
        if 0.0 < toward < squared:
            correction = toward / squared - 1.0
            inner_seg = (
                inner_seg[0] + correction * inset[0],
                inner_seg[1] + correction * inset[1],
                inner_seg[2] + correction * inset[0],
                inner_seg[3] + correction * inset[1],
            )
        offset_x = (inner_seg[0] + inner_seg[2]) * 0.5 - outer_mid[0]
        offset_y = (inner_seg[1] + inner_seg[3]) * 0.5 - outer_mid[1]
        offset_len = math.hypot(offset_x, offset_y)
        if offset_len <= 1e-9:
            return None
        return (
            outer_seg,
            inner_seg,
            (offset_x / offset_len, offset_y / offset_len),
        )

    def ring_double_segments(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        center_3d: tuple[float, float, float] | None = None,
        style: str = DOUBLE_STYLE_DEFAULT,
    ) -> tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float],
    ]:
        if center_3d is not None and a_id is not None and b_id is not None:
            projected = self._projected_3d_segments(
                a,
                b,
                center=center,
                center_3d=center_3d,
                a_id=a_id,
                b_id=b_id,
                style=style,
            )
            if projected is not None:
                return projected

        dx = b.x - a.x
        dy = b.y - a.y
        length = math.hypot(dx, dy) or 1.0
        ux = dx / length
        uy = dy / length
        nx = -dy / length
        ny = dx / length
        offset_unit = None
        if a_id is not None and b_id is not None:
            offset_unit = self.renderer.bond_offset_unit_3d(
                a_id,
                b_id,
                target=center_3d,
            )
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
            if center_3d is None:
                mid_x = (a.x + b.x) / 2.0
                mid_y = (a.y + b.y) / 2.0
                to_cx = center.x() - mid_x
                to_cy = center.y() - mid_y
                if nx * to_cx + ny * to_cy < 0:
                    nx = -nx
                    ny = -ny
        else:
            mid_x = (a.x + b.x) / 2.0
            mid_y = (a.y + b.y) / 2.0
            to_cx = center.x() - mid_x
            to_cy = center.y() - mid_y
            if nx * to_cx + ny * to_cy < 0:
                nx = -nx
                ny = -ny

        spacing = self.context.renderer.bond_spacing() * 1.1
        t0, t1 = self.renderer.trim_line_for_labels(
            a_id, b_id, a.x, a.y, b.x, b.y, ((0.0, 0.0), (nx * spacing, ny * spacing))
        )
        base_bx1 = a.x + dx * t0
        base_by1 = a.y + dy * t0
        base_bx2 = a.x + dx * t1
        base_by2 = a.y + dy * t1

        inner_length = math.hypot(base_bx2 - base_bx1, base_by2 - base_by1) or 1.0
        inner_trim = double_short_trim(
            inner_length, has_label=self._has_label(a_id, b_id)
        )
        inner_full_seg = (
            base_bx1 + nx * spacing,
            base_by1 + ny * spacing,
            base_bx2 + nx * spacing,
            base_by2 + ny * spacing,
        )
        inner_short_seg = (
            base_bx1 + ux * inner_trim + nx * spacing,
            base_by1 + uy * inner_trim + ny * spacing,
            base_bx2 - ux * inner_trim + nx * spacing,
            base_by2 - uy * inner_trim + ny * spacing,
        )
        outer_seg = (base_bx1, base_by1, base_bx2, base_by2)
        variant = normalized_plain_double_style(style, 2)
        if variant == "double_center":
            return outer_seg, inner_full_seg, (nx, ny)
        if variant == DOUBLE_STYLE_OUTER:
            return trim_segment(outer_seg, inner_trim), inner_full_seg, (nx, ny)
        return outer_seg, inner_short_seg, (nx, ny)


__all__ = ["BondRingDoubleGeometryService"]
