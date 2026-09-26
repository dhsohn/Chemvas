from __future__ import annotations

import json
import math
import subprocess
import sys
from types import SimpleNamespace

import pytest
from PIL import Image
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QRawFont, QTextCharFormat
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsScene

from chemvas.domain.document import AnnotationCollection
from chemvas.features.annotations import arrow_label_html
from chemvas.ui.annotations.items import NoteItem
from chemvas.ui.canvas.graphics_items import ArrowLabelItem
from chemvas.ui.export.export_render_service import resolve_export_plan
from chemvas.ui.export.export_scope import content_bounds, item_export_bounds
from tests.subprocess_support import source_subprocess_env


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _label(text, *, italic=False):
    item = ArrowLabelItem()
    item.setData(0, "arrow_label")
    font = QFont("DejaVu Sans", 12)
    font.setItalic(italic)
    item.setFont(font)
    item.setDefaultTextColor(QColor("#195b90"))
    item.setHtml(arrow_label_html(text))
    item.setPos(17.25, -28.75)
    return item


def _render(scene, source, *, scale=8):
    image = QImage(
        math.ceil(source.width() * scale),
        math.ceil(source.height() * scale),
        QImage.Format.Format_RGBA8888,
    )
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    try:
        scene.render(
            painter,
            QRectF(0, 0, source.width() * scale, source.height() * scale),
            source,
        )
    finally:
        painter.end()
    return image


def _ink_bounds(image, source, *, scale=8):
    pixels = Image.frombytes(
        "RGBA",
        (image.width(), image.height()),
        image.constBits().asstring(image.sizeInBytes()),
    )
    bounds = pixels.getchannel("A").getbbox()
    assert bounds is not None
    left, top, right, bottom = bounds
    return QRectF(
        source.x() + left / scale,
        source.y() + top / scale,
        (right - left) / scale,
        (bottom - top) / scale,
    )


@pytest.mark.parametrize(
    "text",
    [
        "oxidation",
        "MnO_{2}\nCH_{2}Cl_{2}",
        "ΔG^{‡}\nK_{eq}",
        "A\n\nB",
        "  spaced  ",
        "مرحبا",
    ],
)
@pytest.mark.parametrize("angle,italic", [(0, False), (37, True), (90, False)])
def test_arrow_export_bounds_fit_actual_outlined_ink_without_changing_layout(
    text, angle, italic
):
    scene = QGraphicsScene()
    parent = QGraphicsRectItem()
    parent.setPen(QPen(Qt.PenStyle.NoPen))
    parent.setPos(11.5, -7.25)
    parent.setRotation(13)
    parent.setScale(1.2)
    scene.addItem(parent)
    label = _label(text, italic=italic)
    label.setParentItem(parent)
    label.setRotation(angle)
    source = label.sceneBoundingRect().adjusted(-10, -10, 10, 10)
    document = label.document()
    before = (
        label.boundingRect(),
        label.shape(),
        label.toHtml(),
        label.scenePos(),
        document.availableUndoSteps(),
        document.isModified(),
    )
    screen_before = _render(scene, source)
    label.set_outline_mode(True)
    ink = _ink_bounds(_render(scene, source), source)
    label.set_outline_mode(False)
    bounds = item_export_bounds(label)
    # The oracle is Qt's actual outlined paint, not the helper used by bounds.
    # Antialiasing may touch one adjacent physical pixel at this 8x scale.
    for actual, expected in zip(bounds.getCoords(), ink.getCoords(), strict=True):
        assert actual == pytest.approx(expected, abs=1 / 8)
    assert content_bounds([label]) == bounds
    _, plan = resolve_export_plan(scene, items=[label], margin=3)
    assert plan.source_x == bounds.x() - 3
    assert plan.source_y == bounds.y() - 3
    assert plan.source_w == bounds.width() + 6
    assert plan.source_h == bounds.height() + 6
    assert (
        label.boundingRect(),
        label.shape(),
        label.toHtml(),
        label.scenePos(),
        document.availableUndoSteps(),
        document.isModified(),
    ) == before
    assert _render(scene, source) == screen_before


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_blank_arrow_label_adds_no_export_extent(text):
    label = _label(text)
    assert item_export_bounds(label).isNull()
    assert content_bounds([label]) is None


