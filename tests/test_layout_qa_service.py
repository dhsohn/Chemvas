from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.layout_qa_service import check_canvas_layout
from chemvas.ui.sheet_setup_state import SheetSetupState
from tests.runtime_state import canvas_runtime_state


def test_note_whitespace_does_not_collide_with_another_note() -> None:
    from chemvas.bootstrap.document_cli_shared import offscreen_canvas
    from chemvas.features.document_composition import compose_document_state

    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
            "notes": [
                {"text": "A                 B", "x": 0.0, "y": 0.0},
                {"text": "C", "x": 30.0, "y": 0.0},
            ],
        }
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        assert check_canvas_layout(canvas)["ok"] is True


def test_note_whitespace_does_not_collide_with_shape_border() -> None:
    from chemvas.bootstrap.document_cli_shared import offscreen_canvas
    from chemvas.features.document_composition import compose_document_state

    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
            "notes": [{"text": "A                 B", "x": 0.0, "y": 0.0}],
            "shapes": [
                {
                    "shape_kind": "rect",
                    "left": 30.0,
                    "top": -20.0,
                    "right": 150.0,
                    "bottom": 60.0,
                    "stroke_style": "solid",
                }
            ],
        }
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        assert check_canvas_layout(canvas)["ok"] is True


def _canvas(
    *, notes: list[QGraphicsTextItem], shapes: list[QGraphicsPathItem], sheet: QRectF
) -> SimpleNamespace:
    return SimpleNamespace(
        runtime_state=canvas_runtime_state(
            scene_items_state=CanvasSceneItemsState(
                note_items=notes,
                shape_items=shapes,
            ),
            sheet_setup_state=SheetSetupState(rect=sheet),
        )
    )


@pytest.mark.parametrize(
    "html",
    [
        "<p><b>Bold</b> and <i>italic</i></p><p>second line</p>",
        '<p><span style="font-size: 24pt">Large</span> small</p>',
    ],
)
def test_transformed_rich_text_still_reports_visible_overlap(html: str) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    notes = [QGraphicsTextItem(), QGraphicsTextItem()]
    for note in notes:
        note.setHtml(html)
        note.setRotation(37)
        note.setScale(1.5)
        note.setPos(100, 100)
    canvas = _canvas(notes=notes, shapes=[], sheet=QRectF(-1000, -1000, 2000, 2000))
    assert check_canvas_layout(canvas)["counts"]["text-text-overlap"] == 1
    notes[1].setPos(500, 500)
    assert check_canvas_layout(canvas)["ok"] is True


def test_transparent_text_fragment_does_not_report_visible_overlap() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    note = QGraphicsTextItem()
    note.setHtml('<span style="color: transparent">Hidden</span>')
    other = QGraphicsTextItem("Hidden")
    canvas = _canvas(
        notes=[note, other], shapes=[], sheet=QRectF(-100, -100, 1000, 1000)
    )
    assert check_canvas_layout(canvas)["ok"] is True
    note.setHtml('<span style="color: black">Hidden</span>')
    assert check_canvas_layout(canvas)["counts"]["text-text-overlap"] == 1


@pytest.mark.parametrize(
    "style",
    [
        "color:transparent;background-color:red",
        "text-decoration:underline",
        "text-decoration:overline",
        "text-decoration:line-through",
    ],
)
def test_painted_rich_text_whitespace_is_checked(style: str) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    notes = [QGraphicsTextItem(), QGraphicsTextItem()]
    for note in notes:
        note.setHtml(f'<span style="{style}">&nbsp;&nbsp;&nbsp;</span>')
        note.setPos(100, 100)
        note.setRotation(23)
        note.setScale(1.5)
    canvas = _canvas(notes=notes, shapes=[], sheet=QRectF(0, 0, 10, 10))
    report = check_canvas_layout(canvas)
    assert report["counts"]["text-text-overlap"] == 1
    assert report["counts"]["outside-sheet"] == 2


