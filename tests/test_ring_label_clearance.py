"""Graph-only rings and vertical label attachment must match editor rendering."""

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QPolygonF
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.scene_render_access import scene_render_context_for
from tests.test_atom_glyph_bond_clearance import _label_controller


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


def _ring(canvas, *, reverse=False, angle=0, closed=True):
    services = canvas_services_for(canvas).structure
    atoms = services.canvas_atom_mutation_service
    bonds = services.canvas_bond_mutation_service
    ids = [
        atoms.add_atom(
            "C",
            40 * math.cos(math.radians(angle + i * 60)),
            40 * math.sin(math.radians(angle + i * 60)),
        )
        for i in range(6)
    ]
    edges = []
    for i in range(6 if closed else 5):
        a, b = ids[i], ids[(i + 1) % 6]
        edge = bonds.add_bond(
            *((b, a) if reverse != (i == 4) else (a, b)), 2 if i % 2 == 0 else 1
        )
        canvas.bond_renderer.add_bond_graphics(edge)
        edges.append(edge)
    return ids, edges


def _assert_inside(canvas, ids, edges):
    polygon = QPolygonF(
        [QPointF(canvas.model.atoms[i].x, canvas.model.atoms[i].y) for i in ids]
    )
    for edge in edges:
        bond = canvas.model.bonds[edge]
        if bond.order != 2:
            continue
        line = bond_items_for_id(canvas, edge)[1].line()
        for point in (line.p1(), line.center(), line.p2()):
            assert polygon.containsPoint(point, Qt.FillRule.OddEvenFill), (edge, point)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("angle", [0, 30, 90, 167])
def test_graph_only_benzene_double_strokes_are_inside(canvas, reverse, angle):
    ids, edges = _ring(canvas, reverse=reverse, angle=angle)
    assert not scene_render_context_for(canvas).state.scene_items_state.ring_items
    _assert_inside(canvas, ids, edges)


def test_closing_opening_and_restoring_cycle_refreshes_remote_double(canvas):
    ids, edges = _ring(canvas, closed=False, reverse=True)
    mutation = canvas_services_for(canvas).structure.canvas_bond_mutation_service
    middle = edges[2]
    geometry = scene_render_context_for(canvas).geometry
    assert geometry.ring_center_for_bond(canvas.model.bonds[middle]) is None
    closing = mutation.add_bond(ids[-1], ids[0])
    canvas.bond_renderer.add_bond_graphics(closing)
    _assert_inside(canvas, ids, edges)
    assert geometry.ring_center_for_bond(canvas.model.bonds[middle]) is not None
    mutation.remove_bond_by_id(closing)
    assert geometry.ring_center_for_bond(canvas.model.bonds[middle]) is None
    mutation.restore_bond_from_state(closing, {"a": ids[-1], "b": ids[0]})
    _assert_inside(canvas, ids, edges)


@pytest.mark.parametrize("text", ["Ph", "H", "N"])
@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("size", [12, 24])
def test_vertical_bond_clears_label_body(app, text, sign, size):
    item, geometry = _label_controller(text, size=size)
    ink = item.mapToScene(item.glyph_path()).boundingRect()
    start, end = geometry.trim_line_for_labels(1, None, 0, 0, 0, sign * 100)
    boundary = ink.bottom() if sign > 0 else -ink.top()
    assert start * 100 > boundary
    assert end == 1
    reverse = geometry.trim_line_for_labels(None, 1, 0, sign * 100, 0, 0)
    assert reverse == pytest.approx((0, 1 - start))


def test_native_vertical_ph_line_clears_both_labels(canvas):
    services = canvas_services_for(canvas).structure
    a = services.canvas_atom_mutation_service.add_atom("Ph", 0, 0)
    b = services.canvas_atom_mutation_service.add_atom("Ph", 0, 70)
    edge = services.canvas_bond_mutation_service.add_bond(a, b)
    canvas.bond_renderer.add_bond_graphics(edge)
    line = bond_items_for_id(canvas, edge)[0].line()
    first, last = (atom_items_for(canvas)[i] for i in (a, b))
    assert line.y1() > first.mapToScene(first.glyph_path()).boundingRect().bottom()
    assert line.y2() < last.mapToScene(last.glyph_path()).boundingRect().top()


@pytest.mark.parametrize("reverse", [False, True])
def test_exterior_substituents_do_not_pull_ring_double_outward(canvas, reverse):
    from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
    from chemvas.ui.canvas_document_state import snapshot_canvas_document_state

    ids, edges = _ring(canvas, reverse=reverse)
    services = canvas_services_for(canvas).structure
    # Long substituent bonds make a neighbour-average heuristic point outside
    # the ring, as in the user's MeO/Ph-substituted phosphorus example.
    for atom_id in ids[:2]:
        atom = canvas.model.atoms[atom_id]
        outside = services.canvas_atom_mutation_service.add_atom(
            "O", atom.x + 100 * math.cos(math.pi / 6), atom.y + 50
        )
        edge = services.canvas_bond_mutation_service.add_bond(atom_id, outside)
        canvas.bond_renderer.add_bond_graphics(edge)
    _assert_inside(canvas, ids, edges)
    polygon = QPolygonF(
        [QPointF(canvas.model.atoms[i].x, canvas.model.atoms[i].y) for i in ids]
    )
    with offscreen_document_scene(
        snapshot_canvas_document_state(canvas), command="ring-substituent-test"
    ) as scene:
        for edge in edges[::2]:
            line = scene.state.bond_graphics_state.bond_items[edge][1].line()
            assert polygon.containsPoint(line.center(), Qt.FillRule.OddEvenFill)


