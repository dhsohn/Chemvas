"""Editable ChemDraw strokes retain native identities, metrics and references."""

import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import replace

import pytest
from PyQt6.QtCore import QPointF

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document


def drawing(element):
    return (
        '<CDXML LineWidth="0.75"><page id="1" BoundingBox="0 0 400 300">'
        + element
        + '<scheme id="20"><step id="21" ReactionStepArrows="10"/></scheme></page></CDXML>'
    ).encode()


def imported(element):
    return parse_cdxml_document(drawing(element)).state


@pytest.mark.parametrize(
    "attributes,kind,reverse",
    [
        ("", "line", False),
        ('LineType="Dashed"', "line_dashed", False),
        ('LineType="Bold"', "line_bold", False),
        ('ArrowheadHead="Full"', "arrow", False),
        ('ArrowheadTail="Full" LineType="Dashed"', "dotted", True),
        ('ArrowheadHead="HalfRight" ArrowheadTail="HalfRight"', "equilibrium", False),
    ],
)
def test_native_strokes_are_editable_and_save_endpoint_changes(
    attributes, kind, reverse
):
    state = imported(
        f'<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" HeadSize="700" {attributes}/>'
    )
    assert state["images"] == []
    arrow = state["arrows"][0]
    assert arrow["kind"] == kind
    assert arrow["start"] == ([-100, -100] if reverse else [-180, -100])
    assert state["cdxml_source"]["items"]["arrows"] == ["10"]
    untouched = update_native_document(state)
    assert ET.canonicalize(untouched.decode()) == ET.canonicalize(
        state["cdxml_source"]["xml"]
    )
    arrow["end"][0] += 13
    arrow["end"][1] += 17
    arrow["color"] = "#ff0000"
    raw = update_native_document(state)
    root = ET.fromstring(raw)
    target = root.find(".//arrow")
    assert target.get("id") == "10"
    assert target.get("HeadSize") == "700"
    assert target.get("Tail3D" if reverse else "Head3D") == (
        "33 67 0" if reverse else "113 67 0"
    )
    assert root.find(".//step").get("ReactionStepArrows") == "10"
    reopened = parse_cdxml_document(raw).state
    assert reopened["arrows"][0] == arrow
    assert update_native_document(reopened) == raw


def test_legacy_line_head_direction_and_other_metadata_survive():
    state = imported(
        '<graphic id="10" GraphicType="Line" ArrowType="FullHead" BoundingBox="100 50 20 50" Z="3"/>'
    )
    assert state["arrows"][0]["start"] == [-180, -100]
    state["arrows"][0]["end"] = [-90, -80]
    root = ET.fromstring(update_native_document(state))
    assert root.find(".//graphic").attrib == {
        "id": "10",
        "GraphicType": "Line",
        "ArrowType": "FullHead",
        "BoundingBox": "110 70 20 50",
        "Z": "3",
    }


def test_edit_updates_hidden_aliases_without_deleting_referenced_ids():
    state = imported(
        '<graphic id="8" SupersededBy="9"/><graphic id="9" SupersededBy="10"/><arrow id="10" Tail3D="20 50 0" Head3D="100 50 0"/>'
    )
    state["arrows"][0]["start"][0] += 10
    root = ET.fromstring(update_native_document(state))
    assert [g.get("BoundingBox") for g in root.findall(".//graphic")] == [
        "100 50 30 50"
    ] * 2
    assert root.find(".//arrow").get("id") == "10"
    assert root.find(".//step").get("ReactionStepArrows") == "10"


def test_decorative_arc_keeps_its_native_projection():
    state = imported(
        '<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" Center3D="60 50 0" AngularSize="180"/>'
    )
    assert state["arrows"] == []
    assert len(state["images"]) == 1


