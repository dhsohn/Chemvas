"""Bond edits retain a complete document when graphics reconstruction fails."""

import pytest
from PyQt6.QtCore import QEvent, QPointF

from chemvas.ui.canvas.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.selection.selection_queries import selected_ids_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    view.services.structure_build_service.add_bond_between_points(
        QPointF(0, 0), QPointF(40, 0), style="wedge", order=1
    )
    yield view
    schedule_canvas_deletion_for(view)
    qt_application.sendPostedEvents(view, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("operation", ["apply", "cycle", "flip"])
def test_failed_bond_edit_restores_document_graphics_selection_and_history(
    canvas, monkeypatch, operation
):
    controller = canvas.services.scene_transform_controller
    history = canvas.services.history_service
    session = canvas.services.canvas_document_session_service
    items = list(canvas.runtime_state.bond_graphics_state.bond_items[0])
    for item in items:
        item.setSelected(True)
    before = session.snapshot_state()
    selection = selected_ids_for(canvas)
    stacks = history.capture_stack_snapshot()
    original = canvas.bond_renderer.add_bond_graphics
    failed = False

    def fail_once(bond_id):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("bond graphics reconstruction failed")
        return original(bond_id)

    def edit():
        if operation == "apply":
            controller.apply_bond_style(0, "double", 2)
        elif operation == "cycle":
            controller.cycle_bond_style(0)
        else:
            controller.flip_bond_direction(0)

    with monkeypatch.context() as patch:
        patch.setattr(canvas.bond_renderer, "add_bond_graphics", fail_once)
        with pytest.raises(RuntimeError, match="reconstruction failed"):
            edit()

    assert failed
    assert session.snapshot_state() == before
    assert selected_ids_for(canvas) == selection
    assert canvas.runtime_state.bond_graphics_state.bond_items[0] == items
    assert all(item.scene() is canvas.scene() for item in items)
    history.verify_stack_snapshot(stacks)
    edit()
    after = session.snapshot_state()
    assert after != before
    history.undo()
    assert session.snapshot_state() == before
    history.redo()
    assert session.snapshot_state() == after


@pytest.mark.parametrize("style,order", [("double", 2), ("bold_in", 1)])
def test_neighbor_bond_geometry_round_trips_after_delete(
    canvas, qt_application, style, order
):
    canvas.services.canvas_scene_reset_service.clear_scene()
    builder = canvas.services.structure_build_service
    builder.add_bond_between_points(
        QPointF(0, 0), QPointF(40, 0), style=style, order=order
    )
    builder.add_bond_between_points(
        QPointF(0, 0), QPointF(0, -40), style="bold_in", order=1
    )

    def geometry():
        return [
            item.shape()
            for item in canvas.runtime_state.bond_graphics_state.bond_items[0]
        ]

    reopened = build_canvas_view()

    def assert_matches_reopened():
        reopened.services.canvas_document_session_service.apply_state(
            canvas.services.canvas_document_session_service.snapshot_state()
        )
        assert geometry() == [
            item.shape()
            for item in reopened.runtime_state.bond_graphics_state.bond_items[0]
        ]

    try:
        before = geometry()
        assert_matches_reopened()
        canvas.services.scene_delete_controller.delete_bond(1)
        deleted = geometry()
        assert deleted != before
        assert_matches_reopened()
        history = canvas.services.history_service
        for _ in range(2):
            history.undo()
            assert geometry() == before
            assert_matches_reopened()
            history.redo()
            assert geometry() == deleted
            assert_matches_reopened()
    finally:
        schedule_canvas_deletion_for(reopened)
        qt_application.sendPostedEvents(reopened, QEvent.Type.DeferredDelete)
