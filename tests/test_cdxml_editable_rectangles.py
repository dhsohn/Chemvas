"""Native black outlined ChemDraw rectangles import as editable shapes."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.export.cdxml_document_writer import save_cdxml_document

RED_BLUE = (
    '<colortable><color r="1" g="0" b="0"/><color r="0" g="0" b="1"/></colortable>'
)
WHITE_BLACK = (
    '<colortable><color r="1" g="1" b="1"/><color r="0" g="0" b="0"/></colortable>'
)


def drawing(*graphics: str, table: str = "", root: str = "") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<CDXML BondLength="20"{root}>{table}'
        '<page id="1" BoundingBox="0 0 400 300">'
        f"{''.join(graphics)}"
        "</page></CDXML>"
    ).encode()


def plain(identity: int = 10, extra: str = "", box: str = "20 30 80 90") -> str:
    return (
        f'<graphic id="{identity}" GraphicType="Rectangle" RectangleType="Plain" '
        f'BoundingBox="{box}"{extra}/>'
    )


def graphic(saved: bytes, identity: int) -> ET.Element:
    found = ET.fromstring(saved).find(f'.//graphic[@id="{identity}"]')
    assert found is not None
    return found


def test_black_plain_and_filled_rectangles_import_as_bound_shapes():
    state = parse_cdxml_document(
        drawing(
            plain(),
            '<graphic id="11" GraphicType="Rectangle" RectangleType="Filled" '
            'LineWidth="0" BoundingBox="100 40 160 100"/>',
        )
    ).state
    assert state["images"] == []
    assert state["cdxml_source"]["items"]["shapes"] == ["10", "11"]
    outlined, filled = state["shapes"]
    assert outlined == {
        "kind": "shape",
        "left": -180.0,
        "top": -120.0,
        "right": -120.0,
        "bottom": -60.0,
        "shape_kind": "rect",
        "stroke_style": "solid",
        "z": 1.0,
    }
    assert filled["stroke_style"] == "none"
    assert filled["fill"] == "#000000"


@pytest.mark.parametrize(
    ("extra", "table", "editable"),
    [
        # Reserved 0/1 are absolute black/white whatever the table holds.
        (' color="0"', RED_BLUE, True),
        (' color="1"', RED_BLUE, False),
        (' color="1"', "", False),
        # The default color index 3 is the implicit black without a table ...
        ("", "", True),
        # ... and the second table entry otherwise.
        ("", WHITE_BLACK, True),
        ("", RED_BLUE, False),
        (' color="2"', RED_BLUE, False),
    ],
)
def test_palette_index_decides_outlined_import(extra: str, table: str, editable: bool):
    state = parse_cdxml_document(drawing(plain(extra=extra), table=table)).state
    if editable:
        assert state["cdxml_source"]["items"]["shapes"] == ["10"]
        assert state["images"] == []
    else:
        assert state["shapes"] == []
        assert state["cdxml_source"]["items"]["images"] == ["10"]


def test_coloured_filled_rectangle_keeps_fill_only_shape_path():
    state = parse_cdxml_document(
        drawing(
            '<graphic id="10" GraphicType="Rectangle" '
            'RectangleType="Filled" color="2" BoundingBox="20 30 80 90"/>',
            table=RED_BLUE,
        )
    ).state
    assert state["shapes"][0]["stroke_style"] == "none"
    assert state["shapes"][0]["fill"] == "#ff0000"


@pytest.mark.parametrize(
    "element",
    [
        plain().replace('"Plain"', '"RoundEdge"'),
        plain().replace('"Plain"', '"Plain Shadow"'),
        plain().replace('"Plain"', '"Bold"'),
        plain().replace('"Plain"', '"Filled Dashed"'),
        plain().replace(' RectangleType="Plain"', ""),
        plain(extra=' LineType="Dashed"'),
        plain(extra=' CornerRadius="600"'),
        # A rotated rectangle's axes do not fit the axis-aligned shape model.
        plain(
            box="20 20 60 60",
            extra=' Center3D="40 40 0" MajorAxisEnd3D="54.14 54.14 0" '
            'MinorAxisEnd3D="25.86 54.14 0"',
        ),
        # Child elements carry content a shape record cannot represent.
        plain().replace("/>", '><objecttag Name="x"/></graphic>'),
    ],
)
def test_unsupported_rectangles_remain_raster_images(element: str):
    state = parse_cdxml_document(drawing(element)).state
    assert state["shapes"] == []
    assert state["cdxml_source"]["items"]["images"] == ["10"]
    assert len(state["images"]) == 1


def test_zero_line_width_plain_rectangle_stays_unsupported():
    with pytest.raises(ValueError, match="line width"):
        parse_cdxml_document(drawing(plain(extra=' LineWidth="0"')))


def test_move_resize_and_delete_write_native_geometry():
    state = parse_cdxml_document(
        drawing(
            plain(extra=' Z="3" color="0" LineWidth="1.5"'),
            plain(12, box="200 50 240 80"),
        )
    ).state
    untouched = update_native_document(deepcopy(state))
    assert ET.canonicalize(untouched.decode()) == ET.canonicalize(
        state["cdxml_source"]["xml"]
    )

    shape = state["shapes"][0]
    shape["left"] += 10
    shape["right"] += 30
    shape["bottom"] += 15
    del state["shapes"][1]
    del state["cdxml_source"]["items"]["shapes"][1]
    saved = update_native_document(state)
    target = graphic(saved, 10)
    assert target.get("BoundingBox") == "30 30 110 105"
    assert target.get("RectangleType") == "Plain"
    assert target.get("color") == "0"
    assert target.get("LineWidth") == "1.5"
    assert target.get("Z") == "3"
    assert ET.fromstring(saved).find('.//graphic[@id="12"]') is None

    reopened = parse_cdxml_document(saved).state
    assert reopened["cdxml_source"]["items"]["shapes"] == ["10"]
    assert reopened["shapes"][0]["stroke_style"] == "solid"
    assert (reopened["shapes"][0]["left"], reopened["shapes"][0]["right"]) == (
        pytest.approx(-170.0),
        pytest.approx(-90.0),
    )


def test_resize_transforms_rectangle_axes():
    state = parse_cdxml_document(
        drawing(
            plain(
                8,
                box="20 80 60 120",
                extra=' Center3D="40 100 0" MajorAxisEnd3D="60 100 0" '
                'MinorAxisEnd3D="40 120 0"',
            )
        )
    ).state
    shape = state["shapes"][0]
    shape["left"] += 10
    shape["right"] += 50
    shape["bottom"] += 20
    saved = update_native_document(state)
    target = graphic(saved, 8)
    assert target.get("BoundingBox") == "30 80 110 140"
    assert target.get("Center3D") == "70 110 0"
    assert target.get("MajorAxisEnd3D") == "110 110 0"
    assert target.get("MinorAxisEnd3D") == "70 140 0"
    assert parse_cdxml_document(saved).state["cdxml_source"]["items"]["shapes"] == ["8"]


def test_outlined_rectangle_below_chemistry_keeps_native_z():
    state = parse_cdxml_document(
        drawing(
            plain(extra=' Z="1"'),
            '<fragment id="20"><n id="21" Z="5" Element="7" p="50 60"/></fragment>',
        )
    ).state
    assert state["shapes"][0]["z"] == -3.0
    state["shapes"][0]["top"] += 5
    state["shapes"][0]["bottom"] += 5
    assert graphic(update_native_document(state), 10).get("Z") == "1"


def test_linked_fallback_keeps_outlined_rectangle_on_raster_path():
    fallback = plain(9, box="20 80 60 120", extra=' SupersededBy="8"')
    state = parse_cdxml_document(drawing(plain(8, box="20 80 60 120"), fallback)).state
    assert state["shapes"] == []
    assert state["cdxml_source"]["items"]["images"] == ["8"]
    state["images"][0]["x"] += 10
    saved = update_native_document(state)
    assert graphic(saved, 8).get("BoundingBox") == "30 80 70 120"
    assert graphic(saved, 9).get("BoundingBox") == "30 80 70 120"
    assert parse_cdxml_document(saved).state["cdxml_source"]["items"]["images"] == ["8"]


def test_unrelated_edit_keeps_untouched_rectangle_byte_identical():
    state = parse_cdxml_document(
        drawing(
            plain(extra=' Z="7"'),
            '<graphic id="11" GraphicType="Rectangle" RectangleType="Filled" '
            'BoundingBox="100 40 160 100"/>',
        )
    ).state
    before = ET.canonicalize(
        ET.tostring(
            ET.fromstring(state["cdxml_source"]["xml"]).find('.//graphic[@id="10"]'),
            encoding="unicode",
        )
    )
    state["shapes"][1]["left"] += 8
    state["shapes"][1]["right"] += 8
    saved = update_native_document(state)
    assert (
        ET.canonicalize(ET.tostring(graphic(saved, 10), encoding="unicode")) == before
    )
    assert graphic(saved, 11).get("BoundingBox") == "108 40 168 100"


@pytest.mark.parametrize(
    "edit",
    [
        {"fill": "#000000", "fill_alpha": 1.0},
        {"fill": "#0000ff", "fill_alpha": 1.0},
        {"fill": "#0000ff", "fill_alpha": 0.5},
        {"stroke_style": "dashed"},
        {"shape_kind": "ellipse"},
    ],
)
def test_unsupported_outlined_edits_refuse_before_replacing_file(
    tmp_path, qt_application, edit
):
    raw = drawing(plain(extra=' color="0"'))
    path = tmp_path / "rect.cdxml"
    path.write_bytes(raw)
    state = parse_cdxml_document(raw).state
    with offscreen_canvas(state, command="outlined-rect-refusal") as (canvas, service):
        snapshot = service.snapshot_state()
        snapshot["shapes"][0].update(edit)
        with pytest.raises(ValueError, match="unsupported"):
            save_cdxml_document(canvas, str(path), snapshot)
    assert path.read_bytes() == raw


def test_canvas_draws_outline_at_shape_width_not_native_width(tmp_path, qt_application):
    from chemvas.ui.annotations.shape_geometry import shape_stroke_width

    raw = drawing(
        plain(extra=' LineWidth="0.15"'),
        plain(11, box="100 30 160 90", extra=' LineWidth="4"'),
    )
    state = parse_cdxml_document(raw).state
    path = tmp_path / "widths.cdxml"
    with offscreen_canvas(state, command="outlined-rect-width") as (canvas, service):
        widths = {
            item.pen().widthF()
            for item in canvas.scene().items()
            if item.data(0) == "shape"
        }
        expected = shape_stroke_width(canvas.renderer.style.bond_line_width)
        snapshot = service.snapshot_state()
        snapshot["shapes"][0]["left"] += 5
        snapshot["shapes"][0]["right"] += 5
        save_cdxml_document(canvas, str(path), snapshot)
    # Both native widths draw at the one shape width; the file keeps each width.
    assert widths == {expected}
    saved = path.read_bytes()
    assert graphic(saved, 10).get("BoundingBox") == "25 30 85 90"
    assert graphic(saved, 10).get("LineWidth") == "0.15"
    assert graphic(saved, 11).get("LineWidth") == "4"


def test_fill_only_shape_contract_is_unchanged():
    # Existing ADR 0069 shapes still require an opaque fill and recolor in place.
    circle = (
        '<graphic id="10" GraphicType="Oval" OvalType="Circle Filled" '
        'BoundingBox="70 50 50 50" Center3D="50 50 0" MajorAxisEnd3D="70 50 0" '
        'MinorAxisEnd3D="50 70 0"/>'
    )
    rect = (
        '<graphic id="11" GraphicType="Rectangle" RectangleType="Filled" '
        'BoundingBox="100 40 160 100"/>'
    )
    state = parse_cdxml_document(drawing(circle, rect, table=RED_BLUE)).state
    for index in (0, 1):
        cleared = deepcopy(state)
        del cleared["shapes"][index]["fill"]
        with pytest.raises(ValueError, match="opaque fill"):
            update_native_document(cleared)
    state["shapes"][0]["fill"] = "#ff0000"
    saved = graphic(update_native_document(state), 10)
    assert saved.get("OvalType") == "Circle Filled"
    assert "RectangleType" not in saved.attrib
    assert saved.get("color") == "2"


def test_snapshot_path_keeps_previous_rectangle_images():
    """Files previously saved by Chemvas keep rectangles as images via snapshot."""
    from chemvas.features.cdxml_document import embed_document
    from chemvas.features.cdxml_graphics import graphic_image
    from chemvas.features.cdxml_preservation import PreservingImporter

    raw = drawing(plain())
    reader = PreservingImporter(raw.decode())
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
    native_only = parse_cdxml_document(
        embedded[: embedded.index(b"\n<!-- ChemvasDocument:")]
    ).state
    assert native_only["cdxml_source"]["items"]["shapes"] == ["10"]
