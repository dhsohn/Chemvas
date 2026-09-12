"""Real Qt label ink, not the editable/hit rectangle, clears bond paint."""

import math
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFont, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.ui.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    atom_items_for,
)
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_geometry_controller import CanvasGeometryController
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_service_ports import geometry_controller_for_access
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.graphics_items import AtomLabelItem
from chemvas.ui.layout_qa_service import _atom_label_scene_path
from tests.runtime_state import canvas_runtime_state


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def test_native_oxygen_bond_clears_ink_without_document_box_gap(app):
    canvas = CanvasView(renderer=Renderer())
    try:
        services = canvas_services_for(canvas)
        a = services.structure.canvas_atom_mutation_service.add_atom("O", 0, 0)
        b = services.structure.canvas_atom_mutation_service.add_atom("C", 40, 0)
        bond = services.structure.canvas_bond_mutation_service.add_bond(a, b)
        canvas.bond_renderer.add_bond_graphics(bond)
        item = atom_items_for(canvas)[a]
        controller = geometry_controller_for_access(canvas)
        bounds, hit, pos = item.boundingRect(), item.shape(), item.pos()
        model_positions = {k: (v.x, v.y) for k, v in canvas.model.atoms.items()}
        line_item = bond_items_for_id(canvas, bond)[0]
        line = line_item.line()
        ink = _atom_label_scene_path(item)
        # Native baseline: x1=10.32375 at length 40 (document margins).
        assert line.x1() < item.layout_scene_bounding_rect().right() - 1.0
        assert item.export_scene_bounding_rect() == ink.boundingRect()
        assert line.x1() > ink.boundingRect().right()
        centerline = QPainterPath(line.p1())
        centerline.lineTo(line.p2())
        assert (
            not QPainterPathStroker(line_item.pen())
            .createStroke(centerline)
            .intersects(ink)
        )
        before = controller.trim_line_for_labels(a, b, 0, 0, 40, 0)
        assert before[0] * 40 == pytest.approx(line.x1())
        radius = item._hit_radius
        item.set_hit_radius(80)
        assert controller.trim_line_for_labels(a, b, 0, 0, 40, 0) == before
        item.set_hit_radius(radius)
        assert item.boundingRect() == bounds
        assert item.shape() == hit
        assert item.pos() == pos
        assert {k: (v.x, v.y) for k, v in canvas.model.atoms.items()} == model_positions
    finally:
        canvas.close()
        canvas.deleteLater()


def _label_controller(
    text, *, placement="center", width=1.5, size=12, transformed=False
):
    item = AtomLabelItem(text, hit_radius=30)
    item.setFont(QFont("DejaVu Sans", size))
    if placement == "stack-below":
        item.set_stack_anchor("N", hydrogens_below=True)
    elif placement == "stack-above":
        item.set_stack_anchor("N", hydrogens_below=False)
    elif placement == "end":
        item.set_anchor("N", at_end=True)
    elif placement == "start":
        item.set_anchor(text[0])
    center = item.anchor_center()
    if center is None:
        center = item.mapFromScene(item.layout_scene_bounding_rect().center())
    item.setPos(-center)
    if transformed:
        item.setTransformOriginPoint(center)
        item.setRotation(27)
        item.setScale(1.4)
    canvas = SimpleNamespace(
        renderer=SimpleNamespace(
            style=SimpleNamespace(bond_line_width=width),
            bond_line_width=lambda: width,
        ),
        runtime_state=canvas_runtime_state(
            atom_graphics_state=CanvasAtomGraphicsState(atom_items={1: item})
        ),
    )
    return item, CanvasGeometryController(canvas)


