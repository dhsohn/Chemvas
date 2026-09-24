"""The selection frame, its rotation knob, and the outline that replaced the fill."""

import math

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas.pick_radius_access import atom_pick_radius_for
from chemvas.ui.molecule.atom_label_access import add_or_update_atom_label
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.selection.selection_handles import (
    HANDLE_SCREEN_PX,
    ROTATION_HANDLE_STEM_PX,
    ROTATION_HANDLE_TYPE,
)
from chemvas.ui.window.main_window_ports import (
    history_service_for_window,
    select_all_for_window,
    set_zoom_percent_for_window,
)
from tests.gui_workflow_support import _key, _redo
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


def _ctrl(canvas, key):
    _key(canvas, key, Qt.KeyboardModifier.ControlModifier)


def _bonded_pair(canvas):
    a = canvas.services.canvas_atom_mutation_service.add_atom("C", -20.0, 0.0)
    b = canvas.services.canvas_atom_mutation_service.add_atom("C", 20.0, 0.0)
    bond_id = add_bond_for(canvas, a, b)
    canvas.bond_renderer.add_bond_graphics(bond_id)
    return a, b


def _select_all(window, canvas) -> None:
    # Select everything and settle the outline before reading it: under a
    # loaded CI runner the selection signal can land after the assertion.
    select_all_for_window(window)
    QApplication.processEvents()
    canvas.services.selection.update_selection_outline()
    QApplication.processEvents()


def _positions(canvas, *atom_ids):
    return [
        (canvas.model.atom_for_id(i).x, canvas.model.atom_for_id(i).y) for i in atom_ids
    ]


def _outlines(canvas, kind):
    return [
        item
        for item in canvas.runtime_state.selection_state.outlines
        if (item.data(2) or {}).get("kind") == kind
    ]


def _knob(canvas):
    knobs = [
        item
        for item in canvas.runtime_state.selection_state.outlines
        if item.data(1) == ROTATION_HANDLE_TYPE
    ]
    assert len(knobs) == 1
    return knobs[0]


def _knob_screen_pos(canvas, knob) -> QPoint:
    # The knob hangs a stem plus its own radius above the frame's top-centre,
    # in screen pixels, whatever the zoom.
    anchor = canvas.mapFromScene(knob.pos())
    return anchor - QPoint(0, round(ROTATION_HANDLE_STEM_PX + HANDLE_SCREEN_PX / 2))


def _swept(canvas, start: QPoint, center_scene: QPointF, degrees: float) -> QPoint:
    center = canvas.mapFromScene(center_scene)
    dx, dy = start.x() - center.x(), start.y() - center.y()
    radians = math.radians(degrees)
    return QPoint(
        round(center.x() + dx * math.cos(radians) - dy * math.sin(radians)),
        round(center.y() + dx * math.sin(radians) + dy * math.cos(radians)),
    )


ORIGIN = QPointF(0.0, 0.0)


