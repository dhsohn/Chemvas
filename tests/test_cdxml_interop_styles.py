"""Native CDXML style semantics, using only synthetic public test drawings."""

import io
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.domain.document.images import image_bytes_from_state
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.document_files import read_document
from chemvas.features.export.cdxml_consumer_validation import _Scene
from chemvas.ui.export.cdxml_document_writer import save_cdxml_document

pytestmark = pytest.mark.usefixtures("qt_application")

COLORS = Path(__file__).with_name("fixtures") / "cdxml-interop-colors.cdxml"


def _native_save(tmp_path, state):
    path = tmp_path / "saved.cdxml"
    with offscreen_canvas(state, command="test-native-interop") as (canvas, service):
        save_cdxml_document(canvas, str(path), service.snapshot_state())
    assert read_document(path).state
    # A normal save's editing snapshot must not hide a native writer failure.
    raw = path.read_bytes()
    assert b"<!-- ChemvasDocument:" in raw
    native = ET.tostring(ET.fromstring(raw))
    return ET.fromstring(native), parse_cdxml_document(native).state


@pytest.mark.parametrize("root_color,expected", [("4", "#00ff00"), (None, "#0000ff")])
def test_reserved_colors_and_inherited_foreground_survive_native_save(
    tmp_path, root_color, expected
):
    root = ET.parse(COLORS).getroot()
    if root_color is None:
        del root.attrib["color"]
    state = parse_cdxml_document(ET.tostring(root)).state
    for current in (state, _native_save(tmp_path, state)[1]):
        assert [a["color"] for a in current["model"]["atoms"].values()] == [
            expected,
            "#000000",
            "#ffffff",
        ]
        assert [b["color"] for b in current["model"]["bonds"]] == [expected, "#000000"]
        assert current["shapes"][0]["fill"] == "#0000ff"
        assert "color: #0000ff" in current["notes"][0]["html"]
        assert "color: #000000" in current["notes"][0]["html"]
    scene = _Scene(root)
    assert scene.color(root.find('.//b[@id="6"]')) == (
        (0.0, 1.0, 0.0) if root_color else (0.0, 0.0, 1.0)
    )


def test_first_color_edit_keeps_implicit_palette_and_untouched_objects(tmp_path):
    source = b"""<CDXML><page id="1" BoundingBox="0 0 200 120">
      <fragment id="2"><n id="3" p="20 20"/><n id="4" p="40 20"/>
      <b id="5" B="3" E="4" color="3"/></fragment>
      <graphic id="6" GraphicType="Rectangle" RectangleType="Filled"
      BoundingBox="80 20 100 40" LineWidth="0" color="2"/>
    </page></CDXML>"""
    state = parse_cdxml_document(source).state
    state["model"]["atoms"][0]["color"] = "#ff0000"
    root, reopened = _native_save(tmp_path, state)
    assert [
        (c.get("r"), c.get("g"), c.get("b")) for c in root.findall("colortable/color")
    ] == [("1", "1", "1"), ("0", "0", "0"), ("1", "0", "0")]
    assert reopened["model"]["atoms"][0]["color"] == "#ff0000"
    assert reopened["model"]["atoms"][1]["color"] == "#000000"
    assert reopened["model"]["bonds"][0]["color"] == "#000000"
    assert reopened["shapes"][0]["fill"] == "#ffffff"


def test_blank_working_document_has_valid_default_palette(tmp_path):
    state = parse_cdxml_document(b'<CDXML><page id="1"/></CDXML>').state
    del state["cdxml_source"]
    root, _ = _native_save(tmp_path, state)
    assert len(root.findall("colortable/color")) == 2
    assert _Scene(root).color(ET.Element("b")) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    "table,index",
    [
        ("<colortable/>", "3"),
        ('<colortable><color r="1" g="0" b="0"/></colortable>', "3"),
        ("", "4"),
        ("", "-1"),
    ],
)
def test_native_undefined_colors_remain_invalid(table, index):
    raw = f'<CDXML>{table}<page id="1"><fragment id="2"><n id="3" p="0 0" color="{index}"/></fragment></page></CDXML>'
    with pytest.raises(ValueError, match="missing color"):
        parse_cdxml_document(raw.encode())


