"""Directional attachment for generic oxygen and fixed-spelling alkyl labels."""

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QTextLayout
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.core.document_io import read_exact_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.ui.canvas.canvas_view import CanvasView
from tests.test_abbreviation_attachment import _draw


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def canvas(app):
    view = CanvasView(renderer=Renderer())
    yield view
    view.close()
    view.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _assert_attachment(canvas, raw, angle):
    item = canvas.runtime_state.atom_graphics_state.atom_items[1]
    right = math.cos(math.radians(angle)) > 0
    if raw in {"OR", "RO"}:
        expected = "RO" if right else "OR"
    else:
        expected = raw
    assert item.toPlainText() == expected
    layout = QTextLayout(expected, item.font())
    layout.beginLayout()
    line = layout.createLine()
    layout.endLayout()
    index = len(expected) - 1 if right else 0
    left = line.cursorToX(index)[0]
    right_edge = line.cursorToX(index + 1)[0]
    margin = item.document().documentMargin()
    # Attachment centers the facing character's advance cell, which need not
    # share its ink center (notably the right side bearing of Windows "r").
    center = item.mapToScene(QPointF(margin + (left + right_edge) / 2, 0))
    offset = canvas.renderer.style.atom_label_offset_px
    assert center.x() == pytest.approx(canvas.model.atoms[1].x + offset, abs=1e-6)
    assert canvas.model.atoms[1].element == raw


@pytest.mark.parametrize("raw", ["OR", "RO", "tBu", "t-Bu", "i-Pr"])
@pytest.mark.parametrize("angle", [30, 60, 80, 100, 120, 150, 240, 300])
@pytest.mark.parametrize("style", ["single", "wedge", "hash"])
def test_diagonal_attachment_uses_facing_glyph(canvas, raw, angle, style):
    _draw(canvas, raw, angle, style)
    _assert_attachment(canvas, raw, angle)


@pytest.mark.parametrize("raw", ["OR", "RO", "tBu", "t-Bu", "i-Pr"])
def test_relayout_save_and_headless_keep_attachment_and_raw_label(
    canvas, raw, tmp_path
):
    session = _draw(canvas, raw, 60)
    _assert_attachment(canvas, raw, 60)
    neighbor = canvas.model.atoms[0]
    neighbor.x, neighbor.y = -40, 40 * math.sqrt(3)
    canvas.bond_renderer.redraw_bond(0)
    _assert_attachment(canvas, raw, 120)
    path = tmp_path / "substituent.chemvas"
    write_document(path, session.snapshot_state(), CANVAS_FILE_VERSION)
    _, reopened = read_exact_document(path)
    assert reopened.state["model"]["atoms"]["1"]["element"] == raw
    live = canvas.runtime_state.atom_graphics_state.atom_items[1]
    with offscreen_document_scene(reopened.state, command="anchor-test") as scene:
        item = scene.state.atom_graphics_state.atom_items[1]
        assert item.toPlainText() == live.toPlainText()
        assert item.glyph_path() == live.glyph_path()
        assert item.pos() == live.pos()


@pytest.mark.parametrize("raw", ["OR", "RO", "tBu", "t-Bu", "i-Pr"])
def test_isolated_substituent_stays_as_typed(canvas, raw):
    _draw(canvas, raw, 60, isolated=True)
    item = canvas.runtime_state.atom_graphics_state.atom_items[1]
    assert item.toPlainText() == raw
    assert item.anchor_scene_rect() is None
