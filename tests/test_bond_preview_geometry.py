from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsLineItem
from ui.bond_preview_geometry import (
    apply_plain_double_preview_variant,
    expanded_bold_segment,
    plain_double_preview_segments,
    trim_segment,
)


def test_bond_preview_geometry_expands_and_trims_segments() -> None:
    expanded = expanded_bold_segment(QPointF(0.0, 0.0), QPointF(10.0, 0.0), 20.0)

    assert math.isclose(expanded[0], -1.65)
    assert math.isclose(expanded[2], 11.65)
    assert trim_segment((0.0, 0.0, 10.0, 0.0), 2.0) == (2.0, 0.0, 8.0, 0.0)


def test_plain_double_preview_segments_and_item_application() -> None:
    segments = ((0.0, -2.0, 10.0, -2.0), (0.0, 2.0, 10.0, 2.0))

    default_segments = plain_double_preview_segments(segments, "double")
    centered_segments = plain_double_preview_segments(segments, "double_center")

    assert default_segments[0] == (0.0, 0.0, 10.0, 0.0)
    assert centered_segments != segments

    items = [
        QGraphicsLineItem(*segments[0]),
        QGraphicsLineItem(*segments[1]),
    ]
    assert apply_plain_double_preview_variant(items, "double") is items
    assert items[0].line().y1() == 0.0
