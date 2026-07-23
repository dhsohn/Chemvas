"""Behavior characterization for the transaction/history protected contracts.

These tests pin user-observable behavior — document round-trips through real
undo/redo, document integrity after mid-operation failures, and scene-rect
mode preservation — using real Qt objects and the serialized document state
as the only observable. They must keep passing unchanged while the internal
defensive machinery is simplified.
"""

from __future__ import annotations

import copy
import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from chemvas.ui.atom_label_access import add_or_update_atom_label
from chemvas.ui.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas_model_access import bond_count_for, next_atom_id_for
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.history_recording_access import record_additions_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    scene_rect_is_automatic,
)
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsScene


@pytest.fixture(scope="module")
def app() -> QApplication:
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app: QApplication):
    view = CanvasView()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()


def _document_state(canvas) -> dict:
    return canvas.services.document.canvas_document_session_service.snapshot_state()


def _history(canvas) -> CanvasHistoryService:
    return canvas.services.history_service


def _record_molecule(canvas, *, offset: float = 0.0) -> tuple[int, int]:
    """Draw a two-atom molecule with one bond and record one undo entry."""

    before_next_atom_id = next_atom_id_for(canvas)
    before_bond_count = bond_count_for(canvas)
    first = add_atom_for(canvas, "C", 0.0 + offset, 0.0)
    second = add_atom_for(canvas, "O", 40.0 + offset, 0.0)
    add_bond_for(canvas, first, second, 1)
    record_additions_for(canvas, before_next_atom_id, before_bond_count, None)
    canvas.services.structure.structure_build_service.render_model()
    return first, second


def _selected_rotation_controller(canvas):
    assert select_all_scene_items_for(canvas)
    return canvas.services.interaction.selection_rotation_controller


def _primed_rotation_controller(canvas):
    """Return the rotation controller after 3D-state initialization.

    Beginning a rotation initializes the persisted ``perspective`` block as a
    side effect (current behavior, even for a no-movement gesture). Priming
    once lets the round-trip tests compare full document snapshots exactly.
    """

    controller = _selected_rotation_controller(canvas)
    assert controller.begin_selection_3d_rotation() is True
    controller.end_selection_3d_rotation()
    return controller


def test_recorded_addition_round_trips_through_undo_and_redo(canvas) -> None:
    baseline = _document_state(canvas)

    _record_molecule(canvas)
    drawn = _document_state(canvas)

    assert drawn != baseline
    assert len(_history(canvas).state.history) == 1

    _history(canvas).undo()
    assert _document_state(canvas) == baseline

    _history(canvas).redo()
    assert _document_state(canvas) == drawn


def test_atom_delete_round_trips_through_undo_and_redo(canvas) -> None:
    first, _second = _record_molecule(canvas)
    drawn = _document_state(canvas)

    command = canvas.services.scene_operations.scene_delete_controller.delete_atom(
        first
    )
    assert command is not None
    deleted = _document_state(canvas)
    assert deleted != drawn

    _history(canvas).undo()
    assert _document_state(canvas) == drawn

    _history(canvas).redo()
    assert _document_state(canvas) == deleted


def test_delete_selected_items_is_one_undo_step(canvas) -> None:
    _record_molecule(canvas)
    drawn = _document_state(canvas)
    history_length = len(_history(canvas).state.history)

    assert select_all_scene_items_for(canvas)
    assert (
        canvas.services.scene_operations.scene_delete_controller.delete_selected_items()
    )

    assert len(_history(canvas).state.history) == history_length + 1
    deleted = _document_state(canvas)

    _history(canvas).undo()
    assert _document_state(canvas) == drawn

    _history(canvas).redo()
    assert _document_state(canvas) == deleted


def test_atom_label_edit_round_trips_through_undo_and_redo(canvas) -> None:
    first, _second = _record_molecule(canvas)
    drawn = _document_state(canvas)

    add_or_update_atom_label(canvas, first, "OMe")
    labeled = _document_state(canvas)
    assert labeled != drawn

    _history(canvas).undo()
    assert _document_state(canvas) == drawn

    _history(canvas).redo()
    assert _document_state(canvas) == labeled


def test_rotation_gesture_pushes_one_command_and_round_trips(canvas) -> None:
    _record_molecule(canvas)
    controller = _primed_rotation_controller(canvas)
    drawn = _document_state(canvas)
    history_length = len(_history(canvas).state.history)

    assert controller.begin_selection_3d_rotation() is True
    controller.update_selection_3d_rotation(35.0, 20.0)
    controller.end_selection_3d_rotation()

    assert len(_history(canvas).state.history) == history_length + 1
    rotated = _document_state(canvas)
    assert rotated != drawn

    _history(canvas).undo()
    assert _document_state(canvas) == drawn

    _history(canvas).redo()
    assert _document_state(canvas) == rotated


