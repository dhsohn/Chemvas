"""Script notes preserve meaning, painted size, placement and existing guards."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from PyQt6.QtCore import QPointF

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.ui.canvas.graphics_items import note_fragment_baseline_shift
from chemvas.ui.export.export_cdxml import CdxmlUnsupportedObjectError, serialize_cdxml
from chemvas.ui.export.figure_export_service import FigureExportService
from tests.test_cdxml_export import _resolved_export, _simple_state

pytestmark = pytest.mark.usefixtures("qt_application")


@pytest.mark.parametrize(
    "markup",
    [
        "<sub>2</sub>",
        "<sup>2</sup>",
        '<span style="vertical-align:sub">2</span>',
        '<span style="vertical-align:super">2</span>',
    ],
)
@pytest.mark.parametrize("bold", [False, True])
@pytest.mark.parametrize("rotation", [0, 30, 90])
def test_script_semantics_size_and_painted_baseline(markup, bold, rotation):
    html = (
        '<p><span style="font-family:Arial;color:#316699;font-weight:'
        + ("700" if bold else "400")
        + '">A'
        + markup
        + "Z</span></p>"
    )
    state = _simple_state(
        atoms={},
        bonds=[],
        notes=[dict(text="", html=html, x=20, y=30, rotation=rotation)],
    )
    with offscreen_document_scene(state, command="test-script") as context:
        note = context.state.note_items()[0]
        note.setRotation(rotation)
        items, plan = _resolved_export(context)
        before = note.document().toHtml()
        root = ET.fromstring(serialize_cdxml(context, items, plan))
        texts = root.findall("./page/t")
        assert ["".join(t.itertext()) for t in texts] == ["A", "2", "Z"]
        runs = [t.find("s") for t in texts]
        face = 32 if ("sub" in markup) else 64
        assert int(runs[1].get("face")) == face | int(bold)
        scale = plan.out_w_pt / plan.source_w
        block = note.document().begin()
        layout = block.layout()
        glyph = layout.glyphRuns(1, 1)[0]
        raw = glyph.rawFont()
        assert float(runs[1].get("size")) * 0.75 == pytest.approx(
            raw.pixelSize() * scale, abs=0.01875
        )
        # Undo the native script displacement and compare the actual common
        # painter's glyph origin (including Qt's fixed-point baseline shift).
        frag = block.begin()
        frag += 1
        fmt = frag.fragment().charFormat()
        position = (
            layout.position()
            + glyph.positions()[0]
            + QPointF(0, note_fragment_baseline_shift(fmt, raw))
        )
        expected = note.mapToScene(position)
        emitted = [float(x) for x in texts[1].get("p").split()]
        nominal = float(runs[1].get("size")) / scale
        descent = raw.descent() * nominal / raw.pixelSize()
        native_shift = descent if face == 32 else -(nominal - descent) / 2
        delta = note.sceneTransform().map(
            QPointF(0, native_shift)
        ) - note.sceneTransform().map(QPointF(0, 0))
        assert emitted[0] + delta.x() * scale == pytest.approx(
            (expected.x() - plan.source_x) * scale, abs=1e-7
        )
        assert emitted[1] + delta.y() * scale == pytest.approx(
            (expected.y() - plan.source_y) * scale, abs=1e-7
        )
        assert note.document().toHtml() == before


@pytest.mark.parametrize(
    "html",
    [
        "<p><i>A<sub>2</sub></i></p>",
        "<p><u>A<sup>2</sup></u></p>",
        '<p><span style="font-weight:600">A<sub>2</sub></span></p>',
        '<p align="center">A<sup>2</sup></p>',
    ],
)
def test_unsupported_style_with_script_still_preserves_output(tmp_path, html):
    state = _simple_state(
        atoms={}, bonds=[], notes=[dict(text="", html=html, x=0, y=0)]
    )
    dest = tmp_path / "previous.cdxml"
    dest.write_bytes(b"previous")
    with offscreen_document_scene(state, command="test-script") as context:
        with pytest.raises(CdxmlUnsupportedObjectError):
            FigureExportService(context).export_figure(str(dest), fmt="cdxml")
    assert dest.read_bytes() == b"previous"


def test_wrapped_nested_scripts_and_bold_keep_all_text():
    html = '<p><b>A<sub><span style="color:#123456">12</span></sub></b><br/>B<span style="vertical-align:super"><b>3</b></span>C</p>'
    state = _simple_state(
        atoms={}, bonds=[], notes=[dict(text="", html=html, x=0, y=0)]
    )
    with offscreen_document_scene(state, command="test-script") as context:
        items, plan = _resolved_export(context)
        root = ET.fromstring(serialize_cdxml(context, items, plan))
    segments = root.findall("./page/t/s")
    assert "".join(x.text or "" for x in segments) == "A12B3C"
    assert next(x for x in segments if x.text == "12").get("face") == "33"
    assert next(x for x in segments if x.text == "3").get("face") == "65"
