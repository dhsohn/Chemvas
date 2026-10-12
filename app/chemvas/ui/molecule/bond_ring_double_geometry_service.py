from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chemvas.domain.document import Bond
from chemvas.features.rendering import (
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    normalize_3d,
    normalized_plain_double_style,
)
from chemvas.features.selection import translate_projected_point_3d

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
        spacing = self.context.renderer.bond_spacing() * 1.1
        variant = normalized_plain_double_style(style, 2)
        fractions = (
            (-0.5, 0.5)
            if variant == "double_center"
            else (0.0, -1.0)
            if variant == DOUBLE_STYLE_OUTER
            else (0.0, 1.0)
        )
        screen_dx, screen_dy = (
            base_outer[2] - base_outer[0],
            base_outer[3] - base_outer[1],
        )
        screen_length = math.hypot(screen_dx, screen_dy) or 1.0
        spans = []
        for fraction in fractions:
            points = []
            for point, other, atom_id, other_id, direction in (
                (base_a3, base_b3, a_id, b_id, 1),
                (base_b3, base_a3, b_id, a_id, -1),
            ):
                shifted = tuple(
                    point[i] + inward_unit3[i] * spacing * fraction for i in range(3)
                )
                x, y = project(shifted)
                px, py = project(point)
                projected_spacing = math.hypot(x - px, y - py)
                inset = 0.0
                if projected_spacing > 1e-9:
                    cot = (
                        self.renderer.line_geometry._double_endpoint_cotangent(
                            atom_id,
                            other_id,
                            screen_dx * direction,
                            screen_dy * direction,
                            (x - px) / projected_spacing,
                            (y - py) / projected_spacing,
                        )
                        or 0.0
                    )
                    inset = min(0.45, projected_spacing * cot / screen_length)
                trimmed = tuple(
                    shifted[i] + (other[i] - point[i]) * inset for i in range(3)
                )
                points.append(project(trimmed))
            spans.append((*points[0], *points[1]))
        offset_x = (spans[1][0] + spans[1][2] - spans[0][0] - spans[0][2]) * 0.5
        offset_y = (spans[1][1] + spans[1][3] - spans[0][1] - spans[0][3]) * 0.5
        offset_length = math.hypot(offset_x, offset_y)
        if offset_length <= 1e-9:
            return None
        # Return the inward normal independently of the selected outside stroke.
        sign = -1 if variant == DOUBLE_STYLE_OUTER else 1
        return (
            spans[0],
            spans[1],
            (sign * offset_x / offset_length, sign * offset_y / offset_length),
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

        return self.renderer.line_geometry.native_double_segments(
            a.x,
            a.y,
            b.x,
            b.y,
            style=style,
            normal=(nx, ny),
            a_id=a_id,
            b_id=b_id,
        )
