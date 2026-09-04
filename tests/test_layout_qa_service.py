from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QGraphicsPathItem

from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.layout_qa_service import check_canvas_layout
from chemvas.ui.sheet_setup_state import SheetSetupState
from tests.runtime_state import canvas_runtime_state


class _NotePathItem(QGraphicsPathItem):
    def toPlainText(self) -> str:
        return "note"


def _canvas(
    *, notes: list[QGraphicsPathItem], shapes: list[QGraphicsPathItem], sheet: QRectF
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
    note_path = QPainterPath()
    # With Qt's [4, 2] DashLine pattern at width 2, this box sits wholly in
    # the first unpainted top-border gap (x=8..12, accounting for round caps).
    note_path.addRect(QRectF(9.2, -0.2, 1.6, 0.4))
    note = _NotePathItem(note_path)
    note.setPen(QPen(Qt.PenStyle.NoPen))
    note.setBrush(QBrush(QColor("black")))
    canvas = _canvas(
        notes=[note],
        shapes=[shape],
        sheet=QRectF(-20.0, -20.0, 160.0, 100.0),
    )

    report = check_canvas_layout(canvas)

    assert report["counts"]["text-shape-border-overlap"] == 0
    assert report["ok"] is True


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