@pytest.mark.parametrize("mode", ["hidden", "transparent", "opacity", "parent"])
def test_unpainted_arrow_label_adds_no_export_extent(mode):
    label = _label("MnO_2")
    parent = QGraphicsRectItem()
    label.setParentItem(parent)
    if mode == "hidden":
        label.hide()
    elif mode == "transparent":
        label.setDefaultTextColor(QColor("transparent"))
    elif mode == "opacity":
        label.setOpacity(0)
    else:
        parent.setOpacity(0)
    assert item_export_bounds(label).isNull()


def test_bounds_follow_later_label_font_and_text_changes():
    label = _label("oxidation")
    small = item_export_bounds(label)
    font = label.font()
    font.setPointSizeF(24)
    label.setFont(font)
    large = item_export_bounds(label)
    assert large.width() > small.width()
    label.setHtml(arrow_label_html("O"))
    assert item_export_bounds(label).width() < large.width()
    label.setDefaultTextColor(QColor("#80195b90"))
    assert not item_export_bounds(label).isNull()


def test_script_baseline_uses_qt_fixed_point_rounding():
    from chemvas.ui.canvas.graphics_items import _fragment_baseline_shift

    # Concrete Qt DejaVu Sans 11-pixel metrics. QTextLine multiplies the
    # default 1/6 subscript ratio as QFixed(10/64), not as a float 1/6.
    font = SimpleNamespace(ascent=lambda: 10.203125, descent=lambda: 2.59375)
    format_ = QTextCharFormat()
    format_.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
    assert _fragment_baseline_shift(format_, font) == 2.0
    format_.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
    assert _fragment_baseline_shift(format_, font) == -6.40625


@pytest.mark.parametrize(
    "html",
    [
        "<ol><li>one</li><li>two</li></ol>",
        '<p style="background-color:yellow"><b>note</b></p>',
        "H<sub>2</sub>O",
    ],
)
def test_note_bounds_include_all_native_paint(html):
    note = NoteItem(AnnotationCollection())
    note.setHtml(html)
    scene = QGraphicsScene()
    scene.addItem(note)
    bounds = item_export_bounds(note)
    source = note.sceneBoundingRect().adjusted(-20, -20, 20, 20)
    ink = _ink_bounds(_render(scene, source), source)
    assert bounds.adjusted(-0.5, -0.5, 0.5, 0.5).contains(ink)
    if "<ol" in html or "<ul" in html:
        assert bounds == note.sceneBoundingRect()


_COLOR_GLYPH_PROBE = r"""
import hashlib
import json
import sys

from PIL import Image
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QGraphicsScene

from chemvas.features.annotations import arrow_label_html
from chemvas.ui.export.export_scope import item_export_bounds
from chemvas.ui.canvas.graphics_items import ArrowLabelItem

app = QApplication([])
scene = QGraphicsScene()
label = ArrowLabelItem()
label.setFont(QFont("Arial", 12))
label.setHtml(arrow_label_html("A 😀"))
label.setPos(20, 20)
scene.addItem(label)

def paint():
    image = QImage(800, 400, QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, 800, 400), QRectF(0, 0, 200, 100))
    painter.end()
    data = image.constBits().asstring(image.sizeInBytes())
    pixels = Image.frombytes("RGBA", (800, 400), data)
    return hashlib.sha256(data).hexdigest(), pixels.getchannel("A").getbbox()

mode = sys.argv[1]
before = paint() if mode != "measure-first" else None
bounds = item_export_bounds(label) if mode != "control" else None
after = paint()
print(json.dumps({
    "before": before,
    "after": after,
    "bounds": list(bounds.getCoords()) if bounds is not None else None,
}))
"""


