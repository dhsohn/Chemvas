from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QFont, QRawFont, QTransform
from PyQt6.QtWidgets import QApplication, QGraphicsItem, QGraphicsTextItem

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.features.document_composition import compose_document_state
from chemvas.features.export import (
    ExportPlan,
    collect_export_items,
    svg_viewport_size_points,
)
from chemvas.features.export.vector import render_svg_bytes
from chemvas.ui.canvas_scene_items_state import note_items_for, ts_bracket_items_for
from chemvas.ui.export_readability_service import assess_export_readability
from chemvas.ui.scene_decoration_build_access import build_ts_bracket_item_for
from chemvas.ui.scene_item_access import apply_scene_item_state, canvas_scene_for
from chemvas.ui.scene_item_state_serialization import scene_item_state_for


@pytest.fixture(scope="module", autouse=True)
def application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    app.setQuitOnLastWindowClosed(False)
    return app


def _state(**records: object) -> dict:
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
            **records,
        }
    )


def _plan() -> ExportPlan:
    return ExportPlan(
        source_x=0,
        source_y=0,
        source_w=100,
        source_h=100,
        out_w_pt=100,
        out_h_pt=100,
    )


def _assess(
    canvas,
    *,
    plan: ExportPlan | None = None,
    minimum: float = 0.1,
    output_format: str = "png",
):
    plan = plan or _plan()
    return assess_export_readability(
        canvas,
        plan,
        minimum_font_pt=minimum,
        output_format=output_format,
        dpi=72,
        width_pixels=round(plan.out_w_pt),
        height_pixels=round(plan.out_h_pt),
    )


