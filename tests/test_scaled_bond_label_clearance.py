"""Printed bond ends leave visible air around native atom-label ink."""

import math

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QPainterPath, QPainterPathStroker
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.features.rendering import ACS1996Style
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
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("length,metric", [(40, 20), (40, 85 / 3), (112, 235 / 3)])
@pytest.mark.parametrize(
    "left,right", [("P", "Ar"), ("O", "Me"), ("N", "Cl"), ("NH2", "O")]
)
@pytest.mark.parametrize("angle", [0, 30, 45, 60, 90, 225])
@pytest.mark.parametrize(
    "style,order",
    [("single", 1), ("double", 2), ("triple", 3), ("wedge", 1), ("hash", 1)],
)
def test_scaled_bond_paint_leaves_half_pen_width_around_endpoint_ink(
    app, length, metric, left, right, angle, style, order
):
    renderer = Renderer(ACS1996Style(bond_length_px=metric))
    canvas = CanvasView(renderer=renderer)
    try:
        services = canvas_services_for(canvas)
        atoms = services.structure.canvas_atom_mutation_service
        bonds = services.structure.canvas_bond_mutation_service
        radians = math.radians(angle)
        a_id = atoms.add_atom(left, 0, 0)
        b_id = atoms.add_atom(
            right, length * math.cos(radians), length * math.sin(radians)
        )
        bond_id = bonds.add_bond(a_id, b_id, order)
        canvas.model.bonds[bond_id].style = style
        positions = {aid: (atom.x, atom.y) for aid, atom in canvas.model.atoms.items()}
        canvas.bond_renderer.redraw_bond(bond_id)
        glyph = QPainterPath()
        for aid in (a_id, b_id):
            glyph = glyph.united(_atom_label_scene_path(atom_items_for(canvas)[aid]))
        paint = QPainterPath()
        for item in bond_items_for_id(canvas, bond_id):
            paint = paint.united(_graphics_paint_scene_path(item))
        assert not glyph.isEmpty()
        assert not paint.isEmpty()
        # This tests the full painted bond, not merely its centerline. Expanding
        # the independent native label outline by half a pen width also catches
        # a mathematically clear endpoint that still looks fused when printed.
        stroker = QPainterPathStroker()
        stroker.setWidth(renderer.bond_pen().widthF())
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        stroker.setCurveThreshold(0.001)
        margin = stroker.createStroke(glyph).united(glyph)
        overlap = paint.intersected(margin).boundingRect()
        assert overlap.width() < 0.01 or overlap.height() < 0.01
        assert {
            aid: (atom.x, atom.y) for aid, atom in canvas.model.atoms.items()
        } == positions
        bond = canvas.model.bonds[bond_id]
        assert (bond.a, bond.b, bond.order, bond.style) == (a_id, b_id, order, style)
    finally:
        canvas.close()
        canvas.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
