from __future__ import annotations

from chemvas.features.rendering import (
    hash_segments_from_segment,
    trimmed_line_segment,
    wedge_polygon_from_segment,
)


def test_trimmed_line_segment_applies_parametric_bounds() -> None:
    assert trimmed_line_segment(0.0, 0.0, 10.0, 4.0, t0=0.2, t1=0.8) == (
        2.0,
        0.8,
        8.0,
        3.2,
    )


def test_wedge_polygon_from_segment_uses_narrow_start_and_wide_end() -> None:
    polygon = wedge_polygon_from_segment((0.0, 0.0, 10.0, 0.0), max_width=4.0)

    assert polygon.count() == 3
    assert polygon[0].x() == 1.0
    assert polygon[0].y() == 0.0
    assert polygon[1].x() == 10.0
    assert polygon[2].x() == 10.0
    assert polygon[1].y() > polygon[2].y()


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
