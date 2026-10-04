"""Orbital handles follow bond-length edits, Undo and Redo on a real canvas.

The orbital's scale and rotate handles sit 0.8 bond lengths right of and
above its centre. A p orbital centred at (500, 400) therefore has handles at
x=516 / y=384 for a 20 px bond and at x=548 / y=352 for a 60 px bond.
"""

import pytest
from PyQt6.QtCore import QPointF, QRectF

ORBITAL_HANDLE_TYPES = ("orbital_scale", "orbital_rotate")
HANDLES_AT_20 = [("orbital_scale", 516.0, 400.0), ("orbital_rotate", 500.0, 384.0)]
HANDLES_AT_60 = [("orbital_scale", 548.0, 400.0), ("orbital_rotate", 500.0, 352.0)]


@pytest.fixture
def canvas(qt_application):
    from tests.canvas_factory import build_canvas_view

    canvas = build_canvas_view()
    yield canvas
    canvas.services.canvas_scene_reset_service.clear_scene()
    canvas.close()


def _add_p_orbital(canvas):
    canvas.runtime_state.tool_settings_state.active_orbital_type = "p"
    return canvas.services.scene_decoration_service.add_orbital(QPointF(500, 400))


def _active_handle_points(canvas):
    return [
        (handle.data(1), handle.pos().x(), handle.pos().y())
        for handle in canvas.runtime_state.handle_state.active_handles
    ]


def _scene_orbital_handles(canvas):
    return [
        item
        for item in canvas.scene().items()
        if item.data(0) == "handle" and item.data(1) in ORBITAL_HANDLE_TYPES
    ]


def _outline_bounds(canvas):
    return [
        value
        for outline in canvas.runtime_state.selection_state.outlines
        for value in outline.sceneBoundingRect().getRect()
    ]


def _only_orbital(canvas):
    (item,) = canvas.runtime_state.orbital_items()
    return item


def _assert_orbital_handles(canvas, item, expected):
    handles = canvas.runtime_state.handle_state.active_handles
    assert canvas.runtime_state.handle_state.target is item
    assert _active_handle_points(canvas) == [
        (kind, pytest.approx(x, abs=1e-9), pytest.approx(y, abs=1e-9))
        for kind, x, y in expected
    ]
    assert all(handle.data(2) is item for handle in handles)
    # Exactly the active pair is visible; no stale pair is left in the scene.
    assert sorted(map(id, _scene_orbital_handles(canvas))) == sorted(map(id, handles))
    assert all(handle.isVisible() for handle in handles)


def test_selected_orbital_handles_follow_bond_length_undo_and_redo(canvas):
    history = canvas.services.history_service
    item = _add_p_orbital(canvas)
    record_id = item.record_id
    state = item.orbital_state()
    item.setSelected(True)
    lobes_at_20 = item.sceneBoundingRect().getRect()
    outlines_at_20 = _outline_bounds(canvas)
    assert outlines_at_20
    item.setSelected(False)

    canvas.services.geometry_controller.set_bond_length(60)
    item.setSelected(True)
    # Clicking the selected orbital shows its handles through this owner.
    canvas.services.handle_overlay_service.show_orbital_handles(item)
    lobes_at_60 = item.sceneBoundingRect().getRect()
    outlines_at_60 = _outline_bounds(canvas)
    assert lobes_at_60 != pytest.approx(lobes_at_20)
    assert outlines_at_60 != pytest.approx(outlines_at_20)
    _assert_orbital_handles(canvas, item, HANDLES_AT_60)
    shown_at_60 = list(canvas.runtime_state.handle_state.active_handles)

    history.undo()
    assert canvas.renderer.style.bond_length_px == 20
    assert _only_orbital(canvas) is item
    assert item.record_id == record_id and item.orbital_state() == state
    assert item.isSelected()
    assert item.sceneBoundingRect().getRect() == pytest.approx(lobes_at_20, abs=1e-10)
    assert _outline_bounds(canvas) == pytest.approx(outlines_at_20, abs=1e-10)
    _assert_orbital_handles(canvas, item, HANDLES_AT_20)
    assert all(handle.scene() is None for handle in shown_at_60)

    history.redo()
    assert canvas.renderer.style.bond_length_px == 60
    assert _only_orbital(canvas) is item
    assert item.record_id == record_id and item.orbital_state() == state
    assert item.isSelected()
    assert item.sceneBoundingRect().getRect() == pytest.approx(lobes_at_60, abs=1e-10)
    assert _outline_bounds(canvas) == pytest.approx(outlines_at_60, abs=1e-10)
    _assert_orbital_handles(canvas, item, HANDLES_AT_60)

    documents = canvas.services.canvas_document_session_service
    documents.apply_state(documents.snapshot_state())
    assert canvas.runtime_state.handle_state.active_handles == []
    assert canvas.runtime_state.handle_state.target is None
    assert _scene_orbital_handles(canvas) == []
    reopened = _only_orbital(canvas)
    assert reopened.orbital_state() == state
    reopened.setSelected(True)
    canvas.services.handle_overlay_service.show_orbital_handles(reopened)
    _assert_orbital_handles(canvas, reopened, HANDLES_AT_60)