@pytest.mark.parametrize("mode", ["paint-first", "measure-first"])
def test_color_font_keeps_native_paint_and_conservative_bounds(mode):
    # Separate processes keep raw-font caches independent. Calling pathForGlyph
    # on a bitmap color glyph can itself change a subsequent native paint.
    def run(order):
        result = subprocess.run(
            [sys.executable, "-c", _COLOR_GLYPH_PROBE, order],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
            env=source_subprocess_env({"QT_QPA_PLATFORM": "offscreen"}),
        )
        return json.loads(result.stdout)

    control = run("control")
    actual = run(mode)
    assert actual["after"] == control["after"]
    if actual["before"] is not None:
        assert actual["before"] == control["before"]
    ink = [value / 4 for value in actual["after"][1]]
    left, top, right, bottom = actual["bounds"]
    assert left <= ink[0] + 0.25
    assert top <= ink[1] + 0.25
    assert right >= ink[2] - 0.25
    assert bottom >= ink[3] - 0.25


@pytest.mark.parametrize("table", ["EBLC", "CBLC", "CPAL", "sbix", "SVG "])
def test_bitmap_font_table_preflight_precedes_outline_extraction(monkeypatch, table):
    # Exercise actual Qt shaping independently of installed bitmap fonts. Only
    # the table-presence boundary is simulated; an outline request is a failure.
    label = _label("H_{2}O\nA")
    label.setRotation(37)
    layout = label.sceneBoundingRect()
    before = label.toHtml(), label.pos(), label.shape()
    requested = []

    def font_table(_font, tag):
        requested.append(tag)
        assert tag not in {"EBDT", "CBDT"}, "Do not read bitmap payloads"
        return b"present" if tag == table else b""

    def no_outline(_font, _glyph):
        pytest.fail("Bitmap preflight must run before pathForGlyph")

    monkeypatch.setattr(QRawFont, "fontTable", font_table)
    monkeypatch.setattr(QRawFont, "pathForGlyph", no_outline)
    assert item_export_bounds(label) == layout
    assert requested[-1] == table
    assert (label.toHtml(), label.pos(), label.shape()) == before


def test_outline_font_without_bitmap_tables_keeps_tight_bounds(monkeypatch):
    label = _label("H_{2}O")
    requested = []
    glyphs = []
    original = QRawFont.pathForGlyph

    def font_table(_font, tag):
        requested.append(tag)
        assert tag not in {"EBDT", "CBDT"}
        return b""

    def outline(font, glyph):
        glyphs.append(glyph)
        return original(font, glyph)

    monkeypatch.setattr(QRawFont, "fontTable", font_table)
    monkeypatch.setattr(QRawFont, "pathForGlyph", outline)
    bounds = item_export_bounds(label)
    assert glyphs
    assert requested
    assert not bounds.isEmpty()
    assert bounds.height() < label.sceneBoundingRect().height()


@pytest.mark.parametrize(
    "decoration", ["background-color:yellow", "text-decoration:underline"]
)
@pytest.mark.parametrize("text", ["A       ", "       ", "A\t  "])
def test_formatted_note_whitespace_retains_layout_extent(decoration, text):
    note = NoteItem(AnnotationCollection())
    note.setHtml(
        f'<p style="white-space:pre-wrap"><span style="{decoration}">{text}</span></p>'
    )
    scene = QGraphicsScene()
    scene.addItem(note)
    source = note.sceneBoundingRect().adjusted(-20, -20, 20, 20)
    ink = _ink_bounds(_render(scene, source), source)
    bounds = item_export_bounds(note)
    assert bounds.adjusted(-0.5, -0.5, 0.5, 0.5).contains(ink)
    # Keep native character advances across platforms, including spaces with
    # decoration but no glyph outlines. The editing layout already owns them.
    assert bounds == note.sceneBoundingRect()