def test_real_canvas_handles_use_native_vector_metrics_and_round_trip(tmp_path):
    from PyQt6.QtCore import Qt

    from chemvas.bootstrap.document_cli_shared import offscreen_canvas
    from chemvas.features.document_files import read_document

    state = imported(
        '<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" ArrowheadHead="Full" HeadSize="800"/>'
    )
    original = deepcopy(state)
    with offscreen_canvas(state, command="test-editable-native-arrow") as (
        canvas,
        service,
    ):
        context = canvas.render_context
        item = next(iter(context.state.scene_items_state.arrow_items.values()))
        record = context.arrows.record(item)
        assert item.data(0) == "arrow"
        assert item.pen().widthF() == 0.75
        assert item.brush().style() == Qt.BrushStyle.SolidPattern
        context.arrows.set_record(
            item, replace(record, end=(-80, -70), color="#123456")
        )
        assert item.pen().widthF() == 0.75
        assert item.path().elementAt(1).x == -80
        path = tmp_path / "editable.cdxml"
        service.save_to_file(str(path))
        saved = read_document(path).state
        assert saved["arrows"][0]["end"] == [-80, -70]
        assert saved["arrows"][0]["color"] == "#123456"
        service.apply_state(saved)
        service.save_to_file(str(path))
        assert read_document(path).state["arrows"] == saved["arrows"]
        service.apply_state(original)
        assert service.snapshot_state()["arrows"][0]["end"] == (-100, -100)


def test_previously_saved_image_projection_becomes_editable_without_losing_move_or_group():
    from chemvas.features.cdxml_document import embed_document
    from chemvas.features.cdxml_graphics import graphic_image
    from chemvas.features.cdxml_preservation import PreservingImporter

    raw = drawing(
        '<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" ArrowheadHead="Full"/>'
    )
    reader = PreservingImporter(raw.decode())
    state = reader.state()
    image = graphic_image(reader, reader.root.find(".//arrow"))
    state["arrows"] = []
    state["images"] = [image]
    state["groups"] = [{"atoms": [], "items": [["images", 0]]}]
    source = state["cdxml_source"]
    source["items"] = {"arrows": [], "images": ["10"], "notes": []}
    source["baseline_items"] = deepcopy(source["items"])
    source["baseline"] = deepcopy(
        {k: v for k, v in state.items() if k != "cdxml_source"}
    )
    image["x"] += 20
    image["y"] += 10
    image["width"] *= 2
    saved = embed_document(update_native_document(state), state)
    upgraded = parse_cdxml_document(saved).state
    assert upgraded["images"] == []
    assert upgraded["groups"] == [{"atoms": [], "items": [["arrows", 0]]}]
    assert upgraded["arrows"][0]["end"][0] - upgraded["arrows"][0]["start"][
        0
    ] == pytest.approx(160)
    assert upgraded["arrows"][0]["start"][1] == -90
    assert ET.canonicalize(
        update_native_document(upgraded).decode()
    ) == ET.canonicalize(saved.split(b"\n<!--")[0].decode())


def test_recolor_black_is_not_reinterpreted_as_native_foreground():
    raw = drawing('<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0"/>')
    raw = raw.replace(
        b'<CDXML LineWidth="0.75">',
        b'<CDXML LineWidth="0.75" fgcolor="2"><colortable><color r="1" g="0" b="0"/></colortable>',
    )
    state = parse_cdxml_document(raw).state
    assert state["arrows"][0]["color"] == "#ff0000"
    state["arrows"][0]["color"] = "#000000"
    reopened = parse_cdxml_document(update_native_document(state)).state
    assert reopened["arrows"][0]["color"] == "#000000"


def test_mirroring_equilibrium_retains_native_dash_style():
    state = imported(
        '<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" ArrowheadHead="HalfLeft" ArrowheadTail="HalfLeft" LineType="Dashed"/>'
    )
    state["arrows"][0]["mirrored"] = True
    root = ET.fromstring(update_native_document(state))
    assert root.find(".//arrow").get("LineType") == "Dashed"
    assert root.find(".//arrow").get("ArrowheadHead") == "HalfRight"


@pytest.mark.parametrize(
    "attrs,kind",
    [
        ("", "line"),
        ('LineType="Dashed"', "line_dashed"),
        ('LineType="Bold"', "line_bold"),
        ('ArrowheadHead="HalfLeft" ArrowheadTail="HalfLeft"', "equilibrium"),
        (
            'ArrowheadHead="HalfRight" ArrowheadTail="HalfRight" ArrowheadType="Hollow"',
            "equilibrium",
        ),
    ],
)
def test_scene_native_strokes_retain_metrics_during_edit_and_kind_change(attrs, kind):
    from PyQt6.QtCore import Qt

    from chemvas.bootstrap.document_cli_shared import offscreen_canvas

    state = imported(f'<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" {attrs}/>')
    with offscreen_canvas(state, command="test-native-stroke-style") as (
        canvas,
        service,
    ):
        context = canvas.render_context
        item = next(iter(context.state.scene_items_state.arrow_items.values()))
        assert item.data(0) == kind
        # ChemDraw strokes a Bold line at the inherited BoldWidth (default 2).
        assert item.pen().widthF() == (2.0 if kind == "line_bold" else 0.75)
        record = context.arrows.record(item)
        context.arrows.set_record(
            item, replace(record, kind="line_dashed", mirrored=False)
        )
        assert item.pen().widthF() == 0.75
        assert item.pen().style() == Qt.PenStyle.DashLine
        saved = service.snapshot_state()
        assert (
            ET.fromstring(update_native_document(saved))
            .find(".//arrow")
            .get("LineWidth")
            is None
        )
        external = parse_cdxml_document(update_native_document(saved)).state
        assert external["arrows"][0]["kind"] == "line_dashed"