@pytest.mark.parametrize(
    "style",
    [
        "color:transparent;background-color:red",
        "text-decoration:underline",
        "text-decoration:overline",
        "text-decoration:line-through",
    ],
)
@pytest.mark.parametrize("alignment", ["baseline", "super", "sub"])
def test_rich_text_border_collision_matches_native_paint(
    style: str, alignment: str
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    note = QGraphicsTextItem()
    note.setHtml(
        f'<span style="font-size:24pt;vertical-align:{alignment};{style}">A{"&nbsp;" * 12}B</span>'
    )
    scene = QGraphicsScene()
    scene.addItem(note)
    bounds = note.sceneBoundingRect()
    scale = 4
    image = QImage(
        int(bounds.width() * scale) + 1,
        int(bounds.height() * scale) + 1,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    scene.render(
        painter, QRectF(0, 0, bounds.width() * scale, bounds.height() * scale), bounds
    )
    painter.end()
    column = int(bounds.width() * scale / 2)
    painted_rows = [
        row
        for row in range(image.height())
        if image.pixelColor(column, row).alpha() > 200
    ]
    assert painted_rows, "Qt must actually paint the whitespace for this regression"
    row = painted_rows[len(painted_rows) // 2]
    x, y = bounds.x() + (column + 0.5) / scale, bounds.y() + (row + 0.5) / scale
    border = QPainterPath()
    border.addRect(QRectF(x - 0.05, y - 0.05, 0.1, 0.1))
    shape = QGraphicsPathItem(border)
    shape.setPen(QPen(QColor("black"), 0.1))
    canvas = _canvas(notes=[note], shapes=[shape], sheet=QRectF(-100, -100, 1000, 1000))
    assert check_canvas_layout(canvas)["counts"]["text-shape-border-overlap"] == 1


@pytest.mark.parametrize(
    ("html", "width"),
    [
        (
            '<span style="color:transparent;background-color:red">abc אב</span><span style="color:transparent">גד xyz</span>',
            -1,
        ),
        ('<span style="color:transparent;background-color:red">A B C D E F</span>', 65),
        ('<span style="color:transparent;background-color:red">A<br>B</span>', 65),
        ('<p style="color:transparent;background-color:red">A B</p>', 65),
        (
            '<p style="color:transparent;background-color:red">A</p><p style="color:transparent">much longer line</p>',
            -1,
        ),
    ],
)
def test_rich_background_visual_runs_match_native_paint(html: str, width: int) -> None:
    from chemvas.ui.layout_qa_service import _note_paint_scene_path

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    note = QGraphicsTextItem()
    note.setFont(QFont("Sans", 24))
    note.setHtml(html)
    note.setTextWidth(width)
    scene = QGraphicsScene()
    scene.addItem(note)
    bounds = note.sceneBoundingRect()
    image = QImage(
        int(bounds.width()) + 1,
        int(bounds.height()) + 1,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    scene.render(painter, bounds, bounds)
    painter.end()
    paint = _note_paint_scene_path(note)
    checked = 0
    for y in range(2, image.height() - 2):
        for x in range(2, image.width() - 2):
            # Ignore antialiased boundaries; compare interiors and clear gaps
            # against the renderer rather than deriving expected layout metrics.
            neighborhood = {
                image.pixelColor(x + dx, y + dy).alpha()
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
            }
            if neighborhood not in ({0}, {255}):
                continue
            assert paint.contains(QPointF(x + 0.5, y + 0.5)) == (neighborhood == {255})
            checked += 1
    assert checked > 100


def test_dashed_shape_gap_does_not_report_a_text_border_overlap() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    shape_path = QPainterPath()
    shape_path.addRect(QRectF(0.0, 0.0, 100.0, 40.0))
    shape = QGraphicsPathItem(shape_path)
    pen = QPen(QColor("black"), 2.0, Qt.PenStyle.DashLine)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    shape.setPen(pen)
    shape.setBrush(QBrush(QColor(0, 0, 0, 0)))
    # With Qt's [4, 2] DashLine pattern at width 2, this glyph sits wholly in
    # the first unpainted top-border gap (x=8..12, accounting for round caps).
    note = QGraphicsTextItem("I")
    note.setFont(QFont("Sans", 10))
    note.setScale(0.04)
    note.setPos(9.2, -0.4)
    canvas = _canvas(
        notes=[note],
        shapes=[shape],
        sheet=QRectF(-20.0, -20.0, 160.0, 100.0),
    )

    report = check_canvas_layout(canvas)

    assert report["counts"]["text-shape-border-overlap"] == 0
    assert report["ok"] is True
    pen.setStyle(Qt.PenStyle.SolidLine)
    shape.setPen(pen)
    assert check_canvas_layout(canvas)["counts"]["text-shape-border-overlap"] == 1


def test_fully_transparent_shape_outside_sheet_is_ignored() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    path = QPainterPath()
    path.addRect(QRectF(100.0, 100.0, 20.0, 20.0))
    shape = QGraphicsPathItem(path)
    shape.setPen(QPen(Qt.PenStyle.NoPen))
    shape.setBrush(QBrush(QColor(0, 0, 0, 0)))
    canvas = _canvas(
        notes=[],
        shapes=[shape],
        sheet=QRectF(-10.0, -10.0, 20.0, 20.0),
    )

    report = check_canvas_layout(canvas)

    assert report["counts"]["outside-sheet"] == 0
    assert report["warning_count"] == 0
    assert report["ok"] is True
