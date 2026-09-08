from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.layout_qa_service import (
    _atom_label_scene_path,
    _graphics_paint_scene_path,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.mark.parametrize("endpoint", ["start", "end", "both"])
@pytest.mark.parametrize("text", ["O", "N", "NH2", "OMe"])
@pytest.mark.parametrize("angle", [0, 30, 60, 90, 135, 180, 225, 270])
@pytest.mark.parametrize(
    ("style", "order"),
    [
        ("single", 1),
        ("double", 2),
        ("double_center", 2),
        ("double_outer", 2),
        ("triple", 3),
        ("wedge", 1),
        ("hash", 1),
        ("bold_in", 1),
        ("bold_out", 1),
        ("bold_center", 1),
        ("dotted", 1),
        ("dotted_double", 2),
        ("dotted_double_outer", 2),
    ],
)
def test_native_bond_paint_does_not_enter_endpoint_glyphs(
    app, text, angle, style, order, endpoint
):
    canvas = CanvasView(renderer=Renderer())
    try:
        services = canvas_services_for(canvas)
        atom_mutation = services.structure.canvas_atom_mutation_service
        bond_mutation = services.structure.canvas_bond_mutation_service
        a_id = atom_mutation.add_atom(text if endpoint != "end" else "C", 0.0, 0.0)
        radians = math.radians(angle)
        b_id = atom_mutation.add_atom(
            text if endpoint != "start" else "C",
            40.0 * math.cos(radians),
            40.0 * math.sin(radians),
        )
        bond_id = bond_mutation.add_bond(a_id, b_id, order)
        canvas.model.bonds[bond_id].style = style
        canvas.bond_renderer.add_bond_graphics(bond_id)
        labels = [
            atom_items_for(canvas)[aid]
            for aid in (a_id, b_id)
            if aid in atom_items_for(canvas)
        ]
        glyph = _atom_label_scene_path(labels[0])
        for label in labels[1:]:
            glyph = glyph.united(_atom_label_scene_path(label))
        assert not glyph.isEmpty()
        for item in bond_items_for_id(canvas, bond_id):
            painted = _graphics_paint_scene_path(item)
            overlap = glyph.intersected(painted).boundingRect()
            assert overlap.width() <= 0.01 or overlap.height() <= 0.01
    finally:
        canvas.close()
        canvas.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("text", ["O", "NH2"])
@pytest.mark.parametrize("endpoint", ["both", "start"])
@pytest.mark.parametrize("length", [4.0, 12.0, 40.0])
@pytest.mark.parametrize(
    "style",
    ["dotted", "dotted_double", "dotted_double_outer"],
)
def test_native_short_dotted_bond_actual_paint_clears_glyphs(
    app, text, endpoint, length, style
):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage, QPainter, QPainterPath
    from PyQt6.QtWidgets import QGraphicsPathItem, QStyleOptionGraphicsItem

    from chemvas.ui.bond_renderer_access import bond_renderer_for
    from chemvas.ui.canvas_model_access import bonds_for

    def alpha_mask(items=(), glyph=None):
        image = QImage(640, 384, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(8, 8)
        painter.translate(16, 16)
        try:
            if glyph is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(Qt.GlobalColor.black)
                painter.drawPath(glyph)
            else:
                for item in items:
                    painter.save()
                    painter.setTransform(item.sceneTransform(), True)
                    item.paint(painter, QStyleOptionGraphicsItem(), None)
                    painter.restore()
        finally:
            painter.end()
        return image.constBits().asstring(image.sizeInBytes())[3::4]

    canvas = CanvasView(renderer=Renderer())
    try:
        services = canvas_services_for(canvas)
        atoms = services.structure.canvas_atom_mutation_service
        bonds = services.structure.canvas_bond_mutation_service
        a_id = atoms.add_atom(text, 0.0, 0.0)
        b_id = atoms.add_atom(text if endpoint == "both" else "C", length, 0.0)
        order = 1 if style == "dotted" else 2
        bond_id = bonds.add_bond(a_id, b_id, order)
        bond = bonds_for(canvas)[bond_id]
        bond.style = style
        bond_renderer_for(canvas).redraw_bond(bond_id)
        labels = atom_items_for(canvas)
        assert a_id in labels
        if endpoint == "both":
            assert b_id in labels
        glyph = QPainterPath()
        for aid in (a_id, b_id):
            if aid in labels:
                glyph = glyph.united(_atom_label_scene_path(labels[aid]))
        assert not glyph.isEmpty()
        items = bond_items_for_id(canvas, bond_id)
        assert len(items) == order
        paths = [item.path() for item in items if isinstance(item, QGraphicsPathItem)]
        assert len(paths) == 1
        bond_alpha = alpha_mask(items=items)
        glyph_alpha = alpha_mask(glyph=glyph)
        overlap = sum(
            b > 200 and g > 200 for b, g in zip(bond_alpha, glyph_alpha, strict=True)
        )
        assert overlap == 0, f"{overlap} overlapping opaque pixels at 8x"
        if length == 40.0:
            assert not paths[0].isEmpty()
            assert any(alpha > 200 for alpha in bond_alpha)
        if style == "dotted":
            t0, t1 = bond_renderer_for(canvas).trim_line_for_labels(
                a_id, b_id, 0.0, 0.0, length, 0.0
            )
            if t0 == t1:
                assert paths[0].isEmpty()
        assert bonds_for(canvas)[bond_id] is bond
        assert (bond.a, bond.b, bond.order, bond.style) == (a_id, b_id, order, style)
    finally:
        canvas.close()
        canvas.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