def test_native_background_line_remains_behind_chemical_structure():
    from chemvas.bootstrap.document_cli_shared import offscreen_canvas

    state = imported(
        '<fragment id="30"><n id="31" p="40 50" Z="5"/><n id="32" p="60 50" Z="6"/><b id="33" B="31" E="32" Z="7"/></fragment><arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" Z="2"/>'
    )
    with offscreen_canvas(state, command="test-native-stroke-layer") as (canvas, _):
        item = next(
            iter(canvas.render_context.state.scene_items_state.arrow_items.values())
        )
        assert item.zValue() == -3


@pytest.mark.parametrize("edit_other", [False, True])
def test_canvas_save_preserves_untouched_native_xml(tmp_path, edit_other):
    from chemvas.bootstrap.document_cli_shared import offscreen_canvas

    state = imported(
        '<graphic id="9" GraphicType="Line" SupersededBy="10" BoundingBox="100.000 50.000 20.000 50.000"/>'
        '<arrow id="10" Tail3D="20.000 50.000 0.000" Head3D="100.000 50.000 0.000" BoundingBox="19 49 101 51"/>'
        '<arrow id="11" Tail3D="20 80 0" Head3D="100 80 0"/>'
    )
    original = ET.fromstring(state["cdxml_source"]["xml"])
    with offscreen_canvas(state, command="test-untouched-native-stroke") as (
        canvas,
        service,
    ):
        if edit_other:
            context = canvas.render_context
            item = list(context.state.scene_items_state.arrow_items.values())[1]
            context.arrows.set_record(
                item, replace(context.arrows.record(item), end=(-70, -60))
            )
        path = tmp_path / "untouched.cdxml"
        service.save_to_file(str(path))
        root = ET.fromstring(path.read_bytes())
        for identity in ("9", "10"):
            # Saving resolves missing/tied Z at the document boundary while
            # keeping every native vector attribute, including exact decimals.
            saved = root.find(f'.//*[@id="{identity}"]')
            assert {
                key: value for key, value in saved.attrib.items() if key != "Z"
            } == original.find(f'.//*[@id="{identity}"]').attrib
        z = [
            int(root.find(f'.//*[@id="{identity}"]').get("Z"))
            for identity in ("9", "10", "11")
        ]
        assert len(set(z)) == 3 and min(z) > 0
        if edit_other:
            assert root.find('.//*[@id="11"]').get("Head3D") == "130 90 0"


