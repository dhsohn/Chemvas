"""Spatial native highlight classification, using only synthetic documents."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest
from PIL import Image
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.features.document_files import read_document
from chemvas.ui.export.export_scope import item_export_bounds

pytestmark = pytest.mark.usefixtures("qt_application")

SOURCE = b"""<CDXML LabelFont="3" LabelSize="10" CaptionFont="3" CaptionSize="10" BondLength="40" LineWidth="1">
<fonttable><font id="3" name="Arial"/></fonttable>
<colortable><color r="0.95" g="0.84" b="0.84"/></colortable>
<page id="1" BoundingBox="0 0 240 160">
  <graphic id="2" Z="1" GraphicType="Rectangle" RectangleType="RoundEdge Filled" BoundingBox="45 40 120 80" color="2"/>
  <graphic id="3" Z="1" GraphicType="Rectangle" RectangleType="RoundEdge Filled" BoundingBox="140 40 200 80" color="2"/>
  <fragment id="4">
    <n id="5" Z="2" p="60 60"/>
    <n id="6" Z="2" p="100 60" Element="8" NumHydrogens="0"><t id="7" Z="2" p="100 60"><s font="3" size="10" face="96">O</s></t></n>
    <b id="8" Z="2" B="5" E="6"/>
  </fragment>
  <t id="9" Z="2" p="150 62"><s font="3" size="10">step</s></t>
