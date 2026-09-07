"""Real-canvas contracts for the single pre-build rollback authority."""

from __future__ import annotations

from unittest import mock

import pytest
from PyQt6.QtWidgets import QApplication

from chemvas.ui import structure_build_committer as committer_module
from chemvas.ui.canvas_smiles_input_state import (
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()


def _document(canvas):
    return canvas.services.document.canvas_document_session_service.snapshot_state()


def _draw_chain(canvas, size):
    for index in range(size):
        canvas.model.add_atom("C", index * 40.0, 0.0)
    for index in range(size - 1):
        canvas.model.add_bond(index, index + 1, 1)
    canvas.services.structure.structure_build_service.render_model()


@pytest.mark.parametrize("size", [2, 100])
def test_recorded_ring_uses_one_prebuild_capture_and_round_trips(canvas, size):
    _draw_chain(canvas, size)
    before = _document(canvas)
    history = canvas.services.history_service
    service = canvas.services.structure.structure_build_service
    captured_atom_counts = []
    capture = committer_module.capture_history_transaction_for_history

    def capture_before_mutation(*args, **kwargs):
        captured_atom_counts.append(len(canvas.model.atoms))
        return capture(*args, **kwargs)

    with mock.patch.object(
        committer_module,
        "capture_history_transaction_for_history",
        side_effect=capture_before_mutation,
    ):
        service.sprout_regular_ring_from_atom(0, 6)

    assert captured_atom_counts == [size]
    assert len(canvas.model.atoms) == size + 5
    assert len(history.state.history) == 1
    after = _document(canvas)
    history.undo()
    assert _document(canvas) == before
    history.redo()
    assert _document(canvas) == after


@pytest.mark.parametrize("failure_phase", ["mutation", "recording", "push"])
def test_failed_build_restores_original_document_items_and_stacks(
    canvas, failure_phase
):
    _draw_chain(canvas, 2)
    service = canvas.services.structure.structure_build_service
    history = canvas.services.history_service
    service.sprout_regular_ring_from_atom(0, 5)
    service.sprout_regular_ring_from_atom(1, 6)
    history.undo()
    set_last_smiles_input_for(canvas, "previous input")
    before = _document(canvas)
    model = canvas.model
    scene_items = tuple(canvas.scene().items())
    history_list = history.state.history
    redo_list = history.state.redo_stack
    history_before = tuple(history_list)
    redo_before = tuple(redo_list)
    failure = RuntimeError(f"build {failure_phase} failure")

    def build():
        first = service.committer.add_atom("N", 160.0, 80.0)
        second = service.committer.add_atom("O", 200.0, 80.0)
        service.committer.add_bond(first, second)
        if failure_phase == "mutation":
            raise failure
        return []

    if failure_phase == "recording":
        target = canvas.services.document.canvas_history_recording_service
        method = "record_additions"
    else:
        target = history
        method = "push"
    with mock.patch.object(target, method, side_effect=failure) as failing_call:
        with pytest.raises(RuntimeError) as raised:
            service.run_recorded_build(build)

    assert raised.value is failure
    assert failing_call.call_count == (0 if failure_phase == "mutation" else 1)
    assert canvas.model is model
    assert _document(canvas) == before
    assert tuple(canvas.scene().items()) == scene_items
    assert history.state.history is history_list
    assert history.state.redo_stack is redo_list
    assert tuple(history_list) == history_before
    assert tuple(redo_list) == redo_before
    assert last_smiles_input_for(canvas) == "previous input"


def test_recorded_build_preserves_explicit_smiles_predecessor_on_undo(canvas):
    _draw_chain(canvas, 2)
    set_last_smiles_input_for(canvas, "live input")
    service = canvas.services.structure.structure_build_service

    def build():
        service.committer.add_atom("N", 80.0, 80.0)
        return []

    service.run_recorded_build(build, before_smiles_input="logical predecessor")
    assert last_smiles_input_for(canvas) is None
    canvas.services.history_service.undo()
    assert last_smiles_input_for(canvas) == "logical predecessor"
    canvas.services.history_service.redo()
    assert last_smiles_input_for(canvas) is None