def _drag_knob(canvas, degrees, *, center=ORIGIN, cancel=False, after_move=None):
    start = _knob_screen_pos(canvas, _knob(canvas))
    end = _swept(canvas, start, center, degrees)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, 30)
    if after_move is not None:
        after_move()
    if cancel:
        _key(canvas, Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    QApplication.processEvents()


def _assert_rotated(canvas, atom_ids, before, degrees, *, center=ORIGIN):
    radians = math.radians(degrees)
    for atom_id, (x, y) in zip(atom_ids, before, strict=True):
        dx, dy = x - center.x(), y - center.y()
        expected = (
            center.x() + dx * math.cos(radians) - dy * math.sin(radians),
            center.y() + dx * math.sin(radians) + dy * math.cos(radians),
        )
        atom = canvas.model.atom_for_id(atom_id)
        assert abs(atom.x - expected[0]) < 0.6, (atom_id, atom.x, expected)
        assert abs(atom.y - expected[1]) < 0.6, (atom_id, atom.y, expected)


def test_two_bonded_atoms_get_a_frame_and_a_rotation_knob(drawing):
    window, canvas = drawing
    _bonded_pair(canvas)
    _select_all(window, canvas)

    assert len(_outlines(canvas, "frame")) == 1
    knob = _knob(canvas)
    assert knob.data(0) == "handle"
    frame = _outlines(canvas, "frame")[0]
    assert knob.pos() == QPointF(
        frame.path().boundingRect().center().x(), frame.path().boundingRect().top()
    )


def test_a_lone_atom_gets_no_frame(drawing):
    window, canvas = drawing
    canvas.services.canvas_atom_mutation_service.add_atom("C", 0.0, 0.0)
    _select_all(window, canvas)

    assert _outlines(canvas, "frame") == []
    assert [
        item
        for item in canvas.runtime_state.selection_state.outlines
        if item.data(0) == "handle"
    ] == []


def test_a_single_arrow_gets_a_frame(drawing):
    window, canvas = drawing
    canvas.services.scene_decoration_service.add_arrow(
        QPointF(-30.0, 0.0), QPointF(30.0, 0.0), "arrow"
    )
    _select_all(window, canvas)

    assert len(_outlines(canvas, "frame")) == 1
    _knob(canvas)


def test_dragging_the_knob_rotates_the_selection_as_one_history_step(drawing):
    window, canvas = drawing
    set_zoom_percent_for_window(window, 200)
    a, b = _bonded_pair(canvas)
    _select_all(window, canvas)
    before = _positions(canvas, a, b)
    history = history_service_for_window(window)
    count = len(history.state.history)

    _drag_knob(canvas, 90.0)

    _assert_rotated(canvas, (a, b), before, 90.0)
    assert len(history.state.history) == count + 1
    # The frame followed the turn and still offers its knob.
    _knob(canvas)
    _ctrl(canvas, Qt.Key.Key_Z)
    assert _positions(canvas, a, b) == before
    _redo(canvas)
    _assert_rotated(canvas, (a, b), before, 90.0)


def test_escape_cancels_a_rotation_drag(drawing, tmp_path):
    window, canvas = drawing
    set_zoom_percent_for_window(window, 200)
    a, b = _bonded_pair(canvas)
    _select_all(window, canvas)
    document_action = window.services.document_action_service
    assert document_action.save_canvas_to_path(window, str(tmp_path / "turn.chemvas"))
    baseline = canvas.services.canvas_document_session_service.snapshot_state()
    history = history_service_for_window(window)
    count = len(history.state.history)

    before = _positions(canvas, a, b)

    def turned() -> None:
        # The drag really took hold before Escape undid it.
        _assert_rotated(canvas, (a, b), before, 60.0)

    _drag_knob(canvas, 60.0, cancel=True, after_move=turned)

    assert canvas.services.canvas_document_session_service.snapshot_state() == baseline
    assert len(history.state.history) == count
    assert not window.isWindowModified()


def test_a_click_on_the_knob_without_moving_changes_nothing(drawing, tmp_path):
    window, canvas = drawing
    a, b = _bonded_pair(canvas)
    _select_all(window, canvas)
    document_action = window.services.document_action_service
    assert document_action.save_canvas_to_path(window, str(tmp_path / "still.chemvas"))
    before = _positions(canvas, a, b)
    history = history_service_for_window(window)
    count = len(history.state.history)

    _drag_knob(canvas, 0.0)

    assert _positions(canvas, a, b) == before
    assert len(history.state.history) == count
    assert not window.isWindowModified()


def test_a_drag_back_to_its_start_restores_the_positions_exactly(drawing):
    window, canvas = drawing
    set_zoom_percent_for_window(window, 200)
    # Coordinates that floating-point rotation by zero does not reproduce.
    a = canvas.services.canvas_atom_mutation_service.add_atom("C", -20.1, 0.3)
    b = canvas.services.canvas_atom_mutation_service.add_atom("C", 19.7, 0.3)
    bond_id = add_bond_for(canvas, a, b)
    canvas.bond_renderer.add_bond_graphics(bond_id)
    _select_all(window, canvas)
    before = _positions(canvas, a, b)
    history = history_service_for_window(window)
    count = len(history.state.history)
    viewport = canvas.viewport()
    start = _knob_screen_pos(canvas, _knob(canvas))
    away = _swept(canvas, start, ORIGIN, 50.0)

    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, away, 30)
    assert _positions(canvas, a, b) != before
    QTest.mouseMove(viewport, start, 30)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=start)
    QApplication.processEvents()

    # Bit-for-bit, not merely close: a zero sweep is the identity.
    assert _positions(canvas, a, b) == before
    assert len(history.state.history) == count


