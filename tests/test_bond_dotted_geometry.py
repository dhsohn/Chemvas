from __future__ import annotations

from chemvas.features.rendering import dotted_bond_path_from_trimmed_segment


def test_dotted_bond_path_handles_zero_length_and_trim_scaling() -> None:
    zero = dotted_bond_path_from_trimmed_segment(
        1.0,
        2.0,
        1.0,
        2.0,
        start_trim=0.0,
        end_trim=0.0,
        dot_radius=1.0,
        target_spacing=4.0,
    )
    assert zero.elementCount() > 0
    assert zero.boundingRect().center().x() == 1.0
    assert zero.boundingRect().center().y() == 2.0

    scaled = dotted_bond_path_from_trimmed_segment(
        0.0,
        0.0,
        10.0,
        0.0,
        start_trim=9.0,
        end_trim=9.0,
        dot_radius=1.0,
        target_spacing=4.0,
    )
    assert scaled.elementCount() > 0
    assert 0.0 < scaled.boundingRect().center().x() < 10.0


def test_dotted_bond_path_places_multiple_dots_on_usable_segment() -> None:
    path = dotted_bond_path_from_trimmed_segment(
        0.0,
        0.0,
        20.0,
        0.0,
        start_trim=2.0,
        end_trim=2.0,
        dot_radius=1.0,
        target_spacing=4.0,
    )

    assert path.elementCount() > 4
    bounds = path.boundingRect()
    assert bounds.left() >= 1.0
    assert bounds.right() <= 19.0