def test_ring_queries_scan_topology_once_per_graph_revision(canvas, monkeypatch):
    from unittest.mock import Mock

    from chemvas.ui import scene_geometry

    ids, edges = _ring(canvas)
    context = scene_render_context_for(canvas)
    geometry = context.geometry

    class CountedBonds(list):
        scans = 0

        def __iter__(self):
            self.scans += 1
            return super().__iter__()

    bonds = CountedBonds(canvas.model.bonds)
    canvas.model.bonds = bonds
    context.state.graph_state.bump_version()
    finder = Mock(wraps=scene_geometry.find_rings)
    monkeypatch.setattr(scene_geometry, "find_rings", finder)
    for _ in range(4):
        for edge in edges:
            assert geometry.ring_center_for_bond(bonds[edge]) is not None
            geometry.ring_center_3d_for_bond(bonds[edge])
    assert bonds.scans == 1
    assert finder.call_count == 1
    before = geometry.ring_center_for_bond(bonds[edges[0]])
    for atom_id in ids:
        canvas.model.atoms[atom_id].x += 12
    after = geometry.ring_center_for_bond(bonds[edges[0]])
    assert after.x() == pytest.approx(before.x() + 12)
    assert bonds.scans == 1
    # Graph reset can reuse the same revision number; its new neighbor map
    # must invalidate the cache even when the model object is retained.
    revision = context.state.graph_state.graph_version
    context.state.graph_state.reset()
    context.state.graph_state.graph_version = revision
    geometry.ring_center_for_bond(bonds[edges[0]])
    assert bonds.scans == 2
    assert finder.call_count == 2


def test_failed_ring_edit_then_different_cycle_does_not_reuse_topology(canvas):
    from chemvas.ui.transactions.document import document_transaction

    ids, edges = _ring(canvas, closed=False)
    mutation = canvas_services_for(canvas).structure.canvas_bond_mutation_service
    for edge in edges:
        bond = canvas.model.bonds[edge]
        mutation.restore_bond_from_state(edge, {"a": bond.a, "b": bond.b, "order": 1})
    context = scene_render_context_for(canvas)
    version = context.state.graph_state.graph_version
    with pytest.raises(RuntimeError, match="injected") as failure:
        with document_transaction(canvas):
            closing = mutation.add_bond(ids[-1], ids[0], 2)
            canvas.bond_renderer.add_bond_graphics(closing)
            assert (
                context.geometry.ring_center_for_bond(canvas.model.bonds[closing])
                is not None
            )
            raise RuntimeError("injected")
    assert not getattr(failure.value, "__notes__", [])
    assert context.state.graph_state.graph_version == version
    chord = mutation.add_bond(ids[1], ids[4], 2)
    canvas.bond_renderer.add_bond_graphics(chord)
    center = context.geometry.ring_center_for_bond(canvas.model.bonds[chord])
    assert center is not None
    assert center.x() == pytest.approx(
        sum(canvas.model.atoms[i].x for i in ids[1:5]) / 4
    )
    assert center.y() == pytest.approx(
        sum(canvas.model.atoms[i].y for i in ids[1:5]) / 4
    )


def test_acyclic_growth_and_style_changes_do_not_refresh_remote_ring_bonds(
    canvas, monkeypatch
):
    from unittest.mock import Mock

    from chemvas.ui import canvas_bond_mutation_service as module

    ids, edges = _ring(canvas)
    mutation = canvas_services_for(canvas).structure.canvas_bond_mutation_service
    atoms = canvas_services_for(canvas).structure.canvas_atom_mutation_service
    scans = Mock(wraps=module.bonds_for)
    monkeypatch.setattr(module, "bonds_for", scans)
    previous = ids[0]
    for index in range(30):
        atom = atoms.add_atom("C", 80 + index * 20, 0)
        edge = mutation.add_bond(previous, atom)
        canvas.bond_renderer.add_bond_graphics(edge)
        mutation.restore_bond_from_state(
            edge, {"a": previous, "b": atom, "order": 1, "color": "#123456"}
        )
        previous = atom
    assert scans.call_count == 0
    # Retarget a cyclic edge at unchanged cycle rank: a different ring must
    # still refresh remote double-bond geometry.
    mutation.restore_bond_from_state(edges[-1], {"a": ids[-1], "b": ids[1], "order": 1})
    assert scans.call_count == 1
