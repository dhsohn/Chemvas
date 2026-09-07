from __future__ import annotations

import math

import pytest

from chemvas.features.selection import (
    axis_rotated_coords,
    center_for_coords_3d,
    dominant_axis_angle_from_drag,
    flatten_coords_to_plane,
    fragment_plane_normal_for,
    normalize_3d,
    project_point_3d,
    rigid_rotated_coords,
    rigid_rotation_angles_from_drag,
    rotate_point_around_axis,
    translate_projected_point_3d,
    unproject_point_3d,
)


@pytest.mark.parametrize("bond_length_px", [10.0, 40.0])
@pytest.mark.parametrize(
    ("depth_ratio", "scale"),
    [(-100.0, 1 / 1.8), (-0.8, 1 / 1.8), (0.0, 1.0), (0.7, 1 / 0.3), (100.0, 1 / 0.3)],
)
def test_projection_inverse_and_screen_translation_share_clamped_depth(
    bond_length_px, depth_ratio, scale
) -> None:
    focal = max(bond_length_px * 8.0, 120.0)
    center = (10.0, -5.0, 100.0)
    anchor = (20.0, 30.0)
    point = (13.0, 7.0, center[2] + depth_ratio * focal)
    frame = dict(bond_length_px=bond_length_px, center_3d=center, anchor_2d=anchor)
    projected = project_point_3d(point, **frame)

    assert projected == pytest.approx((20.0 + 3.0 * scale, 30.0 + 12.0 * scale))
    assert unproject_point_3d(projected, point[2], **frame) == pytest.approx(point)
    moved = translate_projected_point_3d(
        point, 9.0, -6.0, bond_length_px=bond_length_px, center_3d=center
    )
    assert moved[2] == point[2]
    assert project_point_3d(moved, **frame) == pytest.approx(
        (projected[0] + 9.0, projected[1] - 6.0)
    )
    assert translate_projected_point_3d(
        moved, -9.0, 6.0, bond_length_px=bond_length_px, center_3d=center
    ) == pytest.approx(point)


def test_projection_without_camera_is_identity_and_keeps_depth() -> None:
    frame = dict(bond_length_px=20.0, center_3d=None, anchor_2d=(100.0, 200.0))
    assert project_point_3d((3.0, 7.0, 11.0), **frame) == (3.0, 7.0)
    assert unproject_point_3d((3.0, 7.0), 11.0, **frame) == (3.0, 7.0, 11.0)
    assert translate_projected_point_3d(
        (3.0, 7.0, 11.0), 9.0, -6.0, bond_length_px=20.0, center_3d=None
    ) == (12.0, 1.0, 11.0)


def test_projection_without_anchor_uses_the_camera_center() -> None:
    frame = dict(bond_length_px=20.0, center_3d=(10.0, 20.0, 30.0), anchor_2d=None)
    projected = project_point_3d((13.0, 27.0, 30.0), **frame)
    assert projected == (13.0, 27.0)
    assert unproject_point_3d(projected, 30.0, **frame) == (13.0, 27.0, 30.0)


def test_selection_reexports_the_bond_geometry_normalize_3d() -> None:
    """Rotation callers import it from `features.selection`.

    Bond geometry owns the implementation so that `features.rendering` stays
    importable without Qt; this keeps the selection import path a re-export of
    the same object rather than a second copy.
    """
    from chemvas.features.rendering import normalize_3d as rendering_normalize_3d

    assert normalize_3d is rendering_normalize_3d


def test_normalize_and_center_for_coords_3d_cover_empty_and_valid_inputs() -> None:
    assert normalize_3d(0.0, 0.0, 0.0) is None
    assert normalize_3d(0.0, 3.0, 4.0) == (0.0, 0.6, 0.8)

    assert center_for_coords_3d(set(), {}) is None
    assert center_for_coords_3d({1, 2}, {3: (1.0, 2.0, 3.0)}) is None
    assert center_for_coords_3d(
        {1, 2},
        {
            1: (0.0, 2.0, 4.0),
            2: (2.0, 4.0, 8.0),
        },
    ) == (1.0, 3.0, 6.0)