def test_resolved_font_pixels_not_declared_points_control_the_minimum() -> None:
    state = _state(notes=[{"text": "H", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        note = note_items_for(canvas)[0]
        note.setFont(QFont("DejaVu Sans", 12))
        expected = QRawFont.fromFont(note.font()).pixelSize()
        report = _assess(canvas, minimum=expected)
        assert report["minimum_font_pt"] == pytest.approx(expected)
        assert report["minimum_witness"] == {
            "kind": "note",
            "index": 0,
            "script": False,
        }
        assert report["coverage"]["note"]["glyphs"] == 1
        with pytest.raises(ValueError, match="below --min-font-pt"):
            _assess(canvas, minimum=expected + 0.01)


def test_rich_text_scripts_and_small_spans_use_resolved_runs() -> None:
    state = _state(notes=[{"text": "placeholder", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        note = note_items_for(canvas)[0]
        note.setFont(QFont("DejaVu Sans", 12))
        note.setHtml('H<sub>2</sub>O<sup>+</sup><span style="font-size:6pt">x</span>')
        report = _assess(canvas)
        assert report["coverage"]["note_script"]["glyphs"] == 2
        assert report["coverage"]["note"]["glyphs"] == 3
        small_font = QFont(note.font())
        small_font.setPointSizeF(6)
        assert report["minimum_font_pt"] == QRawFont.fromFont(small_font).pixelSize()
        assert (
            report["coverage"]["note_script"]["minimum_pt"] > report["minimum_font_pt"]
        )


def test_custom_atom_scripts_and_arrow_scripts_and_ts_glyph_are_covered() -> None:
    state = _state(
        atoms=[{"id": 0, "element": "NH4+", "x": 10, "y": 20}],
        arrows=[
            {
                "kind": "arrow",
                "start": [40, 20],
                "end": [100, 20],
                "labels": {"above": "k_1", "below": "G^‡"},
            }
        ],
        ts_brackets=[
            {
                "left": 130,
                "top": 0,
                "right": 150,
                "bottom": 40,
                "bracket_kind": "double_dagger",
            }
        ],
    )
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        report = _assess(canvas)
        assert report["coverage"]["atom_script"]["glyphs"] == 1
        assert report["coverage"]["arrow_script"]["glyphs"] == 2
        assert report["coverage"]["ts_bracket"]["glyphs"] == 1
        assert (
            report["coverage"]["atom_script"]["minimum_pt"]
            < report["coverage"]["atom"]["minimum_pt"]
        )
        bracket = ts_bracket_items_for(canvas)[0]
        text, font = bracket.export_glyph_run()
        assert text == "‡"
        assert (
            report["coverage"]["ts_bracket"]["minimum_pt"]
            == QRawFont.fromFont(font).pixelSize()
        )
        bracket.setPath(bracket.path())
        with pytest.raises(ValueError, match="construction font"):
            _assess(canvas)


@pytest.mark.parametrize("bracket_kind", ["dagger", "double_dagger"])
@pytest.mark.parametrize("output_format", ["svg", "png"])
def test_native_ts_rebuild_refreshes_glyph_font_and_restores_it(
    bracket_kind: str, output_format: str
) -> None:
    state = _state(
        ts_brackets=[
            {
                "left": 10,
                "top": 10,
                "right": 30,
                "bottom": 50,
                "bracket_kind": bracket_kind,
            }
        ]
    )
    with offscreen_canvas(state, command="test-native-ts-font") as (canvas, _):
        item = ts_bracket_items_for(canvas)[0]
        original = scene_item_state_for(canvas, item)
        assert original is not None
        for rect in (
            QRectF(40, 20, 20, 40),
            QRectF(40, 20, 40, 16),
            QRectF(10, 10, 20, 40),
        ):
            rebuilt = dict(
                original,
                left=rect.left(),
                top=rect.top(),
                right=rect.right(),
                bottom=rect.bottom(),
            )
            apply_scene_item_state(canvas, item, rebuilt)
            fresh = build_ts_bracket_item_for(canvas, rect, bracket_kind)
            assert item.path() == fresh.path()
            text, font = fresh.export_glyph_run()
            report = _assess(canvas, output_format=output_format)
            actual_text, actual_font = item.export_glyph_run()
            assert actual_text == text and actual_font == font
            assert (
                report["coverage"]["ts_bracket"]["minimum_pt"]
                == QRawFont.fromFont(font).pixelSize()
            )
        assert scene_item_state_for(canvas, item) == original


def test_hidden_transparent_and_whitespace_text_are_not_missing_measurements() -> None:
    state = _state(
        notes=[{"text": " ", "x": 0, "y": 0}, {"text": "Hidden", "x": 20, "y": 0}]
    )
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        note_items_for(canvas)[1].setVisible(False)
        report = _assess(canvas, minimum=100)
        assert report["status"] == "no-visible-text"
        assert report["minimum_font_pt"] is None
        assert report["coverage"] == {}
        note_items_for(canvas)[0].setHtml(
            '<span style="color:transparent">hidden</span>'
        )
        assert _assess(canvas)["status"] == "no-visible-text"


def test_uniform_parent_transform_and_rotation_preserve_the_measurement() -> None:
    state = _state(notes=[{"text": "H", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        note = note_items_for(canvas)[0]
        first = _assess(canvas)["minimum_font_pt"]
        note.setRotation(73)
        note.setScale(2)
        assert _assess(canvas)["minimum_font_pt"] == pytest.approx(first * 2)


@pytest.mark.parametrize(
    "transform",
    [QTransform().scale(2, 1), QTransform().shear(0.2, 0), QTransform().scale(-1, 1)],
)
def test_unsupported_transforms_are_refused(transform: QTransform) -> None:
    state = _state(notes=[{"text": "H", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        note_items_for(canvas)[0].setTransform(transform)
        with pytest.raises(ValueError, match="uniform-scale/rotation"):
            _assess(canvas)


def test_view_dependent_text_is_refused() -> None:
    state = _state(notes=[{"text": "H", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        note_items_for(canvas)[0].setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        )
        with pytest.raises(ValueError, match="view-dependent"):
            _assess(canvas)


def test_svg_point_rounding_affects_the_final_minimum() -> None:
    state = _state(notes=[{"text": "H", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        first = _assess(canvas, output_format="svg")["minimum_font_pt"]
        plan = replace(_plan(), out_w_pt=100.49, out_h_pt=100.49)
        assert _assess(canvas, plan=plan, output_format="svg")[
            "minimum_font_pt"
        ] == pytest.approx(first)
        assert svg_viewport_size_points(plan) == (100, 100)
        plan = replace(plan, out_w_pt=100.51, out_h_pt=100.51)
        assert _assess(canvas, plan=plan, output_format="svg")[
            "minimum_font_pt"
        ] == pytest.approx(first * 1.01)


def test_svg_and_png_share_the_resolved_native_note_glyph_size() -> None:
    state = _state(notes=[{"text": "H", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        note_items_for(canvas)[0].setFont(QFont("DejaVu Sans", 12))
        report = _assess(canvas, output_format="svg")
        assert report == _assess(canvas, output_format="png")
        assert report["minimum_font_pt"] == pytest.approx(16)
        assert report["minimum_witness"] == {
            "kind": "note",
            "index": 0,
            "script": False,
        }
        with pytest.raises(ValueError, match="below --min-font-pt 16.1"):
            _assess(canvas, minimum=16.1, output_format="svg")


def test_svg_mixed_pixel_point_and_script_sizes_follow_native_glyphs() -> None:
    state = _state(notes=[{"text": "placeholder", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        note = note_items_for(canvas)[0]
        note.setFont(QFont("DejaVu Sans", 12))
        note.setHtml(
            '<span style="font-size:9px">A</span><span style="font-size:9pt">B</span>H<sub>2</sub>'
        )
        report = _assess(canvas, output_format="svg")
        assert report == _assess(canvas, output_format="png")
        assert report["coverage"]["note"]["glyphs"] == 3
        assert report["coverage"]["note_script"]["glyphs"] == 1
        assert report["minimum_font_pt"] == pytest.approx(9)
        note.setScale(2)
        note.setRotation(37)
        assert _assess(canvas, output_format="svg")["minimum_font_pt"] == pytest.approx(
            18
        )


def test_automatic_list_markers_match_native_svg_pixel_fonts() -> None:
    state = _state(notes=[{"text": "placeholder", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        note = note_items_for(canvas)[0]
        note.setFont(QFont("DejaVu Sans", 12))
        note.setHtml(
            '<ol><li style="font-size:6pt"><span style="font-size:12pt">H</span></li></ol>'
        )
        scene = canvas_scene_for(canvas)
        content = render_svg_bytes(
            scene, collect_export_items(scene), _plan(), "white", "fixture"
        )
        texts = [e for e in ET.fromstring(content).iter() if e.tag.endswith("}text")]
        assert [(e.text, float(e.attrib["font-size"])) for e in texts] == [("1.", 8)]
        report = _assess(canvas, output_format="svg")
        assert report == _assess(canvas, output_format="png")
        assert report["coverage"]["note"]["glyphs"] == 3
        assert report["minimum_font_pt"] == 8
        with pytest.raises(ValueError, match="below --min-font-pt 8.1"):
            _assess(canvas, output_format="svg", minimum=8.1)


def test_noncanonical_visible_text_is_rejected_only_by_the_opt_in_guard() -> None:
    with offscreen_canvas(_state(), command="test-readability") as (canvas, _):
        item = QGraphicsTextItem("custom")
        item.setData(0, "custom-text")
        canvas_scene_for(canvas).addItem(item)
        with pytest.raises(ValueError, match="canonical export typography"):
            _assess(canvas, output_format="svg")
        item.setPlainText(" ")
        assert _assess(canvas, output_format="svg")["status"] == "no-visible-text"


def test_no_visible_text_svg_has_explicit_empty_coverage() -> None:
    state = _state(notes=[{"text": " ", "x": 0, "y": 0}])
    with offscreen_canvas(state, command="test-readability") as (canvas, _):
        report = _assess(canvas, output_format="svg", minimum=100)
        assert report["status"] == "no-visible-text"
        assert report["minimum_font_pt"] is None
        assert report["coverage"] == {}


@pytest.mark.parametrize("minimum", [0, -1, float("nan"), float("inf")])
def test_invalid_direct_threshold_is_refused(minimum: float) -> None:
    with offscreen_canvas(_state(), command="test-readability") as (canvas, _):
        with pytest.raises(ValueError, match="positive finite"):
            _assess(canvas, minimum=minimum)
