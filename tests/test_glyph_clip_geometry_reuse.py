"""Cached render-only preparations agree with fresh scene-space clipping."""

import math
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from chemvas.ui import canvas_geometry_controller as geometry
from tests.test_atom_glyph_bond_clearance import _label_controller


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "text,placement",
    [
        ("O", "center"),
        ("N", "center"),
        ("CO2Me", "center"),
        ("NH2", "stack-below"),
        ("NH2", "stack-above"),
        ("H2N", "end"),
    ],
)
@pytest.mark.parametrize(
    "width,offsets", [(1.5, ()), (4.5, ()), (1.5, ((0, -2), (0, 2)))]
)
@pytest.mark.parametrize("transformed", [False, True])
def test_cached_glyph_clips_match_uncached_all_directions(
    text, placement, width, offsets, transformed
):
    item, controller = _label_controller(
        text, placement=placement, transformed=transformed
    )
    for translation in (QPointF(), QPointF(170.3, -102.7)):
        item.moveBy(translation.x(), translation.y())
        origin = item.mapToScene(
            item.anchor_center() or item.glyph_path().boundingRect().center()
        )
        for angle in range(0, 360, 30):
            end = origin + QPointF(
                80 * math.cos(math.radians(angle)), 80 * math.sin(math.radians(angle))
            )
            fresh = geometry._glyph_line_clip_t(
                origin, end, item.mapToScene(item.glyph_path()), width, offsets
            )
            cached = controller._clip_label_line(item, origin, end, width, offsets)
            if fresh is None:
                assert cached is None
            else:
                assert cached == pytest.approx(fresh, abs=1e-10)


@pytest.mark.parametrize(
    "change",
    [
        "font",
        "text",
        "margin",
        "stack",
        "scale",
        "rotation",
        "width",
        "position",
        "hit",
    ],
)
def test_glyph_cache_compares_current_ink_and_paint_width(change):
    item, controller = _label_controller("NH2", placement="start")
    p1, p2, width = QPointF(), QPointF(80, 0), 1.5
    controller._clip_label_line(item, p1, p2, width, ())
    if change == "font":
        item.setFont(QFont("DejaVu Sans", 20))
    elif change == "text":
        item.setPlainText("CO2Me")
    elif change == "margin":
        item.document().setDocumentMargin(8)
    elif change == "stack":
        item.set_stack_anchor("N", hydrogens_below=True)
    elif change == "scale":
        item.setScale(1.5)
    elif change == "rotation":
        item.setRotation(25)
    elif change == "width":
        width = 4.5
    elif change == "position":
        item.moveBy(20, 30)
        p1, p2 = p1 + QPointF(20, 30), p2 + QPointF(20, 30)
    else:
        item.set_hit_radius(100)
    with mock.patch.object(
        geometry, "_glyph_clearance_path", wraps=geometry._glyph_clearance_path
    ) as prepare:
        value = controller._clip_label_line(item, p1, p2, width, ())
    assert prepare.call_count == (0 if change in {"position", "hit"} else 1)
    fresh = geometry._glyph_line_clip_t(
        p1, p2, item.mapToScene(item.glyph_path()), width
    )
    assert (
        value == pytest.approx(fresh, abs=1e-10) if fresh is not None else value is None
    )