def test_rotation_gesture_without_movement_pushes_nothing(canvas) -> None:
    _record_molecule(canvas)
    controller = _primed_rotation_controller(canvas)
    drawn = _document_state(canvas)
    history_length = len(_history(canvas).state.history)
    redo_length = len(_history(canvas).state.redo_stack)

    assert controller.begin_selection_3d_rotation() is True
    controller.end_selection_3d_rotation()

    assert _document_state(canvas) == drawn
    assert len(_history(canvas).state.history) == history_length
    assert len(_history(canvas).state.redo_stack) == redo_length


def test_failed_history_push_restores_document_and_propagates(canvas) -> None:
    first, _second = _record_molecule(canvas)
    drawn = _document_state(canvas)
    history_before = list(_history(canvas).state.history)

    with mock.patch.object(
        CanvasHistoryService,
        "push",
        side_effect=RuntimeError("simulated push failure"),
    ):
        with pytest.raises(RuntimeError, match="simulated push failure"):
            canvas.services.scene_operations.scene_delete_controller.delete_atom(first)

    assert _document_state(canvas) == drawn
    assert list(_history(canvas).state.history) == history_before


def test_failed_rotation_frame_reverts_to_previous_frame_and_propagates(canvas) -> None:
    """A failing frame reverts only itself and pushes nothing.

    Current behavior: the rolling checkpoint restores the document to the
    last successful frame (not the gesture start) and the error propagates
    without recording a history entry.
    """

    _record_molecule(canvas)
    controller = _primed_rotation_controller(canvas)
    drawn = _document_state(canvas)
    history_length = len(_history(canvas).state.history)

    assert controller.begin_selection_3d_rotation() is True
    controller.update_selection_3d_rotation(12.0, 6.0)
    after_first_frame = _document_state(canvas)

    original_apply = type(controller).apply_projected_atom_positions

    def failing_apply(self, atom_ids_arg, coords):
        raise RuntimeError("simulated projection failure")

    with mock.patch.object(
        type(controller),
        "apply_projected_atom_positions",
        failing_apply,
    ):
        with pytest.raises(RuntimeError, match="simulated projection failure"):
            controller.update_selection_3d_rotation(90.0, 45.0)

    assert type(controller).apply_projected_atom_positions is original_apply
    assert _document_state(canvas) == after_first_frame
    assert len(_history(canvas).state.history) == history_length
    assert drawn != after_first_frame


def test_failed_rotation_begin_leaves_document_unchanged(canvas) -> None:
    _record_molecule(canvas)
    controller = _primed_rotation_controller(canvas)
    drawn = _document_state(canvas)
    history_length = len(_history(canvas).state.history)

    assert select_all_scene_items_for(canvas)

    def failing_flatten(self, atom_ids_arg, coords):
        raise RuntimeError("simulated flatten failure")

    with mock.patch.object(
        type(controller),
        "flatten_planar_fragments",
        failing_flatten,
    ):
        with pytest.raises(RuntimeError, match="simulated flatten failure"):
            controller.begin_selection_3d_rotation()

    assert _document_state(canvas) == drawn
    assert len(_history(canvas).state.history) == history_length

    # The controller must be able to start a fresh gesture afterwards.
    assert select_all_scene_items_for(canvas)
    assert controller.begin_selection_3d_rotation() is True
    controller.end_selection_3d_rotation()


def test_failed_rotation_end_push_restores_pre_gesture_document(canvas) -> None:
    """A failed finalization fails closed (ADR 0002).

    No command is recorded, the history stacks stay untouched, the document
    reverts to the gesture start, and a fresh gesture can begin afterwards.
    """

    _record_molecule(canvas)
    controller = _primed_rotation_controller(canvas)
    drawn = _document_state(canvas)
    history_before = list(_history(canvas).state.history)

    with mock.patch.object(
        CanvasHistoryService,
        "push",
        side_effect=RuntimeError("simulated rotation push failure"),
    ):
        assert controller.begin_selection_3d_rotation() is True
        controller.update_selection_3d_rotation(25.0, 15.0)
        with pytest.raises(RuntimeError, match="simulated rotation push failure"):
            controller.end_selection_3d_rotation()

    assert _document_state(canvas) == drawn
    assert list(_history(canvas).state.history) == history_before

    assert select_all_scene_items_for(canvas)
    assert controller.begin_selection_3d_rotation() is True
    controller.end_selection_3d_rotation()


