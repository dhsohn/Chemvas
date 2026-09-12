from __future__ import annotations

import math
from copy import deepcopy

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state
from chemvas.features.scheme_layout import validate_layout_request
from chemvas.ui.canvas_bond_graphics_state import bond_items_for
from chemvas.ui.canvas_document_state import document_item_lists_for
from chemvas.ui.layout_qa_service import note_paint_scene_path
from chemvas.ui.scheme_layout_service import arrange_canvas, plan_canvas_layout


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _source():
    source = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {
                    "id": offset + vertex,
                    "element": "C",
                    "x": 100 + offset * 40 + 30 * math.cos(vertex * math.pi / 3),
                    "y": 80 + 30 * math.sin(vertex * math.pi / 3),
                }
                for offset in (0, 6)
                for vertex in range(6)
            ],
            "bonds": [
                {"a": offset + vertex, "b": offset + (vertex + 1) % 6, "order": 1}
                for offset in (0, 6)
                for vertex in range(6)
            ],
            "notes": [
                {"text": text, "x": 80 + column * 240, "y": 150 + level * 60}
                for column in range(2)
                for level, text in enumerate(("Compound", "Condition"))
            ],
        }
    )
    source["settings"].update(
        note_box_enabled=True,
        note_box_alpha=1.0,
        note_border_enabled=True,
        note_border_width=1.2,
        note_padding=8.0,
    )
    return source


def _request(source, alignment="row"):
    return validate_layout_request(
        source,
        {
            "format": "chemvas-scheme-layout",
            "version": 1,
            "source_sha256": "a" * 64,
            "caption_alignment": alignment,
            "rows": [
                {
                    "blocks": [
                        {"atoms": list(range(6)), "captions": [0, 1]},
                        {"atoms": list(range(6, 12)), "captions": [2, 3]},
                    ]
                }
            ],
        },
        source_sha256="a" * 64,
    )


@pytest.mark.parametrize("alignment", ["row", "structure"])
@pytest.mark.parametrize("paint", ["fill-and-border", "fill", "border"])
def test_arranged_caption_boxes_clear_bonds_and_each_other_after_reopen(
    tmp_path, alignment, paint
):
    source = _source()
    source["settings"]["note_box_enabled"] = paint != "border"
    source["settings"]["note_border_enabled"] = paint != "fill"
    request = _request(source, alignment)
    original = deepcopy(source)
    with offscreen_canvas(source, command="caption-box-test") as (canvas, _):
        candidate, _ = arrange_canvas(canvas, source, request)
    assert source == original
    output = tmp_path / "arranged.chemvas"
    write_document(output, candidate, version=CANVAS_FILE_VERSION)
    reopened = read_document(output).state
    with offscreen_canvas(reopened, command="caption-box-reopen-test") as (canvas, _):
        notes = document_item_lists_for(canvas)["notes"]
        for column in range(2):
            pieces = [
                piece
                for bond_id in range(column * 6, column * 6 + 6)
                for piece in bond_items_for(canvas)[bond_id]
            ]
            bottom = max(piece.sceneBoundingRect().bottom() for piece in pieces)
            for level in range(2):
                note = notes[column * 2 + level]
                box = note.data(20)
                assert box.isVisible()
                bounds = box.sceneBoundingRect()
                gap = request.caption_gap if level == 0 else request.line_gap
                assert bounds.top() >= bottom + gap - 1e-8
                assert not any(
                    bounds.intersects(piece.sceneBoundingRect()) for piece in pieces
                )
                bottom = bounds.bottom()


@pytest.mark.parametrize(
    "hidden", ["disabled", "transparent", "transparent-paint", "scene-hidden"]
)
def test_unpainted_caption_box_does_not_change_layout(hidden):
    source = _source()
    source["settings"].update(note_box_enabled=False, note_border_enabled=False)
    with offscreen_canvas(source, command="caption-ink-control") as (canvas, _):
        control = plan_canvas_layout(canvas, source, _request(source))
    source["settings"].update(note_box_enabled=True, note_border_enabled=True)
    with offscreen_canvas(source, command="unpainted-caption-box") as (canvas, _):
        for note in document_item_lists_for(canvas)["notes"]:
            box = note.data(20)
            if hidden == "disabled":
                box.setPen(QPen(Qt.PenStyle.NoPen))
                box.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            elif hidden == "transparent":
                box.setOpacity(0.0)
            elif hidden == "transparent-paint":
                box.setPen(QPen(QColor("transparent")))
                box.setBrush(QBrush(QColor("transparent")))
            else:
                box.hide()
            assert not note_paint_scene_path(note).isEmpty()
        plan = plan_canvas_layout(canvas, source, _request(source))
    assert plan == control


def test_transparent_border_does_not_inflate_visible_fill_bounds():
    source = _source()
    with offscreen_canvas(source, command="transparent-caption-border") as (canvas, _):
        notes = document_item_lists_for(canvas)["notes"]
        for note in notes:
            note.data(20).setPen(QPen(Qt.PenStyle.NoPen))
        control = plan_canvas_layout(canvas, source, _request(source))
        for note in notes:
            pen = QPen(QColor("transparent"))
            pen.setWidthF(20.0)
            note.data(20).setPen(pen)
        plan = plan_canvas_layout(canvas, source, _request(source))
    assert plan == control
