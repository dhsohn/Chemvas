"""Native black ChemDraw rectangles import as editable shapes and write back."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document


def drawing(*graphics: str, fgcolor: str | None = None) -> bytes:
    body = "".join(graphics)
    fg = f' fgcolor="{fgcolor}"' if fgcolor is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<CDXML BondLength="20"{fg}>'
        "<colortable>"
        '<color r="1" g="0" b="0"/>'
        '<color r="0" g="0" b="1"/>'
        "</colortable>"
        '<page id="1" BoundingBox="0 0 400 300">'
        f"{body}"
        "</page></CDXML>"
    ).encode()


def _strip_snapshot(raw: bytes) -> bytes:
    marker = b"\n<!-- ChemvasDocument:"
    if marker not in raw:
        return raw
    return raw[: raw.index(marker)]


def _reopen_native(raw: bytes):
    return parse_cdxml_document(_strip_snapshot(raw)).state


def test_black_plain_and_filled_rectangles_import_as_bound_shapes():
    state = parse_cdxml_document(
        drawing(
            '<graphic id="10" GraphicType="Rectangle" RectangleType="Plain" '
            'BoundingBox="20 30 80 90"/>',
            '<graphic id="11" GraphicType="Rectangle" RectangleType="Filled" '
            'BoundingBox="100 40 160 100"/>',
        )
    ).state
    assert state["images"] == []
    assert state["cdxml_source"]["items"]["shapes"] == ["10", "11"]
    plain, filled = state["shapes"]
    assert plain == {
        "kind": "shape",
        "left": -180.0,
        "top": -120.0,
        "right": -120.0,
        "bottom": -60.0,
        "shape_kind": "rect",
        "stroke_style": "solid",
    }
    assert filled["shape_kind"] == "rect"
    assert filled["stroke_style"] == "solid"
    assert filled["fill"] == "#000000"
    assert (filled["left"], filled["top"], filled["right"], filled["bottom"]) == (
        -100.0,
        -110.0,
        -40.0,
        -50.0,
    )
    assert "fill" not in plain


@pytest.mark.parametrize(
    "attributes",
    [
        'RectangleType="Plain" color="2" BoundingBox="20 30 80 90"',
        'RectangleType="Filled" color="2" BoundingBox="20 30 80 90"',
    ],
)
def test_coloured_plain_and_filled_rectangles_remain_raster_images(attributes: str):
    state = parse_cdxml_document(
        drawing(f'<graphic id="10" GraphicType="Rectangle" {attributes}/>')
    ).state
    assert state["shapes"] == []
    assert state["cdxml_source"]["items"]["images"] == ["10"]
    assert len(state["images"]) == 1


def test_plain_color_zero_under_nonblack_fgcolor_stays_raster_image():
    state = parse_cdxml_document(
        drawing(
            '<graphic id="10" GraphicType="Rectangle" RectangleType="Plain" '
            'color="0" BoundingBox="20 30 80 90"/>',
            fgcolor="2",
        )
    ).state
    assert state["shapes"] == []
    assert state["cdxml_source"]["items"]["images"] == ["10"]
    assert len(state["images"]) == 1


@pytest.mark.parametrize(
    "attributes",
    [
        'RectangleType="RoundEdge" BoundingBox="20 30 80 90"',
        'RectangleType="Plain Shadow" BoundingBox="20 30 80 90"',
        'RectangleType="Filled Dashed" BoundingBox="20 30 80 90"',
        'RectangleType="Bold" BoundingBox="20 30 80 90"',
        'RectangleType="Plain" LineType="Dashed" BoundingBox="20 30 80 90"',
        'RectangleType="Plain" CornerRadius="600" BoundingBox="20 30 80 90"',
        'BoundingBox="20 30 80 90"',
    ],
)
def test_unsupported_rectangles_remain_raster_images(attributes: str):
    state = parse_cdxml_document(
        drawing(f'<graphic id="10" GraphicType="Rectangle" {attributes}/>')
    ).state
    assert state["shapes"] == []
    assert state["cdxml_source"]["items"]["images"] == ["10"]
    assert len(state["images"]) == 1


def test_move_resize_clear_fill_delete_and_unsupported_edits():
    state = parse_cdxml_document(
        drawing(
            '<graphic id="10" Z="3" GraphicType="Rectangle" RectangleType="Plain" '
            'color="0" BoundingBox="20 30 80 90"/>',
            '<graphic id="11" GraphicType="Rectangle" RectangleType="Filled" '
            'BoundingBox="100 40 160 100"/>',
            '<graphic id="12" GraphicType="Rectangle" RectangleType="Plain" '
            'BoundingBox="200 50 240 80"/>',
        )
    ).state
    plain, filled, _other = state["shapes"]
    untouched = update_native_document(deepcopy(state))
    assert ET.canonicalize(untouched.decode()) == ET.canonicalize(
        state["cdxml_source"]["xml"]
    )

    # Move Plain; existing stroke color attribute stays byte-stable beside BoundingBox.
    plain["left"] += 10
    plain["right"] += 10
    moved = update_native_document(state)
    root = ET.fromstring(moved)
    target = root.find('.//graphic[@id="10"]')
    assert target.get("BoundingBox") == "30 30 90 90"
    assert target.get("RectangleType") == "Plain"
    assert target.get("color") == "0"
    assert target.get("Z") == "3"
    state = _reopen_native(moved)
    assert state["shapes"][0]["left"] == pytest.approx(-170.0)
    assert state["cdxml_source"]["items"]["shapes"][0] == "10"

    # Resize Filled.
    filled = state["shapes"][1]
    filled["right"] += 20
    filled["bottom"] += 15
    resized = update_native_document(state)
    root = ET.fromstring(resized)
    assert root.find('.//graphic[@id="11"]').get("BoundingBox") == "100 40 180 115"
    state = _reopen_native(resized)
    assert state["shapes"][1]["right"] == pytest.approx(-20.0)
    assert state["shapes"][1]["bottom"] == pytest.approx(-35.0)
    assert state["shapes"][1]["fill"] == "#000000"

    # Recolor Plain stroke via Chemvas fill → native Filled with that color.
    plain = state["shapes"][0]
    plain["fill"] = "#0000ff"
    recolored_plain = update_native_document(state)
    root = ET.fromstring(recolored_plain)
    target = root.find('.//graphic[@id="10"]')
    assert target.get("RectangleType") == "Filled"
    assert target.get("color") not in {None, "0", "1"}
    # Non-black Filled is no longer identical in Chemvas, so native reopen is raster.
    state = _reopen_native(recolored_plain)
    assert "10" in state["cdxml_source"]["items"]["images"]
    assert all(s.get("fill") != "#0000ff" for s in state["shapes"])

    # Restore a black Filled for remaining shape-bound edits.
    state = parse_cdxml_document(
        drawing(
            '<graphic id="11" GraphicType="Rectangle" RectangleType="Filled" '
            'BoundingBox="100 40 180 115"/>',
            '<graphic id="12" GraphicType="Rectangle" RectangleType="Plain" '
            'BoundingBox="200 50 240 80"/>',
        )
    ).state

    # Clear Filled → Plain writes an explicit black stroke color.
    filled = state["shapes"][0]
    del filled["fill"]
    cleared = update_native_document(state)
    root = ET.fromstring(cleared)
    target = root.find('.//graphic[@id="11"]')
    assert target.get("RectangleType") == "Plain"
    assert target.get("color") == "0"
    state = _reopen_native(cleared)
    assert "fill" not in state["shapes"][0]
    assert state["cdxml_source"]["items"]["shapes"][0] == "11"

    # Delete the second rectangle; remaining native IDs stay bound.
    del state["shapes"][1]
    del state["cdxml_source"]["items"]["shapes"][1]
    deleted = update_native_document(state)
    root = ET.fromstring(deleted)
    assert root.find('.//graphic[@id="12"]') is None
    assert {g.get("id") for g in root.findall(".//graphic")} == {"11"}
    state = _reopen_native(deleted)
    assert state["cdxml_source"]["items"]["shapes"] == ["11"]
    assert len(state["shapes"]) == 1


def test_clear_fill_under_nonblack_fgcolor_writes_explicit_black():
    # Default color 0 remaps through red fgcolor. Absolute black lives in the
    # colortable (index 4) so a black Filled still imports as an editable shape.
    raw = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<CDXML BondLength="20" fgcolor="2">'
        b"<colortable>"
        b'<color r="1" g="0" b="0"/>'
        b'<color r="1" g="1" b="1"/>'
        b'<color r="0" g="0" b="0"/>'
        b"</colortable>"
        b'<page id="1" BoundingBox="0 0 400 300">'
        b'<graphic id="10" GraphicType="Rectangle" RectangleType="Filled" '
        b'color="4" BoundingBox="20 30 80 90"/>'
        b"</page></CDXML>"
    )
    state = parse_cdxml_document(raw).state
    assert state["cdxml_source"]["items"]["shapes"] == ["10"]
    assert state["shapes"][0]["fill"] == "#000000"

    del state["shapes"][0]["fill"]
    cleared = update_native_document(state)
    root = ET.fromstring(cleared)
    target = root.find('.//graphic[@id="10"]')
    assert target.get("RectangleType") == "Plain"
    # Must not drop color (would reopen as red via fgcolor); absolute black index.
    assert target.get("color") not in {None, "0", "1", "2"}
    assert root.get("fgcolor") == "2"
    state = _reopen_native(cleared)
    assert state["cdxml_source"]["items"]["shapes"] == ["10"]
    assert "fill" not in state["shapes"][0]
    assert state["images"] == []


def test_unsupported_shape_edits_leave_file_unchanged(tmp_path):
    state = parse_cdxml_document(
        drawing(
            '<graphic id="10" GraphicType="Rectangle" RectangleType="Filled" '
            'BoundingBox="20 30 80 90"/>'
        )
    ).state
    original_xml = state["cdxml_source"]["xml"]
    path = tmp_path / "rect.cdxml"
    path.write_bytes(
        drawing(
            '<graphic id="10" GraphicType="Rectangle" RectangleType="Filled" '
            'BoundingBox="20 30 80 90"/>'
        )
    )
    before_bytes = path.read_bytes()

    state["shapes"][0]["fill_alpha"] = 0.5
    with pytest.raises(ValueError, match="Translucent native rectangles"):
        update_native_document(state)
    assert state["cdxml_source"]["xml"] == original_xml
    assert path.read_bytes() == before_bytes

    del state["shapes"][0]["fill_alpha"]
    state["shapes"][0]["stroke_style"] = "dashed"
    with pytest.raises(ValueError, match="stroke_style"):
        update_native_document(state)
    assert path.read_bytes() == before_bytes

    state["shapes"][0]["stroke_style"] = "solid"
    state["shapes"][0]["shape_kind"] = "circle"
    with pytest.raises(ValueError, match="shape_kind"):
        update_native_document(state)
    assert path.read_bytes() == before_bytes


def test_unrelated_edit_keeps_untouched_rectangle_byte_identical():
    state = parse_cdxml_document(
        drawing(
            '<graphic id="10" GraphicType="Rectangle" RectangleType="Plain" '
            'Z="7" BoundingBox="20 30 80 90"/>',
            '<graphic id="11" GraphicType="Rectangle" RectangleType="Filled" '
            'BoundingBox="100 40 160 100"/>',
        )
    ).state
    graphic_before = ET.canonicalize(
        ET.tostring(
            ET.fromstring(state["cdxml_source"]["xml"]).find('.//graphic[@id="10"]'),
            encoding="unicode",
        )
    )
    state["shapes"][1]["left"] += 8
    state["shapes"][1]["right"] += 8
    saved = update_native_document(state)
    graphic_after = ET.canonicalize(
        ET.tostring(
            ET.fromstring(saved).find('.//graphic[@id="10"]'), encoding="unicode"
        )
    )
    assert graphic_after == graphic_before
    moved = ET.fromstring(saved).find('.//graphic[@id="11"]')
    assert moved.get("BoundingBox") == "108 40 168 100"


def test_snapshot_path_keeps_previous_rectangle_images():
    """Files previously saved by Chemvas keep rectangles as images via snapshot."""
    from chemvas.features.cdxml_document import embed_document
    from chemvas.features.cdxml_graphics import graphic_image
    from chemvas.features.cdxml_preservation import PreservingImporter

    raw = drawing(
        '<graphic id="10" GraphicType="Rectangle" RectangleType="Filled" '
        'BoundingBox="20 30 80 90"/>'
    )
    reader = PreservingImporter(raw.decode())
    # Build a pre-change snapshot where the rectangle is still an image binding.
    image = graphic_image(reader, reader.root.find(".//graphic"))
    assert image is not None
    state = reader.state()
    state["shapes"] = []
    state["images"] = [image]
    source = state["cdxml_source"]
    source["items"] = {"notes": [], "arrows": [], "shapes": [], "images": ["10"]}
    source["baseline_items"] = deepcopy(source["items"])
    source["baseline"] = deepcopy(
        {k: v for k, v in state.items() if k != "cdxml_source"}
    )
    embedded = embed_document(update_native_document(state), state)
    with_snapshot = parse_cdxml_document(embedded).state
    assert with_snapshot["images"]
    assert with_snapshot["cdxml_source"]["items"]["images"] == ["10"]
    # Native XML alone (snapshot stripped) uses the new shape binding.
    native_only = _reopen_native(embedded)
    assert native_only["shapes"]
    assert native_only["cdxml_source"]["items"]["shapes"] == ["10"]
