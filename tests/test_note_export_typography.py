from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageChops, ImageFilter
from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QTextCursor
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from chemvas.features.export import ExportPlan, render_scene_to_svg_bytes
from chemvas.features.export.raster import export_raster_file
from chemvas.features.export.scope import exported_scene
from chemvas.ui.note_item import NoteItem

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module", autouse=True)
def application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    app.setQuitOnLastWindowClosed(False)
    return app


def _render(scene: QGraphicsScene, source: QRectF, svg: bytes | None = None) -> QImage:
    image = QImage(
        round(source.width() * 4),
        round(source.height() * 4),
        QImage.Format.Format_RGBA8888,
    )
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    if svg is None:
        scene.render(painter, QRectF(image.rect()), source)
    else:
        renderer = QSvgRenderer(QByteArray(svg))
        assert renderer.isValid()
        renderer.render(painter, QRectF(image.rect()))
    painter.end()
    return image


def _assert_same_ink(first: QImage, second: QImage) -> None:
    first = first.convertToFormat(QImage.Format.Format_RGBA8888)
    second = second.convertToFormat(QImage.Format.Format_RGBA8888)
    samples = [
        Image.frombytes(
            "RGBA",
            (image.width(), image.height()),
            image.constBits().asstring(image.sizeInBytes()),
        )
        for image in (first, second)
    ]
    # Independently compare each color channel, so backgrounds and colored
    # decorations cannot conceal missing or displaced dark glyphs.
    for channel in range(3):
        masks = [
            sample.getchannel(channel).point(lambda value: 255 if value < 160 else 0)
            for sample in samples
        ]
        for actual, expected in (masks, masks[::-1]):
            ink = actual.histogram()[255]
            if ink:
                missing = ImageChops.subtract(
                    actual, expected.filter(ImageFilter.MaxFilter(3))
                )
                assert missing.histogram()[255] / ink < 0.05


@pytest.mark.parametrize(
    ("html", "angle", "width"),
    [
        ("H<sub>2</sub>O<sup>+</sup>", 0, -1),
        (
            '<span style="font-size:9px">A</span><span style="font-size:9pt">B</span>H<sub>2</sub><sup>+</sup>',
            0,
            -1,
        ),
        (
            '<span style="color:#195b90;background-color:#ffff00;text-decoration:underline">colored</span> <b><i>ΔG‡</i></b><s>strike</s>',
            37,
            -1,
        ),
        ('<p align="center">wrapped long text and H<sub>2</sub>O</p>', 0, 95),
        ("<ul><li>one</li><li>two</li></ul>", 19, -1),
        ("<ol><li>one</li><li>two</li></ol>", 0, -1),
        (
            '<ol type="a"><li style="font-size:9pt;color:red">A</li><li><span style="font-size:9px">B</span>H<sub>2</sub></li></ol>',
            37,
            -1,
        ),
        (
            '<ol type="I"><li>one<ul><li>inner</li></ul></li><li>two</li></ol>',
            19,
            -1,
        ),
    ],
)
def test_note_svg_matches_native_rich_text_and_preserves_editing(
    tmp_path: Path, html: str, angle: float, width: float
) -> None:
    scene = QGraphicsScene()
    note = NoteItem(None)
    note.setData(0, "note")
    font = QFont("DejaVu Sans", 12)
    font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
    note.setFont(font)
    note.setDefaultTextColor(QColor("#195b90"))
    note.setHtml(html)
    note.setTextWidth(width)
    note.setRotation(angle)
    note.setScale(1.25)
    scene.addItem(note)
    source = note.sceneBoundingRect().adjusted(-4, -4, 4, 4)
    before = _render(scene, source)
    original = note.toHtml()
    cursor = note.textCursor()
    cursor.setPosition(1)
    note.setTextCursor(cursor)
    undo_steps = note.document().availableUndoSteps()
    svg = render_scene_to_svg_bytes(scene, source=source, items=[note])
    emitted = [
        element
        for element in ET.fromstring(svg).iter()
        if element.tag.endswith("}text")
    ]
    expected = list(note.export_list_marker_runs())
    assert [
        (element.text, float(element.attrib["font-size"])) for element in emitted
    ] == [(text, font.pixelSize()) for text, font, _color in expected]
    assert b"<image" not in svg
    _assert_same_ink(before, _render(scene, source, svg))
    plan = ExportPlan(
        source_x=source.x(),
        source_y=source.y(),
        source_w=source.width(),
        source_h=source.height(),
        out_w_pt=source.width(),
        out_h_pt=source.height(),
    )
    raster_path = tmp_path / "native.png"
    export_raster_file(scene, str(raster_path), [note], plan, "PNG", 288, "white")
    _assert_same_ink(_render(scene, source, svg), QImage(str(raster_path)))
    assert note.toHtml() == original
    assert note.textCursor().position() == 1
    assert note.document().availableUndoSteps() == undo_steps
    assert _render(scene, source) == before


def test_note_export_respects_parent_clipping_and_restores_after_failure() -> None:
    scene = QGraphicsScene()
    parent = QGraphicsRectItem(0, 0, 70, 35)
    parent.setData(0, "shape")
    parent.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
    scene.addItem(parent)
    note = NoteItem(None)
    note.setParentItem(parent)
    note.setHtml("<b>clipped long text</b><br>second line")
    note.setPos(25, 10)
    source = QRectF(-4, -4, 130, 70)
    before = _render(scene, source)
    # The canonical raster painter honors the parent's clipping. Qt's SVG
    # generator does not implement arbitrary painter clips; do not manufacture
    # an SVG clipping guarantee in this text-only change.
    with exported_scene(scene, [parent]):
        _assert_same_ink(before, _render(scene, source))
    with (
        patch(
            "chemvas.features.export.vector.paint_scene_region",
            side_effect=RuntimeError("paint failed"),
        ),
        pytest.raises(RuntimeError, match="paint failed"),
    ):
        render_scene_to_svg_bytes(scene, source=source, items=[parent])
    assert _render(scene, source) == before


def test_non_note_text_keeps_its_existing_paint_and_note_screen_selection() -> None:
    scene = QGraphicsScene()
    generic = QGraphicsTextItem("unrelated")
    generic.setData(0, "custom-text")
    scene.addItem(generic)
    source = generic.sceneBoundingRect().adjusted(-4, -4, 4, 4)
    assert b"<text" in render_scene_to_svg_bytes(scene, source=source, items=[generic])

    note = NoteItem(None)
    note.setHtml("editable H<sub>2</sub>O")
    baseline = QGraphicsTextItem()
    baseline.setHtml(note.toHtml())
    for item in (note, baseline):
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        item.setSelected(True)
        cursor = item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        item.setTextCursor(cursor)
    scenes = [QGraphicsScene(), QGraphicsScene()]
    for target, item in zip(scenes, (note, baseline), strict=True):
        target.addItem(item)
    source = note.sceneBoundingRect().adjusted(-4, -4, 4, 4)
    assert _render(scenes[0], source) == _render(scenes[1], source)
