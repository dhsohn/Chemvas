from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QGraphicsPathItem, QGraphicsTextItem

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
