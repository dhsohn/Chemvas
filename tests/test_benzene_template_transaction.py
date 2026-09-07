"""Benzene templates use one recorded-build rollback authority."""

from __future__ import annotations

from copy import deepcopy
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.features.insertion import TemplateInsertRequest, plan_template_commit
from chemvas.ui.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.insert_template_commit_service import apply_template_commit_resolution
from chemvas.ui.transactions.document import DocumentSavepoint
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


def _prepare(canvas, size, placement):
    builder = canvas.services.structure.structure_build_service
    for index in range(size):
        canvas.model.add_atom("C", index * 40.0, 0.0)
    for index in range(size - 1):
        canvas.model.add_bond(index, index + 1, 1)
    builder.render_model()
    if placement == "occupied":
        builder.add_benzene_ring(QPointF(120.0, 120.0))
    elif placement == "triple":
        canvas.model.bonds[0].order = 3
        builder.render_model()
    builder.sprout_regular_ring_from_atom(size - 1, 3)
    builder.sprout_regular_ring_from_atom(size - 1, 4)
    canvas.services.history_service.undo()
    set_last_smiles_input_for(canvas, "live input")
    return TemplateInsertRequest(
        6,
        (120.0, 120.0),
        ring_style="benzene",
        atom_id=0 if placement == "atom" else None,
        bond_id=0 if placement in {"fuse", "triple"} else None,
    )


def _apply(canvas, request, predecessor, after_input=None):
    return apply_template_commit_resolution(
        canvas,
        request,
        plan_template_commit(request),
        None,
        before_smiles_input=predecessor,
        after_smiles_input=after_input,
    )


@pytest.mark.parametrize("size", [2, 100])
@pytest.mark.parametrize("placement", ["free", "atom", "fuse"])
@pytest.mark.parametrize("predecessor", [None, "logical predecessor"])
@pytest.mark.parametrize("after_input", [None, "after input"])
def test_benzene_template_captures_once_and_round_trips(
    canvas, size, placement, predecessor, after_input
):
    request = _prepare(canvas, size, placement)
    before = _document(canvas)
    history = canvas.services.history_service
    undo = history.state.history
    redo = history.state.redo_stack
    old_undo_count = len(undo)
    callback = mock.Mock()
    history.state.change_callback = callback

    with mock.patch.object(
        DocumentSavepoint, "capture", wraps=DocumentSavepoint.capture
    ) as capture:
        assert _apply(canvas, request, predecessor, after_input)

    assert capture.call_count == 1
    assert history.state.history is undo
    assert history.state.redo_stack is redo
    assert len(undo) == old_undo_count + 1
    assert redo == []
    callback.assert_called_once()
    after = _document(canvas)
    assert after["last_smiles_input"] is None
    history.undo()
    expected_before = deepcopy(before)
    expected_before["last_smiles_input"] = (
        predecessor if predecessor is not None else after_input
    )
    assert _document(canvas) == expected_before
    history.redo()
    assert _document(canvas) == after


@pytest.mark.parametrize("placement", ["occupied", "triple"])
@pytest.mark.parametrize("predecessor", [None, "logical predecessor"])
def test_benzene_template_noop_restores_once_without_recording(
    canvas, placement, predecessor
):
    request = _prepare(canvas, 2, placement)
    expected = _document(canvas)
    expected["last_smiles_input"] = predecessor
    history = canvas.services.history_service
    undo = history.state.history
    redo = history.state.redo_stack
    undo_before = tuple(undo)
    redo_before = tuple(redo)
    items = tuple(canvas.scene().items())
    restore = DocumentSavepoint.restore
    with (
        mock.patch.object(
            DocumentSavepoint, "capture", wraps=DocumentSavepoint.capture
        ) as capture,
        mock.patch.object(
            DocumentSavepoint, "restore", autospec=True, side_effect=restore
        ) as restored,
    ):
        assert not _apply(canvas, request, predecessor)

    assert capture.call_count == 1
    assert restored.call_count == 1
    assert _document(canvas) == expected
    assert tuple(canvas.scene().items()) == items
    assert history.state.history is undo
    assert history.state.redo_stack is redo
    assert tuple(undo) == undo_before
    assert tuple(redo) == redo_before


@pytest.mark.parametrize("phase", ["mutation", "recording", "push"])
@pytest.mark.parametrize("predecessor", [None, "logical predecessor"])
def test_benzene_template_failure_has_one_restore_and_preserves_primary(
    canvas, phase, predecessor
):
    request = _prepare(canvas, 2, "free")
    expected = _document(canvas)
    expected["last_smiles_input"] = predecessor
    model = canvas.model
    items = tuple(canvas.scene().items())
    history = canvas.services.history_service
    undo = history.state.history
    redo = history.state.redo_stack
    undo_before = tuple(undo)
    redo_before = tuple(redo)
    callback = mock.Mock()
    history.state.change_callback = callback
    primary = RuntimeError("benzene " + phase + " failed")
    if phase == "mutation":
        target = canvas.services.structure.structure_build_service.committer
        method = "add_bond_graphics_range"
    elif phase == "recording":
        target = canvas.services.document.canvas_history_recording_service
        method = "record_additions"
    else:
        target = history
        method = "push"
    restore = DocumentSavepoint.restore
    capture_atom_counts = []
    original_capture = DocumentSavepoint.capture

    def capture_document(target_canvas, **kwargs):
        capture_atom_counts.append(len(target_canvas.model.atoms))
        return original_capture(target_canvas, **kwargs)

    before_atom_count = len(model.atoms)
    with (
        mock.patch.object(target, method, side_effect=primary),
        mock.patch.object(DocumentSavepoint, "capture", side_effect=capture_document),
        mock.patch.object(
            DocumentSavepoint, "restore", autospec=True, side_effect=restore
        ) as restored,
        pytest.raises(RuntimeError) as raised,
    ):
        _apply(canvas, request, predecessor)

    assert raised.value is primary
    # A failed history push retains the recorder's inverse-command savepoint,
    # captured after building; it is not a second pre-build transaction.
    assert capture_atom_counts == (
        [before_atom_count, before_atom_count + 6]
        if phase == "push"
        else [before_atom_count]
    )
    assert restored.call_count == 1
    assert canvas.model is model
    assert _document(canvas) == expected
    assert tuple(canvas.scene().items()) == items
    assert history.state.history is undo
    assert history.state.redo_stack is redo
    assert tuple(undo) == undo_before
    assert tuple(redo) == redo_before
    callback.assert_called_once()
