"""Synthetic regressions for native CDXML behavior observed in ChemDraw 25."""

import io
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.domain.document.images import image_bytes_from_state
from chemvas.features.cdxml_document import parse_cdxml_document, read_cdxml_document
from chemvas.ui.export.cdxml_document_writer import save_cdxml_document

pytestmark = pytest.mark.usefixtures("qt_application")
FIXTURES = Path(__file__).with_name("fixtures")


def test_chemdraw_container_ranks_cannot_collide_with_bonds(tmp_path):
    # A three-atom chain, an opaque background and a fallback/arrow pair
    # reproduce the shared group/fragment/bond rank namespace. Renumbering
    # only drawable leaves collides with retained container ranks.
    raw = (FIXTURES / "cdxml-container-ranks.cdxml").read_bytes()
    original = ET.fromstring(raw)
    state = parse_cdxml_document(raw).state
    path = tmp_path / "containers.cdxml"
    with offscreen_canvas(state, command="consumer-container-z") as (canvas, service):
        save_cdxml_document(canvas, str(path), service.snapshot_state())
    saved = ET.fromstring(path.read_bytes())
    by_id = {e.get("id"): e for e in saved.iter() if e.tag != "font"}
    # Only a superseded graphic and its active arrow may share a rank. Labels
    # without Z use their owner; include every explicit container rank here.
    ranked = [e for e in saved.iter() if "Z" in e.attrib and not e.get("SupersededBy")]
    assert len({e.get("Z") for e in ranked}) == len(ranked)
    background_z = int(by_id["2"].get("Z"))
    assert all(int(b.get("Z")) > background_z for b in saved.iter("b"))
    assert by_id["9"].get("Order") == "3"
    assert all(
        by_id[e.get("id")].get("Z") == e.get("Z")
        for e in original.iter()
        if e.get("id") and e.tag != "font"
    )
    assert parse_cdxml_document(ET.tostring(saved)).state["model"] == state["model"]


def test_zero_width_fills_render_and_survive_native_disk_save(tmp_path):
    raw = (FIXTURES / "cdxml-zero-width-curves.cdxml").read_bytes()
    samples = [
        ("2", 25, 30, (0, 0, 0, 255)),
        ("3", 70, 30, (255, 255, 255, 255)),
        ("4", 70, 30, (0, 0, 0, 255)),
    ]
    imported = parse_cdxml_document(raw)
    assert not imported.has_snapshot
    assert imported.omitted_decorations == 0
    state = imported.state
    path = tmp_path / "saved.cdxml"
    with offscreen_canvas(state, command="test-chemdraw-reverse") as (canvas, service):
        save_cdxml_document(canvas, str(path), service.snapshot_state())
    snapshot = read_cdxml_document(path)
    assert snapshot.has_snapshot
    # Strip the private snapshot so a native-writer failure cannot hide behind it.
    root = ET.fromstring(path.read_bytes())
    reopened = parse_cdxml_document(ET.tostring(root))
    assert not reopened.has_snapshot
    for current in (state, snapshot.state, reopened.state):
        ids = current["cdxml_source"]["items"]["images"]
        ox, oy = current["cdxml_source"]["offset"]
        for identity, x, y, expected in samples:
            record = current["images"][ids.index(identity)]
            image = Image.open(io.BytesIO(image_bytes_from_state(record))).convert(
                "RGBA"
            )
            px = int((x - ox - record["x"]) / record["width"] * image.width)
            py = int((y - oy - record["y"]) / record["height"] * image.height)
            assert image.getpixel((px, py)) == expected
        assert [item["data_base64"] for item in current["images"]] == [
            item["data_base64"] for item in state["images"]
        ]
    for original in ET.fromstring(raw).iter("curve"):
        saved = root.find(f'.//curve[@id="{original.get("id")}"]')
        assert saved is not None
        assert {k: v for k, v in saved.attrib.items() if k != "Z"} == {
            k: v for k, v in original.attrib.items() if k != "Z"
        }


def test_zero_width_fill_has_no_outline():
    root = ET.parse(FIXTURES / "cdxml-zero-width-curves.cdxml").getroot()
    curve = root.find('.//curve[@id="2"]')
    assert curve is not None
    # The triangle's flat edge is x=20. At 8 px/pt, an outline would
    # leak left of that edge. Compare against the same shape with a real stroke.
    for width in ("0", "0.6"):
        curve.set("LineWidth", width)
        state = parse_cdxml_document(ET.tostring(root)).state
        record = state["images"][0]
        raster = Image.open(io.BytesIO(image_bytes_from_state(record))).convert("RGBA")
        bounds = raster.getbbox()
        assert bounds is not None
        left = (
            record["x"]
            + state["cdxml_source"]["offset"][0]
            + bounds[0] / raster.width * record["width"]
        )
        if width == "0":
            assert left == pytest.approx(20, abs=0.02)
        else:
            assert left < 19.9