def test_bond_length_edit_moves_handles_of_selected_orbital(canvas):
    item = _add_p_orbital(canvas)
    item.setSelected(True)
    canvas.services.handle_overlay_service.show_orbital_handles(item)
    _assert_orbital_handles(canvas, item, HANDLES_AT_20)

    canvas.services.geometry_controller.set_bond_length(60)
    _assert_orbital_handles(canvas, item, HANDLES_AT_60)

    canvas.services.history_service.undo()
    _assert_orbital_handles(canvas, item, HANDLES_AT_20)


def test_unselected_orbital_handles_still_clear_on_bond_length_history(canvas):
    history = canvas.services.history_service
    item = _add_p_orbital(canvas)
    overlay = canvas.services.handle_overlay_service
    overlay.show_orbital_handles(item)

    canvas.services.geometry_controller.set_bond_length(60)
    assert canvas.runtime_state.handle_state.active_handles == []
    assert canvas.runtime_state.handle_state.target is None

    overlay.show_orbital_handles(item)
    history.undo()
    assert canvas.runtime_state.handle_state.active_handles == []
    assert canvas.runtime_state.handle_state.target is None
    history.redo()
    assert canvas.runtime_state.handle_state.active_handles == []
    assert canvas.runtime_state.handle_state.target is None
    assert _scene_orbital_handles(canvas) == []


def test_hidden_orbital_handles_stay_hidden_through_bond_length_history(canvas):
    history = canvas.services.history_service
    item = _add_p_orbital(canvas)
    item.setSelected(True)
    overlay = canvas.services.handle_overlay_service
    overlay.show_orbital_handles(item)
    # A second click on the selected orbital hides its handles.
    overlay.clear_handles()

    canvas.services.geometry_controller.set_bond_length(60)
    history.undo()
    history.redo()
    history.undo()

    assert item.isSelected()
    assert canvas.runtime_state.handle_state.active_handles == []
    assert canvas.runtime_state.handle_state.target is None
    assert _scene_orbital_handles(canvas) == []


@pytest.mark.parametrize("kind", ["shape", "arrow"])
def test_bond_length_history_leaves_other_handles_untouched(canvas, kind):
    history = canvas.services.history_service
    decorations = canvas.services.scene_decoration_service
    overlay = canvas.services.handle_overlay_service
    _add_p_orbital(canvas)
    if kind == "shape":
        target = decorations.add_shape(QRectF(100.0, 100.0, 80.0, 40.0))
        target.setSelected(True)
        overlay.show_shape_handles(target)
    else:
        target = decorations.add_arrow(QPointF(100, 100), QPointF(180, 100), "arrow")
        target.setSelected(True)
        overlay.show_endpoint_handles(target)
    handles = list(canvas.runtime_state.handle_state.active_handles)
    points = _active_handle_points(canvas)
    assert handles

    canvas.services.geometry_controller.set_bond_length(60)
    history.undo()
    history.redo()

    assert canvas.runtime_state.handle_state.target is target
    assert canvas.runtime_state.handle_state.active_handles == handles
    assert _active_handle_points(canvas) == points
    assert all(handle.scene() is canvas.scene() for handle in handles)
    assert _scene_orbital_handles(canvas) == []