def _curve(attributes):
    # A triangle, with coincident incoming/outgoing handles and no repeated
    # closing anchor: the closing edge must come from Closed / bit 0x0001.
    return f"""<CDXML LineWidth="0.6" BoldWidth="2"><page id="1" BoundingBox="0 0 200 120">
      <curve id="2" CurvePoints="20 20 20 20 20 20 80 20 80 20 80 20 50 80 50 80 50 80"
      {attributes}/></page></CDXML>""".encode()


def _pixel(record, x, y):
    raster = Image.open(io.BytesIO(image_bytes_from_state(record))).convert("RGBA")
    return raster.getpixel(
        (
            round((x - record["x"]) / record["width"] * raster.width),
            round((y - record["y"]) / record["height"] * raster.height),
        )
    )


@pytest.mark.parametrize(
    "attributes,filled",
    [
        ('CurveType="129"', True),
        ('Closed="yes" FillType="Solid"', True),
        ('CurveType="1" FillType="Solid"', True),
        ('CurveType="129" FillType="Solid" LineWidth="0"', True),
        ('CurveType="129" FillType="None"', False),
        ('CurveType="1"', False),
    ],
)
def test_curve_fill_closure_and_movement_survive_native_save(
    tmp_path, attributes, filled
):
    state = parse_cdxml_document(_curve(attributes)).state
    record = state["images"][0]
    assert bool(_pixel(record, -50, -20)[3]) is filled
    assert _pixel(record, -65, -10)[3] > 0  # Closing edge at native (35, 50).
    record["x"] += 12
    record["y"] += 7
    root, reopened = _native_save(tmp_path, state)
    moved = reopened["images"][0]
    assert moved["x"] == pytest.approx(record["x"])
    assert moved["y"] == pytest.approx(record["y"])
    assert bool(_pixel(moved, -38, -13)[3]) is filled
    assert root.find(".//curve").get("CurveType") == ET.fromstring(
        _curve(attributes)
    ).find(".//curve").get("CurveType")


@pytest.mark.parametrize(
    "attributes",
    [
        'CurveType="Closed Filled"',
        'CurveType="-1"',
        'CurveType="1024"',
        'CurveType="256"',
        'CurveType="512"',
        'FillType="Shaded"',
    ],
)
def test_unrepresentable_curve_style_is_refused(attributes):
    with pytest.raises(ValueError, match="curve|Curve|fill"):
        parse_cdxml_document(_curve(attributes))


@pytest.mark.parametrize(
    "legacy,explicit",
    [
        ('CurveType="4"', 'LineType="Bold"'),
        ('CurveType="2"', 'LineType="Dashed"'),
        ('CurveType="8"', 'ArrowheadHead="Full"'),
        ('CurveType="16"', 'ArrowheadTail="Full"'),
        ('CurveType="32"', 'ArrowheadHead="HalfLeft"'),
        ('CurveType="64"', 'ArrowheadTail="HalfLeft"'),
        ('CurveType="137"', 'ArrowheadHead="Full"'),
        ('CurveType="131"', 'CurveType="3"'),
        ('CurveType="1" Closed="no"', 'CurveType="0"'),
    ],
)
def test_curve_bits_match_explicit_styles_and_arrow_dash_precedence(legacy, explicit):
    first = parse_cdxml_document(_curve(legacy)).state["images"][0]
    second = parse_cdxml_document(_curve(explicit)).state["images"][0]
    for key in ("x", "y", "width", "height", "data_base64"):
        assert first[key] == second[key]


@pytest.mark.parametrize(
    "attributes",
    [
        'CurveType="1"',
        'CurveType="129" FillType="None"',
        'CurveType="131"',
        'CurveType="129" LineType="Dashed"',
        'CurveType="137"',
        'CurveType="129" ArrowheadTail="Full"',
    ],
)
def test_zero_width_curve_requires_effective_fill(attributes):
    with pytest.raises(ValueError, match="line width"):
        parse_cdxml_document(_curve(attributes + ' LineWidth="0"'))


@pytest.mark.parametrize("width", ["-0.1", "101"])
def test_filled_curve_invalid_width_is_rejected(width):
    with pytest.raises(ValueError, match="line width"):
        parse_cdxml_document(_curve(f'CurveType="129" LineWidth="{width}"'))
