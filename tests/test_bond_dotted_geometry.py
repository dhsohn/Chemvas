from __future__ import annotations

from chemvas.features.rendering import dotted_bond_dot_centers


def test_dotted_bond_centers_handle_zero_length_and_trim_scaling() -> None:
    zero = dotted_bond_dot_centers(
        1.0,
        2.0,
        1.0,
        2.0,
        start_trim=0.0,
        end_trim=0.0,
        target_spacing=4.0,
    )
    assert zero == [(1.0, 2.0)]

    scaled = dotted_bond_dot_centers(
        0.0,
        0.0,
        10.0,
        0.0,
        start_trim=9.0,
        end_trim=9.0,
        target_spacing=4.0,
    )
    assert scaled
    assert all(0.0 < x < 10.0 for x, _y in scaled)


def test_dotted_bond_centers_place_multiple_dots_on_usable_segment() -> None:
    centers = dotted_bond_dot_centers(
        0.0,
        0.0,
        20.0,
        0.0,
        start_trim=2.0,
        end_trim=2.0,
        target_spacing=4.0,
    )

    assert len(centers) == 4
    xs = [x for x, _y in centers]
    assert xs == sorted(xs)
    assert min(xs) >= 2.0
    assert max(xs) <= 18.0
    assert all(y == 0.0 for _x, y in centers)
