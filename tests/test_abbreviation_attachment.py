"""Native abbreviation attachment stays on its chemical glyph at every angle."""

from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QByteArray, QEvent, QPointF, Qt
from PyQt6.QtGui import QFontMetricsF, QImage, QPainter, QPainterPath
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.core.document_io import read_exact_document, write_document
from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.features.export import export_scene
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_format_access import file_format_version_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.renderer_style_access import atom_label_offset_px_for

ANGLES = sorted(
    {
        *range(0, 361, 30),
        *(a + epsilon for a in (45, 135, 225, 315) for epsilon in (-1e-6, 0, 1e-6)),
        *(a + epsilon for a in (90, 270) for epsilon in (-1e-4, 1e-4)),
    }
)


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


def _draw(canvas, label, angle, style="single", *, isolated=False):
    radians = math.radians(angle)
    x, y = 80 * math.cos(radians), 80 * math.sin(radians)
    canvas.model = MoleculeModel(
        atoms={0: Atom("C", x, y), 1: Atom(label, 0, 0)},
        bonds=[] if isolated else [Bond(0, 1, 1, style=style)],
        atom_annotations={0: {"formal_charge": 1}},
    )
    expected_model = deepcopy(canvas.model)
    session = canvas_services_for(canvas).document.canvas_document_session_service
    session.apply_state(json.loads(json.dumps(session.snapshot_state())))
    assert canvas.model == expected_model
    return session


def _oxygen_ink_rect(item):
    """Locate O from displayed text and actual font outlines, not anchor metadata."""
    text = item.toPlainText()
    assert text in {"OMe", "MeO"}
    metrics = QFontMetricsF(item.font())
    prefix = text[: text.index("O")]
    margin = item.document().documentMargin()
    path = QPainterPath()
    path.addText(
        QPointF(margin + metrics.horizontalAdvance(prefix), margin + metrics.ascent()),
        item.font(),
        "O",
    )
    return item.mapToScene(path).boundingRect()


def _assert_oxygen_attachment(canvas, raw_label, angle):
    item = atom_items_for(canvas)[1]
    dx = math.cos(math.radians(angle))
    expected_text = raw_label if abs(dx) < 1e-9 else "MeO" if dx > 0 else "OMe"
    assert item.toPlainText() == expected_text
    atom = canvas.model.atoms[1]
    offset = atom_label_offset_px_for(canvas)
    oxygen = _oxygen_ink_rect(item)
    # Font side bearings can offset an optical ink center by a fraction of a
    # pixel from the advance-cell center, but not by the width of the Me group.
    assert oxygen.center().x() == pytest.approx(atom.x + offset, abs=0.6)
    anchor = item.anchor_scene_rect()
    assert anchor is not None
    assert anchor.center().x() == pytest.approx(atom.x + offset, abs=1e-9)
    assert anchor.center().y() == pytest.approx(atom.y - offset, abs=1e-9)
    assert oxygen.intersects(anchor)
    assert canvas.model.atoms[1].element == raw_label


@pytest.mark.parametrize("label", ["OMe", "MeO"])
@pytest.mark.parametrize("angle", ANGLES)
@pytest.mark.parametrize("style", ["single", "wedge", "hash"])
def test_oxygen_glyph_anchors_at_bonded_atom_without_model_changes(
    canvas, label, angle, style
):
    session = _draw(canvas, label, angle, style)
    before = deepcopy(session.snapshot_state())

    labels = canvas_services_for(canvas).atom_label_service
    labels.relayout_atom_labels({0, 1})
    _assert_oxygen_attachment(canvas, label, angle)
    canvas.bond_renderer.redraw_bond(0)
    _assert_oxygen_attachment(canvas, label, angle)

    after = session.snapshot_state()
    assert after["model"] == before["model"]
    assert after["marks"] == before["marks"]
    assert after["model"]["bonds"][0]["style"] == style


@pytest.mark.parametrize("offset", [0.0, 2.0, 5.0])
def test_configured_label_offset_is_applied_to_oxygen_not_abbreviation_center(
    canvas, offset
):
    canvas.renderer.style = replace(canvas.renderer.style, atom_label_offset_px=offset)
    _draw(canvas, "OMe", 90)
    _assert_oxygen_attachment(canvas, "OMe", 90)


@pytest.mark.parametrize("label,angle", [("PhO", 90), ("NH4+", 0), ("NH4+", 90)])
def test_unknown_vertical_and_unreversible_labels_keep_centered_fallback(
    canvas, label, angle
):
    _draw(canvas, label, angle)
    item = atom_items_for(canvas)[1]
    assert item.toPlainText() == label
    assert item.anchor_scene_rect() is None


@pytest.mark.parametrize("label", ["OMe", "MeO", "PhO", "NH4+"])
def test_isolated_labels_keep_typed_order_and_centered_fallback(canvas, label):
    _draw(canvas, label, 90, isolated=True)
    item = atom_items_for(canvas)[1]
    assert item.toPlainText() == label
    assert item.anchor_scene_rect() is None