@pytest.mark.parametrize(
    "text,placement",
    [
        ("O", "center"),
        ("N", "center"),
        ("CO2Me", "center"),
        ("NH2", "start"),
        ("H2N", "end"),
        ("OMe", "start"),
        ("NH2", "stack-below"),
        ("NH2", "stack-above"),
    ],
)
@pytest.mark.parametrize("size,transformed", [(12, False), (18, True)])
def test_directed_bond_stroke_clears_all_native_label_runs(
    app, text, placement, size, transformed
):
    item, controller = _label_controller(
        text, placement=placement, size=size, transformed=transformed
    )
    ink = _atom_label_scene_path(item)
    bounds, hit, pos = item.boundingRect(), item.shape(), item.pos()
    assert not item.glyph_path().isEmpty()
    assert (
        item.mapToScene(item.glyph_path()).boundingRect().intersects(ink.boundingRect())
    )
    for degrees in range(0, 360, 15):
        angle = math.radians(degrees)
        end = QPointF(100 * math.cos(angle), 100 * math.sin(angle))
        start_t, end_t = controller.trim_line_for_labels(
            1, None, 0, 0, end.x(), end.y()
        )
        assert 0 <= start_t < end_t == 1
        line = QPainterPath(end * start_t)
        line.lineTo(end)
        stroke = QPainterPathStroker(QPen(0, 1.5)).createStroke(line)
        assert not stroke.intersects(ink), (text, placement, degrees, start_t)
        reverse = controller.trim_line_for_labels(None, 1, end.x(), end.y(), 0, 0)
        assert reverse == pytest.approx((0, 1 - start_t))
    assert item.boundingRect() == bounds
    assert item.shape() == hit
    assert item.pos() == pos


def test_counter_does_not_emit_bond_inside_oxygen(app):
    item, controller = _label_controller("O")
    ink = item.mapToScene(item.glyph_path())
    assert not ink.contains(QPointF(0, 0))
    start, end = controller.trim_line_for_labels(1, None, 0, 0, 40, 0)
    assert 40 * start > ink.boundingRect().right()
    assert end == 1


@pytest.mark.parametrize(
    "text,axis", [("C", "right"), ("N", "up"), ("N", "down"), ("H", "up")]
)
def test_open_letters_keep_bond_outside_the_glyph_interior(app, text, axis):
    item, controller = _label_controller(text)
    ink = item.mapToScene(item.glyph_path()).boundingRect()
    endpoint = {
        "right": QPointF(100, 0),
        "up": QPointF(0, -100),
        "down": QPointF(0, 100),
    }[axis]
    before = (item.pos(), item.boundingRect(), item.shape())
    start, end = controller.trim_line_for_labels(
        1, None, 0, 0, endpoint.x(), endpoint.y()
    )
    boundary = {"right": ink.right(), "up": -ink.top(), "down": ink.bottom()}[axis]
    assert start * 100 > boundary
    assert end == 1
    # Picking padding is not a typography/figure spacing setting.
    item.set_hit_radius(80)
    assert controller.trim_line_for_labels(
        1, None, 0, 0, endpoint.x(), endpoint.y()
    ) == (start, end)
    assert item.pos() == before[0]


def test_fully_occluded_short_bond_does_not_force_span_through_ink(app):
    item, controller = _label_controller("O")
    # Ending inside the right stroke cannot be repaired by forcing a 2% span.
    right = item.mapToScene(item.glyph_path()).boundingRect().right()
    start, end = controller.trim_line_for_labels(1, None, 0, 0, right, 0)
    assert start >= end


@pytest.mark.parametrize("degrees", [0, 45, 90, 135])
def test_explicit_stroke_width_clears_bold_paint(app, degrees):
    item, controller = _label_controller("N")
    angle = math.radians(degrees)
    end = QPointF(100 * math.cos(angle), 100 * math.sin(angle))
    normal, _ = controller.trim_line_for_labels(1, None, 0, 0, end.x(), end.y())
    wide, _ = controller.trim_line_for_labels(
        1, None, 0, 0, end.x(), end.y(), stroke_width=9.0
    )
    assert wide > normal
    line = QPainterPath(end * wide)
    line.lineTo(end)
    assert (
        not QPainterPathStroker(QPen(0, 9.0))
        .createStroke(line)
        .intersects(_atom_label_scene_path(item))
    )


def test_empty_or_missed_glyphs_do_not_fall_back_to_hit_radius(app):
    for text in ("", " ", "O"):
        item, controller = _label_controller(text)
        assert controller.trim_line_for_labels(1, None, 0, 70, 100, 70) == (0, 1)
        if not text.strip():
            assert controller.trim_line_for_labels(1, None, 0, 0, 40, 0) == (0, 1)