def test_shift_snaps_the_sweep_to_fifteen_degree_steps(drawing):
    window, canvas = drawing
    set_zoom_percent_for_window(window, 200)
    a, b = _bonded_pair(canvas)
    _select_all(window, canvas)
    before = _positions(canvas, a, b)
    viewport = canvas.viewport()
    start = _knob_screen_pos(canvas, _knob(canvas))
    end = _swept(canvas, start, ORIGIN, 80.0)

    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(end),
        QPointF(viewport.mapToGlobal(end)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.sendEvent(viewport, move)
    QTest.mouseRelease(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, end
    )
    QApplication.processEvents()

    _assert_rotated(canvas, (a, b), before, 75.0)


@pytest.mark.parametrize("zoom", [50, 300])
def test_the_knob_is_picked_through_the_view_transform(drawing, zoom):
    window, canvas = drawing
    set_zoom_percent_for_window(window, zoom)
    _bonded_pair(canvas)
    _select_all(window, canvas)
    knob = _knob(canvas)
    hit_testing = canvas.services.hit_testing_service
    knob_screen = _knob_screen_pos(canvas, knob)

    # Three screen pixels off the knob's centre is inside its 8 px circle
    # (and beside its stem), whatever the zoom.
    for dx in (-3, 3):
        on_knob = canvas.mapToScene(knob_screen + QPoint(dx, 0))
        assert hit_testing.item_at_scene_pos(on_knob) is knob, (zoom, dx)
    # Eight screen pixels to the side is off an 8 px knob; it would still be
    # inside one drawn 8 units wide in the document (24 px at 300 %).
    beside = canvas.mapToScene(knob_screen + QPoint(8, 0))
    assert hit_testing.item_at_scene_pos(beside) is not knob


def test_bonded_carbons_share_one_band_without_atom_bubbles(drawing):
    window, canvas = drawing
    a, b = _bonded_pair(canvas)
    _select_all(window, canvas)

    (component,) = _outlines(canvas, "component")
    bounds = component.path().boundingRect()
    assert bounds.height() < atom_pick_radius_for(canvas) * 2.0
    assert component.brush().style() == Qt.BrushStyle.NoBrush
    assert component.pen().isCosmetic()


def test_a_labelled_atom_and_a_lone_atom_keep_their_own_marks(drawing):
    window, canvas = drawing
    carbon = canvas.services.canvas_atom_mutation_service.add_atom("C", -20.0, 0.0)
    oxygen = canvas.services.canvas_atom_mutation_service.add_atom("O", 20.0, 0.0)
    add_or_update_atom_label(canvas, oxygen, "O", record=False)
    bond_id = add_bond_for(canvas, carbon, oxygen)
    canvas.bond_renderer.add_bond_graphics(bond_id)
    canvas.services.canvas_atom_mutation_service.add_atom("C", 80.0, 0.0)
    _select_all(window, canvas)

    components = sorted(
        _outlines(canvas, "component"),
        key=lambda item: item.path().boundingRect().left(),
    )
    assert len(components) == 2
    labelled, lone = components
    radius = atom_pick_radius_for(canvas)
    # The label end of the band is boxed, so the band is as tall as the box.
    assert labelled.path().boundingRect().height() >= radius * 2.0 - 0.5
    # A lone atom is a ring of the pick radius.
    assert abs(lone.path().boundingRect().height() - radius * 2.0) < 0.5


def test_a_ring_double_bond_band_stays_on_the_atom_axis(drawing):
    window, canvas = drawing
    # A ring drawn atom by atom, as a loaded document is: the renderer puts
    # each double bond's second line inside the ring from the cycle alone,
    # with no ring item to name a centre.
    atom_ids = [
        canvas.services.canvas_atom_mutation_service.add_atom(
            "C", 30.0 * math.cos(k * math.pi / 3.0), 30.0 * math.sin(k * math.pi / 3.0)
        )
        for k in range(6)
    ]
    double_bond_ids = []
    for k in range(6):
        order = 2 if k % 2 == 0 else 1
        bond_id = add_bond_for(canvas, atom_ids[k], atom_ids[(k + 1) % 6], order)
        canvas.bond_renderer.add_bond_graphics(bond_id)
        if order == 2:
            double_bond_ids.append(bond_id)
    controller = canvas.services.selection

    for bond_id in double_bond_ids:
        bond = canvas.model.bonds[bond_id]
        lines = [
            item.line()
            for item in canvas.runtime_state.bond_graphics_state.bond_items.get(
                bond_id, []
            )
        ]
        assert len(lines) == 2
        lengths = sorted(line.length() for line in lines)
        # One line spans the atoms, the other is the shortened inner line.
        assert lengths[0] < lengths[1] - 1.0
        a, b = canvas.model.atom_for_id(bond.a), canvas.model.atom_for_id(bond.b)
        axis_mid = QPointF((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
        band_mid = (
            controller.outline_service.selection_path_for_bond(bond_id)
            .boundingRect()
            .center()
        )
        # The band follows the line on the atom axis, not the midpoint between
        # the outer and the shortened inner line, so it meets the single
        # bonds' bands at the ring vertices without a step.
        assert (band_mid - axis_mid).manhattanLength() < 0.3, bond_id


def test_showing_handles_leaves_the_item_pen_alone(drawing):
    window, canvas = drawing
    arrow = canvas.services.scene_decoration_service.add_arrow(
        QPointF(-30.0, 0.0), QPointF(30.0, 0.0), "arrow"
    )
    pen_before = arrow.pen()

    canvas.services.handle_overlay_service.show_endpoint_handles(arrow)

    assert arrow.pen().color().name() == pen_before.color().name()
    assert arrow.pen().widthF() == pen_before.widthF()
