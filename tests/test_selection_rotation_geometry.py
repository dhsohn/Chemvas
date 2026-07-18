from __future__ import annotations

import math

from chemvas.features.selection import (
    axis_rotated_coords,
    center_for_coords_3d,
    dominant_axis_angle_from_drag,
    flatten_coords_to_plane,
    fragment_plane_normal_for,
    normalize_3d,
    rigid_rotated_coords,
    rigid_rotation_angles_from_drag,
    rotate_point_around_axis,
)


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