@pytest.mark.parametrize("fill_z,expected", [(1, "#000000"), (3, "#ff0000")])
def test_untouched_arrow_fill_overlap_and_fallback_keep_native_reopen_pixels(
    tmp_path, fill_z, expected
):
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QImage, QPainter

    from chemvas.bootstrap.document_cli_shared import offscreen_canvas
    from chemvas.features.document_files import read_document

    raw = drawing(
        f'<graphic id="7" Z="{fill_z}" GraphicType="Rectangle" RectangleType="Filled" '
        'BoundingBox="40.000 35.000 80.000 65.000" color="2"/>'
        '<graphic id="8" SupersededBy="9" GraphicType="Line" '
        'BoundingBox="100.000 50.000 20.000 50.000"/>'
        '<graphic id="9" SupersededBy="10" GraphicType="Line" '
        'BoundingBox="100.000 50.000 20.000 50.000"/>'
        '<arrow id="10" Z="2" Tail3D="20.000 50.000 0.000" '
        'Head3D="100.000 50.000 0.000" LineWidth="2.000" ArrowheadHead="Full"/>'
        '<arrow id="11" Tail3D="20 80 0" Head3D="100 80 0"/>'
    ).replace(
        b'<CDXML LineWidth="0.75">',
        b'<CDXML LineWidth="0.75"><colortable><color r="1" g="0" b="0"/></colortable>',
    )
    state = parse_cdxml_document(raw).state
    original = ET.fromstring(state["cdxml_source"]["xml"])

    def render(canvas):
        image = QImage(800, 600, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        canvas.scene().render(
            painter, QRectF(0, 0, 800, 600), QRectF(-200, -150, 400, 300)
        )
        painter.end()
        return image

    with offscreen_canvas(state, command="overlapping-native-arrow") as (
        canvas,
        service,
    ):
        before = render(canvas)
        assert before.pixelColor(120, 100).name() == expected
        path = tmp_path / "overlap.cdxml"
        service.save_to_file(str(path))
        saved = path.read_bytes()
        root = ET.fromstring(saved)
        for old, new in zip(original.iter(), root.iter(), strict=True):
            assert old.tag == new.tag and old.text == new.text
            assert {k: v for k, v in old.attrib.items() if k != "Z"} == {
                k: v for k, v in new.attrib.items() if k != "Z"
            }
        ranks = [
            int(root.find(f'.//*[@id="{identity}"]').get("Z"))
            for identity in (7, 8, 9, 10, 11)
        ]
        assert len(set(ranks)) == 5 and min(ranks) > 0
        assert (ranks[0] < ranks[3]) == (fill_z < 2)
        assert root.find('.//*[@id="8"]').get("SupersededBy") == "9"
        assert root.find('.//*[@id="9"]').get("SupersededBy") == "10"
        assert root.find(".//step").get("ReactionStepArrows") == "10"
        for reopened in (
            read_document(path).state,
            parse_cdxml_document(saved.split(b"\n<!--")[0]).state,
        ):
            service.apply_state(reopened)
            assert render(canvas) == before
            service.save_to_file(str(path))
            assert path.read_bytes().split(b"\n<!--")[0] == saved.split(b"\n<!--")[0]


def test_bold_arrow_thickens_only_its_shaft_like_chemdraw():
    from chemvas.bootstrap.document_cli_shared import offscreen_canvas

    state = parse_cdxml_document(
        drawing(
            '<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" LineType="Bold" '
            'ArrowheadHead="Full" HeadSize="1000" ArrowheadWidth="250"/>'
        ).replace(b'LineWidth="0.75"', b'LineWidth="0.6" BoldWidth="2"')
    ).state
    with offscreen_canvas(state, command="test-native-bold-arrow") as (canvas, _):
        context = canvas.render_context
        item = next(iter(context.state.scene_items_state.arrow_items.values()))
        assert item.pen().widthF() == 0.6
        shape = item.path()
        # Shaft: BoldWidth wide (outline plus the LineWidth pen).
        box = shape.boundingRect()
        x, cy = box.left() + 20, box.center().y()
        mid = [
            cy + dy / 1000
            for dy in range(-2000, 2000)
            if shape.contains(QPointF(x, cy + dy / 1000))
        ]
        assert abs((max(mid) - min(mid)) + 0.6 - 2.0) < 0.05
        # Head: HeadSize/ArrowheadWidth stay in hundredths of LineWidth.
        assert abs(shape.boundingRect().height() - 2 * 2.5 * 0.6) < 0.05


def test_bold_dashed_line_keeps_line_width_dash_period():
    from PyQt6.QtCore import Qt

    from chemvas.bootstrap.document_cli_shared import offscreen_canvas

    state = parse_cdxml_document(
        drawing(
            '<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" LineType="Dashed Bold"/>'
        ).replace(b'LineWidth="0.75"', b'LineWidth="0.6" BoldWidth="2"')
    ).state
    with offscreen_canvas(state, command="test-native-bold-dash") as (canvas, _):
        context = canvas.render_context
        item = next(iter(context.state.scene_items_state.arrow_items.values()))
        pen = item.pen()
        assert pen.widthF() == 2.0
        assert pen.capStyle() == Qt.PenCapStyle.FlatCap
        # Dash and gap are each four LineWidths (2.4 pt), not four BoldWidths.
        assert [round(v * pen.widthF(), 6) for v in pen.dashPattern()] == [2.4, 2.4]
