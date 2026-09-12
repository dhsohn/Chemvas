"""Ring fusion uses the interior at its shared edge, including concave chairs."""

import math

import pytest

from chemvas.core.template_geometry import (
    cyclohexane_chair_flipped_points,
    cyclohexane_chair_points,
    place_template_on_bond,
    regular_ring_points_for_bond,
    ring_points,
)


def proper_crossings(first, second):
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    count = 0
    for a, b in zip(first, first[1:] + first[:1], strict=True):
        for c, d in zip(second, second[1:] + second[:1], strict=True):
            epsilon = max(math.dist(a, b), math.dist(c, d)) ** 2 * 1e-8
            ab_c, ab_d = cross(a, b, c), cross(a, b, d)
            cd_a, cd_b = cross(c, d, a), cross(c, d, b)
            opposite_ab = (ab_c > epsilon and ab_d < -epsilon) or (
                ab_c < -epsilon and ab_d > epsilon
            )
            opposite_cd = (cd_a > epsilon and cd_b < -epsilon) or (
                cd_a < -epsilon and cd_b > epsilon
            )
            count += opposite_ab and opposite_cd
    return count


def ring_shape(kind):
    if kind == "chair":
        return cyclohexane_chair_points((0, 0), 20)
    if kind == "chair_flip":
        return cyclohexane_chair_flipped_points((0, 0), 20)
    return ring_points((0, 0), 6, 20)


@pytest.mark.parametrize("existing", ["chair", "chair_flip", "regular"])
@pytest.mark.parametrize("incoming", [3, 4, 5, 6, 7, 8, "chair", "chair_flip"])
@pytest.mark.parametrize("edge", range(6))
@pytest.mark.parametrize("reverse_cycle", [False, True])
@pytest.mark.parametrize(
    "angle,scale,origin", [(0, 1, (0, 0)), (73, 0.125, (901.2, -712.3))]
)
def test_fusion_stays_outside_shared_edge(
    existing, incoming, edge, reverse_cycle, angle, scale, origin
):
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)
    occupied = [
        (
            origin[0] + scale * (x * cos - y * sin),
            origin[1] + scale * (x * sin + y * cos),
        )
        for x, y in ring_shape(existing)
    ]
    start, end = occupied[edge], occupied[(edge + 1) % 6]
    if reverse_cycle:
        occupied.reverse()
    if isinstance(incoming, int):
        result = regular_ring_points_for_bond(
            incoming, start, end, occupied_polygon=occupied
        )
    else:
        result = place_template_on_bond(
            ring_shape(incoming), start, end, occupied_polygon=occupied
        )

    assert result is not None
    assert proper_crossings(occupied, result) == 0
    assert result[0] == pytest.approx(start)
    assert result[1] == pytest.approx(end)
    expected_length = math.dist(start, end)
    assert all(
        math.dist(a, b) == pytest.approx(expected_length)
        for a, b in zip(result, result[1:] + result[:1], strict=True)
    )
    assert all(
        math.dist(point, old) > expected_length * 1e-7
        for point in result[2:]
        for old in occupied
    )
