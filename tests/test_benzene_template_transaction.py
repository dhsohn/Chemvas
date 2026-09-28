"""Benzene templates use one recorded-build rollback authority."""

from __future__ import annotations

from copy import deepcopy
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.features.insertion import (
    TemplateInsertRequest,
    plan_template_commit,
    plan_template_preview,
)
from chemvas.ui.insert.insert_template_commit_service import (
    apply_template_commit_resolution,
)
from chemvas.ui.insert.template_geometry_resolver_service import (
    TemplateGeometryResolverService,
)
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
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()


def _document(canvas):
    return canvas.services.canvas_document_session_service.snapshot_state()


def _prepare(canvas, size, placement):
    builder = canvas.services.structure_build_service
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
    return TemplateInsertRequest(
        6,
        (120.0, 120.0),
        ring_style="benzene",
        atom_id=0 if placement == "atom" else None,
        bond_id=0 if placement in {"fuse", "triple"} else None,
    )


def _apply(canvas, request=None):
    return apply_template_commit_resolution(
        canvas,
        request,
        plan_template_commit(request),
        None,
    )


@pytest.mark.parametrize("placement", ["free", "atom", "fuse", "double_fuse"])
def test_benzene_preview_matches_committed_positions_and_bond_orders(canvas, placement):
    request = _prepare(canvas, 2, "fuse" if placement == "double_fuse" else placement)
    if placement == "double_fuse":
        canvas.model.bonds[0].order = 2
        canvas.services.structure_build_service.render_model()
    before = _document(canvas)
    resolution = TemplateGeometryResolverService(canvas).resolve_insert(
        request, plan_template_preview(request)
    )
    assert resolution is not None and resolution.points is not None
    assert resolution.bond_orders is not None
    assert _document(canvas) == before  # Hover never allocates atoms or edits history.
    controller = canvas.services.insert_controller
    with mock.patch.object(controller, "template_insert_request", return_value=request):
        controller.render_template_preview(QPointF(*request.cursor_pos))
    lines = canvas.runtime_state.insert_state.template_preview_lines
    assert len(lines) == 6 + resolution.bond_orders.count(2)
    for index, (x, y) in enumerate(resolution.points):
        assert lines[index].line().p1() == QPointF(x, y)
    center_x = sum(x for x, _ in resolution.points) / 6
    center_y = sum(y for _, y in resolution.points) / 6
    double_points = [
        QPointF(x + (center_x - x) * 0.22, y + (center_y - y) * 0.22)
        for (x, y), order in zip(resolution.points, resolution.bond_orders, strict=True)
        if order == 2
    ]
    assert [line.line().p1() for line in lines[6:]] == double_points
    controller.clear_template_preview()
    assert _apply(canvas, request)
    ids = []
    for x, y in resolution.points:
        matches = [
            atom_id
            for atom_id, atom in canvas.model.atoms.items()
            if abs(atom.x - x) < 1e-6 and abs(atom.y - y) < 1e-6
        ]
        assert len(matches) == 1
        ids.append(matches[0])
    for index, expected_order in enumerate(resolution.bond_orders):
        pair = {ids[index], ids[(index + 1) % len(ids)]}
        bonds = [b for b in canvas.model.bonds if b is not None and {b.a, b.b} == pair]
        assert len(bonds) == 1
        assert bonds[0].order == expected_order
    canvas.services.history_service.undo()
    assert _document(canvas) == before


@pytest.mark.parametrize("placement", ["occupied", "triple"])
def test_rejected_benzene_placement_has_no_preview_or_mutation(canvas, placement):
    request = _prepare(canvas, 2, placement)
    before = _document(canvas)
    assert (
        TemplateGeometryResolverService(canvas).resolve_insert(
            request, plan_template_preview(request)
        )
        is None
    )
    assert not _apply(canvas, request)
    assert _document(canvas) == before


@pytest.mark.parametrize("size", [2, 100])
@pytest.mark.parametrize("placement", ["free", "atom", "fuse"])
def test_benzene_template_captures_once_and_round_trips(canvas, size, placement):
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
        assert _apply(canvas, request)

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
    assert _document(canvas) == expected_before
    history.redo()
    assert _document(canvas) == after


@pytest.mark.parametrize("placement", ["occupied", "triple"])
def test_benzene_template_noop_restores_once_without_recording(canvas, placement):
    request = _prepare(canvas, 2, placement)
    expected = _document(canvas)
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
        assert not _apply(canvas, request)

    assert capture.call_count == 1
    assert restored.call_count == 1
    assert _document(canvas) == expected
    assert tuple(canvas.scene().items()) == items
    assert history.state.history is undo
    assert history.state.redo_stack is redo
    assert tuple(undo) == undo_before
    assert tuple(redo) == redo_before


@pytest.mark.parametrize("phase", ["mutation", "recording", "push"])
def test_benzene_template_failure_has_one_restore_and_preserves_primary(canvas, phase):
    request = _prepare(canvas, 2, "free")
    expected = _document(canvas)
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
        target = canvas.services.structure_build_service.committer
        method = "add_bond_graphics_range"
    elif phase == "recording":
        target = canvas.services.canvas_history_recording_service
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
        _apply(canvas, request)

    assert raised.value is primary
    # A failed history push is restored by the pre-build transaction alone;
    # recording does not capture again to invert the built ring first.
    assert capture_atom_counts == [before_atom_count]
    assert restored.call_count == 1
    assert canvas.model is model
    assert _document(canvas) == expected
    assert tuple(canvas.scene().items()) == items
    assert history.state.history is undo
    assert history.state.redo_stack is redo
    assert tuple(undo) == undo_before
    assert tuple(redo) == redo_before
    callback.assert_called_once()
