from __future__ import annotations

from chemvas.features.rendering import (
    hash_segments_from_segment,
    trimmed_line_segment,
    wedge_triangle_from_segment,
)


def test_trimmed_line_segment_applies_parametric_bounds() -> None:
    assert trimmed_line_segment(0.0, 0.0, 10.0, 4.0, t0=0.2, t1=0.8) == (
        2.0,
        0.8,
        8.0,
        3.2,
    )


def test_wedge_triangle_from_segment_uses_narrow_start_and_wide_end() -> None:
    tip, wide_a, wide_b = wedge_triangle_from_segment(
        (0.0, 0.0, 10.0, 0.0), max_width=4.0
    )

    assert tip == (1.0, 0.0)
    assert wide_a[0] == 10.0
    assert wide_b[0] == 10.0
    assert wide_a[1] > wide_b[1]


def test_hash_segments_from_segment_scales_dashes_along_bond() -> None:
    single = hash_segments_from_segment((0.0, 0.0, 10.0, 0.0), count=1, max_size=4.0)
    multiple = hash_segments_from_segment((0.0, 0.0, 10.0, 0.0), count=3, max_size=4.0)

    assert len(single) == 1
    assert len(multiple) == 3
    assert single[0][0] == 5.0
    assert single[0][2] == 5.0
    first_height = abs(multiple[0][3] - multiple[0][1])
    last_height = abs(multiple[-1][3] - multiple[-1][1])
    assert first_height < last_height
