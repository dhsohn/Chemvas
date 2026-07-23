from __future__ import annotations

from chemvas.features.rendering import plain_double_preview_segments


def test_plain_double_preview_positions_keep_one_long_segment() -> None:
    segments = ((0.0, -2.0, 10.0, -2.0), (0.0, 2.0, 10.0, 2.0))

    inward = plain_double_preview_segments(segments, "double")
    outward = plain_double_preview_segments(segments, "double_outer")
    centered = plain_double_preview_segments(segments, "double_center")

    assert inward[0] == (0.0, 0.0, 10.0, 0.0)
    assert (inward[1][1], inward[1][3]) == (4.4, 4.4)
    assert outward[0] == (0.0, 0.0, 10.0, 0.0)
    assert (outward[1][1], outward[1][3]) == (-4.4, -4.4)
    assert (centered[0][1], centered[1][1]) == (-2.2, 2.2)


def test_plain_double_preview_policy_passes_through_non_pairs() -> None:
    segment = (0.0, 0.0, 10.0, 0.0)

    assert plain_double_preview_segments((segment,), "double") == (segment,)
