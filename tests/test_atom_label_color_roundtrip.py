from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QByteArray, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.domain.document import Atom, MoleculeModel
from chemvas.features.export import export_scene
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.history_atom_position_restore import set_atom_positions_for_history

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = CanvasView(renderer=Renderer())
    yield view
    view.deleteLater()
    app.processEvents()


def _assert_ink_color(image: QImage, color: str) -> None:
    assert not image.isNull()
    pixels = Counter(
        pixel.name()
        for y in range(image.height())
        for x in range(image.width())
        if (pixel := image.pixelColor(x, y)).alpha() == 255
    )
    expected = QColor(color).name()
    assert pixels[expected] >= 10, pixels
    if expected != "#000000":
        assert pixels["#000000"] == 0, pixels


def _assert_scene_and_exports(canvas, atom_id: int, color: str, tmp_path: Path):
    item = atom_items_for(canvas)[atom_id]
    assert item.scene() is canvas.scene()
    source = item.sceneBoundingRect().adjusted(-2.0, -2.0, 2.0, 2.0)
    image = QImage(256, 192, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        canvas.scene().render(painter, QRectF(image.rect()), source)
    finally:
        painter.end()
    _assert_ink_color(image, color)
    assert item.defaultTextColor() == QColor(color)

    svg_path = tmp_path / "label.svg"
    export_scene(canvas.scene(), str(svg_path), fmt="svg", items=[item], margin=2.0)
    svg = svg_path.read_bytes()
    assert b"<path" in svg
    assert b"<text" not in svg
    svg_renderer = QSvgRenderer(QByteArray(svg))
    assert svg_renderer.isValid()
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        svg_renderer.render(painter)
    finally:
        painter.end()
    _assert_ink_color(image, color)

    png_path = tmp_path / "label.png"
    export_scene(
        canvas.scene(), str(png_path), fmt="png", items=[item], margin=2.0, dpi=600
    )
    _assert_ink_color(QImage(str(png_path)), color)


@pytest.mark.parametrize("label", ["O", "H", "Ar′", "NH2"])
@pytest.mark.parametrize("color", ["#075CAD", "#000000"])
def test_saved_atom_color_reaches_scene_and_exports(canvas, tmp_path, label, color):
    canvas.model = MoleculeModel(atoms={0: Atom(label, 100.0, 100.0, color=color)})
    session = canvas_services_for(canvas).document.canvas_document_session_service
    state = session.snapshot_state()
    assert state["model"]["atoms"][0]["color"] == color

    session.apply_state(json.loads(json.dumps(state)))

    assert canvas.model.atoms[0].color == color
    assert atom_items_for(canvas)[0].toPlainText() == label
    _assert_scene_and_exports(canvas, 0, color, tmp_path)


def test_default_atom_color_does_not_inherit_renderer_override(canvas, tmp_path):
    canvas.renderer.style = replace(canvas.renderer.style, atom_color="#31A354")
    mutation = canvas_services_for(canvas).structure.canvas_atom_mutation_service

    atom_id = mutation.add_atom("O", 100.0, 100.0)

    assert canvas.model.atoms[atom_id].color == "#000000"
    _assert_scene_and_exports(canvas, atom_id, "#000000", tmp_path)


@pytest.mark.parametrize("label", ["O", "H", "Ar′"])
@pytest.mark.parametrize(
    "operation", ["restore", "relabel", "reposition", "update", "document-restore"]
)
def test_atom_color_survives_label_refresh(canvas, tmp_path, label, operation):
    services = canvas_services_for(canvas)
    mutation = services.structure.canvas_atom_mutation_service
    labels = services.atom_label_service
    session = services.document.canvas_document_session_service
    atom_id = mutation.add_atom(label, 100.0, 100.0)
    mutation.apply_atom_color(atom_id, "#075CAD")
    before_item = atom_items_for(canvas)[atom_id]
    before_position = before_item.pos()
    expected_color = "#075CAD"

    if operation == "restore":
        saved_atom = session.snapshot_state()["model"]["atoms"][atom_id]
        mutation.remove_atom_only(atom_id)
        mutation.restore_atom_from_state(atom_id, saved_atom)
        assert atom_items_for(canvas)[atom_id] is not before_item
    elif operation == "relabel":
        labels.add_or_update_atom_label(atom_id, "N", allow_merge=False)
        _assert_scene_and_exports(canvas, atom_id, expected_color, tmp_path)
        services.history_service.undo()
        assert canvas.model.atoms[atom_id].element == label
        _assert_scene_and_exports(canvas, atom_id, expected_color, tmp_path)
        services.history_service.redo()
        assert canvas.model.atoms[atom_id].element == "N"
        _assert_scene_and_exports(canvas, atom_id, expected_color, tmp_path)
        labels.add_or_update_atom_label(atom_id, label, allow_merge=False)
    elif operation == "reposition":
        set_atom_positions_for_history(canvas, {atom_id: (140.0, 120.0)})
        labels.relayout_atom_label(atom_id)
        assert atom_items_for(canvas)[atom_id].pos() != before_position
        assert (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y) == (
            140.0,
            120.0,
        )
    elif operation == "update":
        expected_color = "#C94A28"
        canvas.model.atoms[atom_id].color = expected_color
        labels.add_or_update_atom_label(atom_id, label, allow_merge=False)
        assert atom_items_for(canvas)[atom_id] is before_item
    else:
        session.apply_state(json.loads(json.dumps(session.snapshot_state())))
        assert atom_items_for(canvas)[atom_id] is not before_item

    assert QColor(canvas.model.atoms[atom_id].color) == QColor(expected_color)
    assert atom_items_for(canvas)[atom_id].toPlainText() == label
    _assert_scene_and_exports(canvas, atom_id, expected_color, tmp_path)
    stored_color = session.snapshot_state()["model"]["atoms"][atom_id]["color"]
    assert QColor(stored_color) == QColor(expected_color)


def test_document_keeps_distinct_atom_colors_on_the_same_scene(canvas, tmp_path):
    canvas.model = MoleculeModel(
        atoms={
            0: Atom("O", 100.0, 100.0, color="#075CAD"),
            1: Atom("H", 160.0, 100.0, color="#C94A28"),
            2: Atom("Ar′", 220.0, 100.0),
        }
    )
    session = canvas_services_for(canvas).document.canvas_document_session_service
    state = session.snapshot_state()

    session.apply_state(json.loads(json.dumps(state)))

    for atom_id, atom in canvas.model.atoms.items():
        assert atom.color == state["model"]["atoms"][atom_id]["color"]
        _assert_scene_and_exports(canvas, atom_id, atom.color, tmp_path)