def test_movement_rotation_and_native_reopen_refresh_attachment_only(canvas, tmp_path):
    session = _draw(canvas, "OMe", 90, "hash")
    original_model = deepcopy(canvas.model)
    mover = canvas_services_for(canvas).interaction.move_controller
    mover.move_atoms({0, 1}, 150, 120)
    _assert_oxygen_attachment(canvas, "OMe", 90)

    # Move only the neighbor around the fixed abbreviation: a native bond
    # geometry refresh must flip display order, never the stored chemical label.
    for angle in (30, 90, 150, 270):
        neighbor = canvas.model.atoms[0]
        anchor = canvas.model.atoms[1]
        target_x = anchor.x + 80 * math.cos(math.radians(angle))
        target_y = anchor.y + 80 * math.sin(math.radians(angle))
        mover.move_atoms({0}, target_x - neighbor.x, target_y - neighbor.y)
        _assert_oxygen_attachment(canvas, "OMe", angle)
        state = deepcopy(session.snapshot_state())
        path = tmp_path / f"rotated-{angle}.chemvas"
        write_document(path, state, file_format_version_for(canvas))
        source_bytes, document = read_exact_document(path)
        assert source_bytes == path.read_bytes()
        session.apply_state(document.state)
        _assert_oxygen_attachment(canvas, "OMe", angle)
        assert session.snapshot_state()["model"] == state["model"]
        assert session.snapshot_state()["marks"] == state["marks"]

    assert canvas.model.bonds == original_model.bonds
    assert canvas.model.atom_annotations == original_model.atom_annotations
    assert canvas.model.atoms[1].element == "OMe"


def _blue_glyph_components(image):
    pixels = {
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if (pixel := image.pixelColor(x, y)).alpha() > 64
        and pixel.blue() > pixel.red() + 40
    }
    components = []
    while pixels:
        first = pixels.pop()
        pending, component = [first], [first]
        while pending:
            x, y = pending.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = x + dx, y + dy
                    if neighbor in pixels:
                        pixels.remove(neighbor)
                        pending.append(neighbor)
                        component.append(neighbor)
        if len(component) >= 4:
            xs, ys = zip(*component, strict=True)
            components.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
    return sorted(components)


@pytest.mark.parametrize(
    "label,angle,style",
    [
        ("OMe", 180, "single"),
        ("MeO", 0, "hash"),
        ("OMe", 60, "single"),
        ("MeO", 90, "single"),
        ("OMe", 120, "wedge"),
        ("MeO", 270, "wedge"),
        ("OMe", 90, "hash"),
        ("MeO", 60, "hash"),
    ],
)
def test_native_oxygen_geometry_reaches_svg_and_png(
    canvas, tmp_path, label, angle, style
):
    session = _draw(canvas, label, angle, style)
    mutation = canvas_services_for(canvas).structure.canvas_atom_mutation_service
    mutation.apply_atom_color(1, "#075CAD")
    _assert_oxygen_attachment(canvas, label, angle)
    before = deepcopy(session.snapshot_state())
    item = atom_items_for(canvas)[1]
    oxygen = _oxygen_ink_rect(item)
    svg_path, png_path = tmp_path / "attachment.svg", tmp_path / "attachment.png"
    svg_plan = export_scene(canvas.scene(), str(svg_path), fmt="svg", margin=4)
    png_plan = export_scene(canvas.scene(), str(png_path), fmt="png", margin=4, dpi=144)
    assert svg_plan == png_plan
    svg = svg_path.read_bytes()
    assert b"<path" in svg and b"<text" not in svg
    png = QImage(str(png_path))
    assert not png.isNull()
    renderer = QSvgRenderer(QByteArray(svg))
    assert renderer.isValid()
    rendered_svg = QImage(png.size(), QImage.Format.Format_ARGB32)
    rendered_svg.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rendered_svg)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    index = 0 if item.toPlainText() == "OMe" else -1
    raster_components = _blue_glyph_components(png)
    vector_components = _blue_glyph_components(rendered_svg)
    assert len(raster_components) == len(vector_components) == 3
    raster_oxygen, vector_oxygen = raster_components[index], vector_components[index]
    assert vector_oxygen == pytest.approx(raster_oxygen, abs=2)
    expected = (
        (oxygen.left() - png_plan.source_x) * png.width() / png_plan.source_w,
        (oxygen.top() - png_plan.source_y) * png.height() / png_plan.source_h,
        (oxygen.right() - png_plan.source_x) * png.width() / png_plan.source_w,
        (oxygen.bottom() - png_plan.source_y) * png.height() / png_plan.source_h,
    )
    assert raster_oxygen == pytest.approx(expected, abs=1.5)
    assert session.snapshot_state() == before