def test_fragment_plane_normal_handles_valid_degenerate_and_collinear_points() -> None:
    assert (
        fragment_plane_normal_for({1, 2}, {1: (0.0, 0.0, 0.0), 2: (1.0, 0.0, 0.0)})
        is None
    )
    assert fragment_plane_normal_for(
        {1, 2, 3},
        {
            1: (0.0, 0.0, 0.0),
            2: (1.0, 0.0, 0.0),
            3: (2.0, 0.0, 0.0),
        },
    ) == (0.0, 0.0, 1.0)

    normal = fragment_plane_normal_for(
        {1, 2, 3},
        {
            1: (0.0, 0.0, 0.0),
            2: (1.0, 0.0, 0.0),
            3: (0.0, 1.0, 1.0),
        },
    )
    assert normal is not None
    assert math.isclose(
        math.sqrt(sum(component * component for component in normal)), 1.0
    )


def test_flatten_coords_to_plane_projects_known_atoms_and_preserves_missing_atoms() -> (
    None
):
    flattened = flatten_coords_to_plane(
        {
            1: (0.0, 0.0, 2.0),
            2: (1.0, 0.0, -1.0),
            4: (10.0, 0.0, 5.0),
        },
        {1, 2, 3},
        normal=(0.0, 0.0, 1.0),
        centroid=(0.0, 0.0, 0.0),
    )

    assert flattened[1] == (0.0, 0.0, 0.0)
    assert flattened[2] == (1.0, 0.0, 0.0)
    assert flattened[4] == (10.0, 0.0, 5.0)
    assert 3 not in flattened


def test_rotate_point_around_axis_handles_zero_axis_and_right_angle_rotation() -> None:
    point = (2.0, 3.0, 4.0)
    assert (
        rotate_point_around_axis(point, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), math.pi)
        == point
    )

    rotated = rotate_point_around_axis(
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        math.pi / 2.0,
    )

    assert math.isclose(rotated[0], 0.0, abs_tol=1e-9)
    assert math.isclose(rotated[1], 1.0, abs_tol=1e-9)
    assert math.isclose(rotated[2], 0.0, abs_tol=1e-9)


def test_drag_angle_helpers_map_pointer_delta_to_rotation_angles() -> None:
    assert rigid_rotation_angles_from_drag(40.0, 20.0) == (0.1, 0.2)
    assert dominant_axis_angle_from_drag(40.0, 20.0) == 0.2
    assert dominant_axis_angle_from_drag(10.0, -30.0) == -0.15


def test_rigid_rotated_coords_rotates_known_atoms_and_skips_missing_coords() -> None:
    rotated = rigid_rotated_coords(
        {1, 2, 3},
        {
            1: (1.0, 0.0, 0.0),
            2: (0.0, 2.0, 0.0),
        },
        (0.0, 0.0, 0.0),
        angle_x=0.1,
        angle_y=0.2,
    )

    cos_y = math.cos(0.2)
    sin_y = math.sin(0.2)
    cos_x = math.cos(0.1)
    sin_x = math.sin(0.1)
    assert set(rotated) == {1, 2}
    assert math.isclose(rotated[1][0], cos_y)
    assert math.isclose(rotated[1][1], sin_y * sin_x)
    assert math.isclose(rotated[1][2], (-sin_y) * cos_x)
    assert math.isclose(rotated[2][0], 0.0)
    assert math.isclose(rotated[2][1], 2.0 * cos_x)
    assert math.isclose(rotated[2][2], 2.0 * sin_x)


def test_axis_rotated_coords_uses_injected_rotation_callback_and_skips_missing_coords() -> (
    None
):
    calls: list[
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
            float,
        ]
    ] = []

    def rotate(point, axis_start, axis_end, angle):
        calls.append((point, axis_start, axis_end, angle))
        return point[0] + angle, point[1] - angle, point[2] + 1.0

    rotated = axis_rotated_coords(
        {1, 2},
        {1: (3.0, 4.0, 5.0)},
        (0.0, 0.0, 0.0),
        (10.0, 0.0, 0.0),
        0.25,
        rotate_point=rotate,
    )

    assert calls == [((3.0, 4.0, 5.0), (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), 0.25)]
    assert rotated == {1: (3.25, 3.75, 6.0)}
