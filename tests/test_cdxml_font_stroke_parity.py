"""Synthetic typography and dash witnesses; no private figures are fixtures."""

import io
import struct
import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest
from PIL import Image
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QFont, QImage, QPainter, QTextCursor

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.domain.document.images import image_bytes_from_state
from chemvas.features.cdxml_document import parse_cdxml_document, read_cdxml_document
from chemvas.ui.export.cdxml_document_writer import save_cdxml_document
from chemvas.ui.export.export_scope import collect_export_items, exported_scene

pytestmark = pytest.mark.usefixtures("qt_application")


def source(content):
    return (
        '<CDXML CaptionFont="3" LineWidth="0.6" BoldWidth="2">'
        '<fonttable><font id="3" name="Arial"/></fonttable>'
        '<page id="1" BoundingBox="0 0 200 120">' + content + "</page></CDXML>"
    ).encode()


def appearance(item):
    item.boundingRect()
    block = item.document().begin()
    transform = item.sceneTransform()
    scale = (transform.m11() ** 2 + transform.m12() ** 2) ** 0.5
    result = []
    for index in range(len(block.text())):
        (run,) = block.layout().glyphRuns(index, 1)
        raw = run.rawFont()
        table = bytes(raw.fontTable("OS/2"))
        result.append(
            (
                raw.pixelSize() * scale,
                raw.weight(),
                raw.style(),
                struct.unpack(">H", table[4:6])[0],
            )
        )
    return result