def test_zero_width_rounded_fill_survives_native_save(tmp_path):
    raw = (FIXTURES / "cdxml-zero-width-rounded-rectangle.cdxml").read_bytes()
    state = parse_cdxml_document(raw).state
    assert len(state["images"]) == 1
    record = state["images"][0]
    raster = Image.open(io.BytesIO(image_bytes_from_state(record))).convert("RGBA")
    assert raster.getpixel((raster.width // 2, raster.height // 2)) == (
        0,
        0,
        0,
        255,
    )
    assert raster.getpixel((0, raster.height // 2))[3] == 0
    path = tmp_path / "rounded.cdxml"
    with offscreen_canvas(state, command="rounded-fill-save") as (canvas, service):
        save_cdxml_document(canvas, str(path), service.snapshot_state())
    native = ET.tostring(ET.fromstring(path.read_bytes()))
    reopened = parse_cdxml_document(native).state
    assert (
        read_cdxml_document(path).state["images"][0]["data_base64"]
        == record["data_base64"]
    )
    original = ET.fromstring(raw).find(".//graphic")
    saved = ET.fromstring(native).find(".//graphic")
    assert original is not None and saved is not None
    assert saved.attrib == original.attrib
    assert reopened["images"][0]["data_base64"] == record["data_base64"]
    assert not reopened["shapes"]


@pytest.mark.parametrize("line_width", ["0", "0.3", "0.75"])
@pytest.mark.parametrize("corner_radius", ["0", "600", "1600"])
def test_rounded_fill_keeps_its_native_radius(tmp_path, line_width, corner_radius):
    root = ET.parse(FIXTURES / "cdxml-zero-width-rounded-rectangle.cdxml").getroot()
    graphic = root.find(".//graphic")
    graphic.set("LineWidth", line_width)
    graphic.set("CornerRadius", corner_radius)
    state = parse_cdxml_document(ET.tostring(root)).state
    path = tmp_path / "rounded.cdxml"
    with offscreen_canvas(state, command="native-rounded-fill") as (canvas, service):
        save_cdxml_document(canvas, str(path), service.snapshot_state())
    assert ET.fromstring(path.read_bytes()).find(".//graphic").attrib == graphic.attrib


def test_zero_width_rounded_fill_uses_document_line_width_for_corners(tmp_path):
    # ChemDraw uses document LineWidth when a rounded fill has no outline.
    # This synthetic rectangle has a 12 pt radius: 1600 * 0.75 / 100.
    raw = (FIXTURES / "cdxml-zero-width-rounded-rectangle.cdxml").read_bytes()
    state = parse_cdxml_document(raw).state
    path = tmp_path / "rounded.cdxml"
    with offscreen_canvas(state, command="rounded-corner-preview") as (canvas, service):
        save_cdxml_document(canvas, str(path), service.snapshot_state())
    native = ET.tostring(ET.fromstring(path.read_bytes()))
    for current in (
        state,
        read_cdxml_document(path).state,
        parse_cdxml_document(native).state,
    ):
        record = current["images"][0]
        raster = Image.open(io.BytesIO(image_bytes_from_state(record))).convert("RGBA")
        ox, oy = current["cdxml_source"]["offset"]

        # Both corners distinguish the expected radius from a square or a
        # default-size corner. The midpoint verifies that zero still means no outline.
        for x, y, alpha in (
            (22, 22, 0),
            (98, 58, 0),
            (26, 26, 255),
            (94, 54, 255),
            (19.75, 40, 0),
            (20.25, 40, 255),
        ):
            px = round((x - ox - record["x"]) / record["width"] * raster.width)
            py = round((y - oy - record["y"]) / record["height"] * raster.height)
            assert raster.getpixel((px, py))[3] == alpha
        # A radius-12 circle centered at (32, 32) meets y=21 at x~=27.20.
        # Measure the contour too, so an arbitrary rounded radius fails.
        row = round((21 - oy - record["y"]) / record["height"] * raster.height)
        first = next(x for x in range(raster.width) if raster.getpixel((x, row))[3])
        left = record["x"] + ox + first * record["width"] / raster.width
        assert left == pytest.approx(27.20, abs=0.25)