</page></CDXML>"""


def _image(state, identity="2"):
    index = state["cdxml_source"]["items"]["images"].index(identity)
    return state["images"][index]


def _state(root):
    return parse_cdxml_document(ET.tostring(root)).state


def _distant_carbon(root):
    # This single extra node caused the visible bond to disappear in 0.28.0.
    ET.SubElement(root.find(".//fragment"), "n", id="10", Z="1", p="210 130")


def _render(canvas):
    image = QImage(960, 640, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        canvas.scene().render(
            painter, QRectF(0, 0, 960, 640), QRectF(-120, -80, 240, 160)
        )
    finally:
        painter.end()
    return image


def _bond_pixels(image):
    return sum(
        max(image.pixelColor(x, y).getRgb()[:3]) < 100
        for x in range(300, 340)
        for y in range(236, 245)
    )


def _native(raw):
    return raw.split(b"\n<!-- ChemvasDocument:")[0]


def _without_z(raw):
    root = ET.fromstring(raw)
    for e in root.iter():
        e.attrib.pop("Z", None)
    return ET.canonicalize(ET.tostring(root, encoding="unicode"))


@pytest.mark.parametrize(
    "distant", ["same-fragment", "fragment", "bond", "label", "caption"]
)
def test_distant_low_z_does_not_hide_the_highlighted_bond(distant):
    root = ET.fromstring(SOURCE)
    if distant == "same-fragment":
        _distant_carbon(root)
    elif distant == "caption":
        ET.SubElement(root.find("page"), "t", id="10", Z="0", p="210 130").append(
            ET.fromstring('<s font="3" size="10">far</s>')
        )
    else:
        fragment = ET.SubElement(root.find("page"), "fragment", id="10")
        node = ET.SubElement(fragment, "n", id="11", Z="0", p="210 130")
        if distant == "bond":
            ET.SubElement(fragment, "n", id="12", Z="0", p="230 130")
            ET.SubElement(fragment, "b", id="13", Z="0", B="11", E="12")
        elif distant == "label":
            node.set("Element", "7")
            node.append(ET.fromstring('<t id="12" Z="0" p="210 130"><s>N</s></t>'))
    state = _state(root)
    assert _image(state)["z"] == -3
    with offscreen_canvas(state, command="native-highlight") as (canvas, _):
        image = _render(canvas)
        assert _bond_pixels(image) >= 120
        assert image.pixelColor(320, 240).name() == "#000000"
        assert image.pixelColor(320, 200).name() == "#f2d6d6"


def test_local_foreground_stays_over_a_lower_z_bond_despite_higher_z_nodes():
    root = ET.fromstring(SOURCE)
    root.find('.//graphic[@id="2"]').set("Z", "3")
    root.find('.//graphic[@id="2"]').set("BoundingBox", "70 50 90 70")
    for node in root.iter("n"):
        node.set("Z", "100")
    state = _state(root)
    assert _image(state)["z"] == 1
    with offscreen_canvas(state, command="native-foreground") as (canvas, _):
        assert _bond_pixels(_render(canvas)) == 0


@pytest.mark.parametrize("lower_z", ["0", "1"])
def test_crossing_bond_is_relevant_even_with_both_endpoints_outside(lower_z):
    root = ET.fromstring(SOURCE)
    fragment = ET.SubElement(root.find("page"), "fragment", id="10")
    ET.SubElement(fragment, "n", id="11", Z=lower_z, p="80 10")
    ET.SubElement(fragment, "n", id="12", Z=lower_z, p="80 110")
    ET.SubElement(fragment, "b", id="13", Z=lower_z, B="11", E="12")
    # Some overlapping chemistry is behind the fill. A global/local maximum
    # would incorrectly put the fill behind this explicitly lower bond.
    assert _image(_state(root))["z"] == 1


def test_diagonal_bond_box_alone_does_not_establish_overlap():
    root = ET.fromstring(SOURCE)
    root.find('.//graphic[@id="2"]').set("BoundingBox", "70 50 90 70")
    fragment = ET.SubElement(root.find("page"), "fragment", id="10")
    # Its enclosing rectangle overlaps, but the segment clears the highlight.
    ET.SubElement(fragment, "n", id="11", Z="0", p="0 40")
    ET.SubElement(fragment, "n", id="12", Z="0", p="150 140")
    ET.SubElement(fragment, "b", id="13", Z="0", B="11", E="12")
    assert _image(_state(root))["z"] == -3


@pytest.mark.parametrize(
    "attributes,y",
    [
        ({"LineWidth": "20"}, 89),
        ({"Display": "Bold", "BoldWidth": "20"}, 89),
        ({"Order": "2", "BondLength": "40", "BondSpacing": "25"}, 89),
        ({"Display": "WedgeBegin", "BoldWidth": "20", "LineWidth": "10"}, 94),
        ({"Display": "WedgedHashBegin", "BoldWidth": "20", "LineWidth": "10"}, 94),
        ({"Display": "Wavy", "LineWidth": "10"}, 87),
        ({"Display": "Hash", "LineWidth": "10"}, 87),
    ],
)
def test_native_stroke_metrics_guard_overlap_beyond_the_bond_centerline(attributes, y):
    root = ET.fromstring(SOURCE)
    fragment = ET.SubElement(root.find("page"), "fragment", id="10")
    ET.SubElement(fragment, "n", id="11", Z="0", p=f"40 {y}")
    ET.SubElement(fragment, "n", id="12", Z="0", p=f"130 {y}")
    ET.SubElement(fragment, "b", id="13", Z="0", B="11", E="12", **attributes)
    assert _image(_state(root))["z"] == 1


def test_invisible_carbon_and_stale_node_boxes_do_not_supply_painted_overlap():
    root = ET.fromstring(SOURCE)
    ET.SubElement(root.find(".//fragment"), "n", id="10", Z="0", p="80 60")
    root.find('.//n[@id="5"]').set("Z", "0")
    _distant = ET.SubElement(root.find(".//fragment"), "n", id="11", Z="0", p="210 130")
    _distant.set("BoundingBox", "45 40 120 80")
    assert _image(_state(root))["z"] == -3


def test_native_label_box_guards_a_local_lower_z_label_with_an_outside_anchor():
    root = ET.fromstring(SOURCE)
    root.find('.//n[@id="6"]').set("p", "130 60")
    root.find('.//n[@id="6"]').set("Z", "0")
    text = root.find('.//t[@id="7"]')
    text.set("p", "130 60")
    text.set("BoundingBox", "115 50 135 65")
    assert _image(_state(root))["z"] == 1


@pytest.mark.parametrize("kind", ["reversed-rectangle", "oval", "curve"])
def test_projection_uses_rendered_native_extent_not_a_generic_xml_box(kind):
    root = ET.fromstring(SOURCE)
    _distant_carbon(root)
    graphic = root.find('.//graphic[@id="2"]')
    if kind == "reversed-rectangle":
        graphic.set("BoundingBox", "120 80 45 40")
        expected = (-76.5, -41.5, 78, 43)
    elif kind == "oval":
        graphic.set("GraphicType", "Oval")
        graphic.set("OvalType", "Filled")
        graphic.set("BoundingBox", "120 60 80 60")
        expected = (-81.5, -61.5, 83, 83)
    else:
        graphic.tag = "curve"
        graphic.set("CurveType", "Closed Filled")
        graphic.set("CurvePoints", "40 40 40 40 40 80 120 80 120 40 120 40")
        graphic.set("BoundingBox", "200 120 230 140")  # Stale cache, not the path.
        expected = None
    state = _state(root)
    assert _image(state)["z"] == -3
    with offscreen_canvas(state, command="native-highlight-bounds") as (canvas, _):
        item = canvas.runtime_state.image_items()[0]
        bounds = item_export_bounds(item)
        assert bounds.contains(-40, -20)
        if expected is not None:
            assert bounds.getRect() == pytest.approx(expected)
        assert _bond_pixels(_render(canvas)) >= 120


def test_colored_molecular_area_keeps_its_explicit_background_semantics():
    root = ET.fromstring(SOURCE)
    _distant_carbon(root)
    ET.SubElement(root.find(".//fragment"), "n", id="11", Z="0", p="80 80")
    ET.SubElement(
        root.find("page"),
        "ColoredMolecularArea",
        id="12",
        Z="100",
        BasisObjects="5 6 11",
        bgcolor="2",
    )
    assert _image(_state(root), "12")["z"] == -3


@pytest.mark.parametrize("z,expected", [("1", -3), ("3", 1)])
def test_embedded_preview_keeps_native_payload_and_local_background_or_foreground(
    z, expected
):
    root = ET.fromstring(SOURCE)
    _distant_carbon(root)
    data = io.BytesIO()
    Image.new("RGB", (8, 4), "#f2d6d6").save(data, format="PNG")
    root.find("page").remove(root.find('.//graphic[@id="2"]'))
    embedded = ET.SubElement(
        root.find("page"),
        "embeddedobject",
        id="2",
        Z=z,
        BoundingBox="45 40 120 80",
        PNG=data.getvalue().hex(),
        EnhancedMetafile="retained-native-representation",
    )
    state = _state(root)
    assert _image(state)["z"] == expected
    saved = ET.fromstring(update_native_document(state)).find(".//embeddedobject")
    assert saved.attrib == embedded.attrib
    with offscreen_canvas(state, command="embedded-highlight") as (canvas, _):
        assert (_bond_pixels(_render(canvas)) >= 120) == (expected == -3)


@pytest.mark.parametrize("foreground", [False, True])
def test_distant_object_highlights_captions_and_native_bounds_survive_repeated_saves(
    tmp_path,
    foreground,
):
    root = ET.fromstring(SOURCE)
    _distant_carbon(root)
    if foreground:
        graphic = root.find('.//graphic[@id="2"]')
        graphic.set("Z", "3")
        graphic.set("BoundingBox", "70 50 90 70")
        # A foreground over an all-carbon fragment is representable. A fill
        # between a fragment's bond and visible atom label uses the writer's
        # existing unsupported interleaving path, tested separately below.
        node = root.find('.//n[@id="6"]')
        node.set("Element", "6")
        node.remove(node.find("t"))
    state = _state(root)
    before_state = deepcopy(state)
    assert ET.canonicalize(state["cdxml_source"]["xml"]) == ET.canonicalize(
        ET.tostring(root, encoding="unicode")
    )
    assert ET.canonicalize(update_native_document(state).decode()) == ET.canonicalize(
        state["cdxml_source"]["xml"]
    )
    path = tmp_path / "native-highlight.cdxml"
    with offscreen_canvas(state, command="highlight-save-reopen") as (canvas, service):
        before = _render(canvas)
        assert (_bond_pixels(before) >= 120) == (not foreground)
        caption = canvas.runtime_state.note_items()[0]
        fill = canvas.runtime_state.image_items()[1]
        assert item_export_bounds(caption).intersects(item_export_bounds(fill))
        assert caption.zValue() > fill.zValue()
        bounds = [item_export_bounds(i) for i in canvas.runtime_state.image_items()]
        service.save_to_file(str(path))
        first = path.read_bytes()
        assert _without_z(first) == _without_z(state["cdxml_source"]["xml"])
        assert b"embeddedobject" not in first
        for reopened in (
            read_document(path).state,
            parse_cdxml_document(_native(first)).state,
        ):
            service.apply_state(reopened)
            assert _render(canvas) == before
            assert [
                item_export_bounds(i) for i in canvas.runtime_state.image_items()
            ] == bounds
            service.save_to_file(str(path))
            assert _native(path.read_bytes()) == _native(first)
    assert state == before_state


def test_caption_overlapping_the_chemistry_highlight_retains_its_foreground():
    root = ET.fromstring(SOURCE)
    _distant_carbon(root)
    root.find('.//t[@id="9"]').set("p", "65 53")
    state = _state(root)
    with offscreen_canvas(state, command="caption-and-bond-highlight") as (canvas, _):
        caption = canvas.runtime_state.note_items()[0]
        fill = canvas.runtime_state.image_items()[0]
        assert item_export_bounds(caption).intersects(item_export_bounds(fill))
        assert caption.zValue() > fill.zValue()
        assert _bond_pixels(_render(canvas)) >= 120


def test_mixed_local_bond_order_is_not_silently_saved_as_a_background(tmp_path):
    root = ET.fromstring(SOURCE)
    fragment = ET.SubElement(root.find("page"), "fragment", id="10")
    ET.SubElement(fragment, "n", id="11", Z="0", p="80 10")
    ET.SubElement(fragment, "n", id="12", Z="0", p="80 110")
    ET.SubElement(fragment, "b", id="13", Z="0", B="11", E="12")
    state = _state(root)
    assert _image(state)["z"] == 1
    path = tmp_path / "keep.cdxml"
    path.write_bytes(b"original destination")
    with offscreen_canvas(state, command="mixed-bond-highlight") as (_, service):
        with pytest.raises(ValueError, match="overlapping"):
            service.save_to_file(str(path))
    assert path.read_bytes() == b"original destination"


def test_unsupported_foreground_over_caption_still_refuses_without_overwrite(tmp_path):
    root = ET.fromstring(SOURCE)
    _distant_carbon(root)
    root.find('.//graphic[@id="3"]').set("Z", "3")
    path = tmp_path / "keep.cdxml"
    path.write_bytes(b"original destination")
    with offscreen_canvas(_state(root), command="unsupported-caption-overlap") as (
        _,
        service,
    ):
        with pytest.raises(
            ValueError, match="conflicts with overlapping scene artwork"
        ):
            service.save_to_file(str(path))
    assert path.read_bytes() == b"original destination"