def test_failed_rotation_finalization_after_push_keeps_command_and_document(
    canvas,
) -> None:
    """After a successful push, a later finalization failure must not revert.

    The stack top describes the rotated document, so the document stays
    rotated, the command stays recorded, and undo still restores the
    pre-gesture document exactly.
    """

    _record_molecule(canvas)
    controller = _primed_rotation_controller(canvas)
    drawn = _document_state(canvas)
    history_length = len(_history(canvas).state.history)

    assert controller.begin_selection_3d_rotation() is True
    controller.update_selection_3d_rotation(25.0, 15.0)

    with mock.patch.object(
        type(controller),
        "restore_selection_from_ids",
        side_effect=RuntimeError("simulated selection restore failure"),
    ):
        with pytest.raises(RuntimeError, match="selection restore failure"):
            controller.end_selection_3d_rotation()

    rotated = _document_state(canvas)
    assert rotated != drawn
    assert len(_history(canvas).state.history) == history_length + 1

    _history(canvas).undo()
    assert _document_state(canvas) == drawn


def test_moved_drag_gesture_pushes_one_command_and_round_trips(canvas) -> None:
    from chemvas.ui.move_tool import MoveTool
    from PyQt6.QtCore import QPointF

    _record_molecule(canvas)
    drawn = _document_state(canvas)
    history_length = len(_history(canvas).state.history)

    assert select_all_scene_items_for(canvas)
    tool = MoveTool(canvas, context=canvas.services.tool_controller.context)
    from chemvas.ui.selection_collection_access import selection_snapshot_for

    snapshot = selection_snapshot_for(canvas)
    assert snapshot is not None
    assert tool._begin_selection_drag(
        set(snapshot.selected_atom_ids),
        list(snapshot.selection_items),
        QPointF(),
    )
    tool._apply_drag_delta(QPointF(15.0, -7.0))
    tool._commit_selection_drag()

    assert len(_history(canvas).state.history) == history_length + 1
    moved = _document_state(canvas)
    assert moved != drawn

    _history(canvas).undo()
    assert _document_state(canvas) == drawn

    _history(canvas).redo()
    assert _document_state(canvas) == moved


def test_failed_document_open_leaves_no_half_applied_document(canvas, app) -> None:
    _record_molecule(canvas)
    source_state = _document_state(canvas)

    target = CanvasView()
    try:
        blank = _document_state(target)
        corrupted = copy.deepcopy(source_state)
        corrupted["model"] = {"bogus": "payload"}

        session = target.services.document.canvas_document_session_service
        with pytest.raises(KeyError):
            session.apply_state(corrupted)

        after_failure = _document_state(target)
        assert after_failure["model"] == blank["model"]
        assert len(target.model.atoms) == 0
        # The canvas must remain fully usable after the failed open.
        add_atom_for(target, "N", 5.0, 5.0)
        assert len(target.model.atoms) == 1
    finally:
        target.services.document.canvas_scene_reset_service.clear_scene()
        target.close()


def test_successful_document_open_round_trips_between_canvases(canvas, app) -> None:
    _record_molecule(canvas)
    source_state = _document_state(canvas)

    target = CanvasView()
    try:
        session = target.services.document.canvas_document_session_service
        session.apply_state(copy.deepcopy(source_state))

        assert _document_state(target)["model"] == source_state["model"]
        assert len(target.services.history_service.state.history) == 0
    finally:
        target.services.document.canvas_scene_reset_service.clear_scene()
        target.close()


def test_scene_rect_guard_preserves_automatic_mode_after_restore(app) -> None:
    scene = QGraphicsScene()
    assert scene_rect_is_automatic(scene)

    snapshot = SceneRectSnapshot.capture(scene)
    scene.addItem(QGraphicsRectItem(0, 0, 500, 400))
    snapshot.restore()

    assert scene_rect_is_automatic(scene)


def test_scene_rect_guard_release_keeps_growth_and_automatic_mode(app) -> None:
    scene = QGraphicsScene()
    snapshot = SceneRectSnapshot.capture(scene)
    scene.addItem(QGraphicsRectItem(0, 0, 500, 400))
    snapshot.release()

    assert scene_rect_is_automatic(scene)
    assert scene.sceneRect().width() >= 500