def test_fractional_faces_mixed_runs_edit_and_disk_roundtrip(tmp_path):
    raw = source(
        '<t id="2" p="80 30" Justification="Center">'
        '<s font="3" size="8.5">N</s>'
        '<s font="3" size="9.4" face="1">B</s>'
        '<s font="3" size="7.2" face="2">I</s>'
        '<s font="3" size="7.4" face="3">X</s>'
        '<s font="3" size="8.5" face="0">R</s></t>'
    )
    state = parse_cdxml_document(raw).state
    original = deepcopy(state)
    path = tmp_path / "faces.cdxml"
    with offscreen_canvas(state, command="native-font-faces") as (canvas, service):
        item = next(iter(canvas.runtime_state.scene_items_state.note_items.values()))
        measured = appearance(item)
        assert [r[0] for r in measured] == pytest.approx([8.5, 9.4, 7.2, 7.4, 8.5])
        assert [r[1] for r in measured] == [400, 700, 400, 700, 400]
        assert [r[3] for r in measured] == [400, 700, 400, 700, 400]
        assert [r[2] for r in measured] == [
            QFont.Style.StyleNormal,
            QFont.Style.StyleNormal,
            QFont.Style.StyleItalic,
            QFont.Style.StyleItalic,
            QFont.Style.StyleNormal,
        ]
        save_cdxml_document(canvas, str(path), service.snapshot_state())
        # A plain load/save keeps the authored native sizes and faces.
        saved = ET.fromstring(path.read_bytes())
        assert [(s.attrib, s.text) for s in saved.findall(".//t/s")] == [
            (s.attrib, s.text) for s in ET.fromstring(raw).findall(".//t/s")
        ]
        cursor = QTextCursor(item.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("n")
        edited = tmp_path / "edited.cdxml"
        save_cdxml_document(canvas, str(edited), service.snapshot_state())
        assert [
            s.get("size") for s in ET.fromstring(edited.read_bytes()).findall(".//t/s")
        ] == [
            "8.5",
            "9.4",
            "7.2",
            "7.4",
            "8.5",
        ]
        assert appearance(item) == measured + [measured[-1]]
        item.document().undo()
        assert item.toPlainText() == "NBIXR"
        assert appearance(item) == measured
    assert state == original
    for reopened in (
        read_cdxml_document(path).state,
        parse_cdxml_document(ET.tostring(saved)).state,
    ):
        with offscreen_canvas(reopened, command="native-font-reopen") as (canvas, _):
            item = next(
                iter(canvas.runtime_state.scene_items_state.note_items.values())
            )
            assert appearance(item) == measured


def test_pixel_paste_undo_and_legacy_pixel_snapshot():
    state = parse_cdxml_document(
        source('<t id="2" p="20 20"><s font="3" size="8.5">A</s></t>')
    ).state
    with offscreen_canvas(state, command="native-font-paste") as (canvas, _):
        item = next(iter(canvas.runtime_state.scene_items_state.note_items.values()))
        cursor = QTextCursor(item.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml('<span style="font-size:12px">P</span>')
        assert [r[0] for r in appearance(item)] == [8.5, 12]
        item.document().undo()
        assert item.toPlainText() == "A"
        item.document().redo()
        assert [r[0] for r in appearance(item)] == [8.5, 12]
    # Preexisting snapshots used px. Their logical size and HTML stay intact.
    state["notes"][0]["html"] = state["notes"][0]["html"].replace("8.5pt", "9px")
    with offscreen_canvas(state, command="legacy-font-snapshot") as (canvas, _):
        item = next(iter(canvas.runtime_state.scene_items_state.note_items.values()))
        assert appearance(item)[0][0] == 9
        assert "9px" in item.toHtml()


def test_native_canvas_and_export_use_identical_glyph_ink():
    state = parse_cdxml_document(
        source(
            '<t id="2" p="30 30"><s font="3" size="8.5">Normal </s>'
            '<s font="3" size="9.4" face="1">Bold </s>'
            '<s font="3" size="7.2" face="2">Italic</s></t>'
            '<fragment id="3"><n id="4" p="40 60" Element="7">'
            '<t p="36 64"><s font="3" size="10.5" face="96">NH2</s></t>'
            "</n></fragment>"
        )
    ).state
    with offscreen_canvas(state, command="native-text-paint") as (canvas, _):
        scene = canvas.scene()
        items = collect_export_items(scene)
        # Empty native document background has no transient or sheet items in
        # this window. Hide editor furniture equally in both render paths.
        for item in scene.items():
            if item not in items:
                item.setVisible(False)

        def paint():
            image = QImage(800, 400, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            scene.render(painter, QRectF(0, 0, 800, 400), QRectF(-90, -50, 160, 80))
            painter.end()
            return image

        displayed = paint()
        with exported_scene(scene, items):
            exported = paint()
        assert displayed == exported
        assert any(
            displayed.pixelColor(x, y) != Qt.GlobalColor.white
            for x in range(800)
            for y in range(400)
        )


@pytest.mark.parametrize("width", [0.3, 0.6, 1.2])
@pytest.mark.parametrize("bold", ["", " Bold"])
@pytest.mark.parametrize("spacing", [1.25, 2.5, 4])
def test_native_dash_units_caps_phase_and_solid_fill(width, bold, spacing):
    state = parse_cdxml_document(
        source(
            f'<group id="3" HashSpacing="{spacing}"><arrow id="2" Tail3D="20 30 0" Head3D="89 30 0" LineType="Dashed{bold}" LineWidth="{width}"/></group>'
        )
    ).state
    with offscreen_canvas(state, command="native-dash") as (canvas, _):
        item = next(iter(canvas.runtime_state.scene_items_state.arrow_items.values()))
        pen = item.pen()
        assert pen.widthF() == (2 if bold else width)
        assert pen.capStyle() == Qt.PenCapStyle.FlatCap
        assert [v * pen.widthF() for v in pen.dashPattern()] == pytest.approx(
            [spacing, spacing]
        )
        # 69pt is deliberately not an integral period; the head starts a dash.
        ox, oy = state["cdxml_source"]["offset"]
        assert item.path().pointAtPercent(0) == QPointF(89 - ox, 30 - oy)


@pytest.mark.parametrize("spacing", ["0", "-1", "nan", "inf", "1001"])
@pytest.mark.parametrize("graphic", [False, True])
def test_invalid_native_dash_spacing_is_refused(spacing, graphic):
    element = (
        '<graphic id="2" GraphicType="Rectangle" RectangleType="Dashed" BoundingBox="20 20 80 60"/>'
        if graphic
        else '<arrow id="2" Tail3D="20 30 0" Head3D="89 30 0" LineType="Dashed"/>'
    )
    with pytest.raises(ValueError):
        parse_cdxml_document(
            source(f'<group id="3" HashSpacing="{spacing}">{element}</group>')
        )


def test_raster_dashed_shape_keeps_equal_physical_dashes_and_gaps():
    state = parse_cdxml_document(
        source(
            '<graphic id="2" GraphicType="Rectangle" RectangleType="Dashed" BoundingBox="20 20 80 60"/>'
        )
    ).state
    record = state["images"][0]
    im = Image.open(io.BytesIO(image_bytes_from_state(record))).convert("RGBA")
    ox, oy = state["cdxml_source"]["offset"]
    x = round((20 - ox - record["x"]) * im.width / record["width"])
    start = round((22 - oy - record["y"]) * im.height / record["height"])
    end = round((57 - oy - record["y"]) * im.height / record["height"])
    runs = []
    last = None
    for y in range(start, end):
        ink = im.getpixel((x, y))[3] > 0
        if ink != last:
            runs.append(0)
        runs[-1] += 1
        last = ink
    lengths = [v * record["height"] / im.height for v in runs[1:-1]]
    assert len(lengths) >= 10
    # Pillow includes the last stroke pixel; both endpoints can quantize.
    tolerance = 2 * record["height"] / im.height
    assert lengths == pytest.approx([2.5] * len(lengths), abs=tolerance)


def test_subpixel_dash_spacing_keeps_raster_projection_bounded():
    state = parse_cdxml_document(
        source(
            '<graphic id="2" GraphicType="Rectangle" RectangleType="Dashed" '
            'HashSpacing="0.000001" BoundingBox="20 20 80 60"/>'
        )
    ).state
    image = Image.open(io.BytesIO(image_bytes_from_state(state["images"][0])))
    assert image.getbbox() is not None
    assert image.width * image.height < 1_000_000
