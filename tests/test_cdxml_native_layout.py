"""Regression cases found by comparing Scheme1 in the native ChemDraw UI."""

import os
from itertools import pairwise

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFontInfo
from PyQt6.QtWidgets import QApplication

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.canvas.document_scene import detached_document_scene
from chemvas.ui.canvas.native_document_layout import native_bond_style
from chemvas.ui.export.cdxml_native_text import write_native_caption

SOURCE = b"""<CDXML BondLength="14.4" LineWidth="0.6" BondSpacing="18" LabelFont="3" CaptionFont="3"><fonttable><font id="3" name="Arial"/></fonttable><page id="1" BoundingBox="0 0 200 200"><fragment id="2"><n id="3" p="20 20"/><n id="4" p="27.2 20"/><n id="5" p="34.4 20"/><b id="6" B="3" E="4" LineWidth="0.3" BondLength="7.2" Order="2"/><b id="7" B="4" E="5" LineWidth="1.2"/></fragment><graphic id="8" GraphicType="Rectangle" RectangleType="Filled" BoundingBox="40 50 20 35"/><t id="9" p="30 40" BoundingBox="23 35 37 48" Justification="Center"><s font="3" size="5" color="1" face="3">Ar\ntuning</s></t></page></CDXML>"""


@pytest.fixture(scope="module", autouse=True)
def app():
    app = QApplication.instance() or QApplication([])
    yield app


def state():
    return parse_cdxml_document(SOURCE, preserve_source=True).state


def test_per_bond_dimensions_and_reset_survive_redraw_and_move():
    with detached_document_scene(state()) as context:
        original = context.renderer.style
        for bond_id, width, spacing in ((0, 0.3, 1.296), (1, 1.2, 2.592)):
            with native_bond_style(context, bond_id):
                assert context.renderer.bond_line_width() == pytest.approx(width)
                assert context.renderer.bond_spacing() * 1.1 == pytest.approx(spacing)
            assert context.renderer.style == original
            context.bonds.redraw_bond(bond_id)
        context.model.atoms[0].x += 1
        context.bonds.update_bond_geometry(0)
        assert context.renderer.style == original
        with pytest.raises(RuntimeError), native_bond_style(context, 0):
            raise RuntimeError("restore even after an interrupted render")
        assert context.renderer.style == original


def test_caption_scene_baseline_center_size_and_foreground_preserve_state():
    document = state()
    before = deepcopy(document)
    with detached_document_scene(document) as context:
        item = next(iter(context.state.scene_items_state.note_items.values()))
        layout = item.document().begin().layout()
        line = layout.lineAt(0)
        anchor = QPointF(
            layout.position().x() + line.naturalTextRect().center().x(),
            layout.position().y() + line.y() + line.ascent(),
        )
        assert item.mapToScene(anchor) == QPointF(-70, -60)
        font = item.document().begin().begin().fragment().charFormat().font()
        assert QFontInfo(font).pixelSize() == 5
        assert (
            item.zValue()
            > next(iter(context.state.scene_items_state.image_items.values())).zValue()
        )
        item.setPos(item.pos() + QPointF(7, 9))
        assert item.mapToScene(anchor) == QPointF(-63, -51)
    assert document == before
    assert update_native_document(document) == update_native_document(before)


def test_caption_edit_retains_native_size_in_saved_xml():
    document = state()
    note = document["notes"][0]
    note["text"] = "Ar\ntuned"
    note["html"] = note["html"].replace("tuning", "tuned")
    raw = update_native_document(document, note_writer=write_native_caption)
    root = ET.fromstring(raw)
    text = root.find(".//t")
    assert text is not None
    assert all(float(run.get("size")) == 5 for run in text.findall("s"))
    assert "tuned" in "".join(text.itertext())


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1"])
def test_invalid_native_bond_dimensions_fail_closed(value):
    document = parse_cdxml_document(
        SOURCE.replace(b'LineWidth="0.3"', f'LineWidth="{value}"'.encode()),
        preserve_source=True,
    ).state
    with pytest.raises(ValueError, match="native bond"):
        with detached_document_scene(document):
            pass


def test_rotated_caption_keeps_its_native_baseline_anchor():
    document = parse_cdxml_document(
        SOURCE.replace(
            b'Justification="Center"', b'Justification="Center" RotationAngle="4521984"'
        ),
        preserve_source=True,
    ).state
    with detached_document_scene(document) as context:
        item = next(iter(context.state.scene_items_state.note_items.values()))
        layout = item.document().begin().layout()
        line = layout.lineAt(0)
        anchor = QPointF(
            layout.position().x() + line.naturalTextRect().center().x(),
            layout.position().y() + line.y() + line.ascent(),
        )
        mapped = item.mapToScene(anchor)
        assert mapped.x() == pytest.approx(-70)
        assert mapped.y() == pytest.approx(-60)
        vector = item.mapToScene(anchor + QPointF(1, 0)) - mapped
        import math

        assert math.degrees(math.atan2(vector.y(), vector.x())) == pytest.approx(69)


def projection(attributes):
    from types import SimpleNamespace

    from chemvas.features.cdxml_graphics import _GraphicProjection

    node = ET.Element("arrow", attributes)
    reader = SimpleNamespace(
        color=lambda e: "#000000",
        number=lambda v, e: float(v),
        inherited=lambda e, k, d: e.get(k, d),
    )
    return _GraphicProjection(reader, node)


def test_native_half_heads_are_filled_and_equilibrium_direction_is_preserved():
    graphic = projection(
        dict(
            Tail3D="0 0 0",
            Head3D="30 0 0",
            ArrowheadHead="HalfLeft",
            ArrowheadTail="HalfLeft",
            ArrowheadType="Solid",
            HeadSize="800",
            ArrowheadWidth="200",
            ArrowShaftSpacing="300",
        )
    )
    graphic.arrow()
    upper, lower, head, tail = graphic.paths
    assert upper[0][-1][1] < 0 < lower[0][0][1]
    assert head[1:] == (True, "#000000")
    assert tail[1:] == (True, "#000000")
    assert head[0][0][0] == 30
    assert tail[0][0][0] == 0
    assert len(head[0]) == 3


def test_native_curved_equilibrium_has_two_separate_shafts():
    graphic = projection(
        dict(
            Tail3D="10 0 0",
            Head3D="0 -10 0",
            Center3D="0 0 0",
            AngularSize="90",
            ArrowheadHead="HalfLeft",
            ArrowheadTail="HalfLeft",
        )
    )
    graphic.arrow()
    first, second = graphic.paths[:2]
    assert len(first[0]) == len(second[0]) == 97
    assert first[0][0] != second[0][0]


def test_round_dashed_frame_retains_empty_corner_and_gaps():
    import base64
    import io

    from PIL import Image

    raw = SOURCE.replace(
        b'RectangleType="Filled"',
        b'RectangleType="RoundEdge Dashed" CornerRadius="600"',
    )
    document = parse_cdxml_document(raw, preserve_source=True).state
    image = document["images"][0]
    # Inspect projected alpha, independently of the path construction.
    raster = Image.open(io.BytesIO(base64.b64decode(image["data_base64"])))
    alpha = raster.getchannel("A")
    assert alpha.getextrema() == (0, 255)
    assert alpha.getpixel((0, 0)) == 0
    transitions = []
    for y in range(alpha.height):
        row = [alpha.getpixel((x, y)) > 0 for x in range(alpha.width)]
        transitions.append(sum(a != b for a, b in pairwise(row)))
    assert max(transitions) >= 6
