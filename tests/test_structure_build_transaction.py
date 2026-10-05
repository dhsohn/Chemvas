"""Real-canvas contracts for the single pre-build rollback authority."""

from __future__ import annotations

from unittest import mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.domain.transactions import RestoreOutcome
from chemvas.features.insertion import (
    TemplateInsertRequest,
    plan_template_commit,
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


def _draw_chain(canvas, size):
    for index in range(size):
        canvas.model.add_atom("C", index * 40.0, 0.0)
    for index in range(size - 1):
        canvas.model.add_bond(index, index + 1, 1)
    canvas.services.structure_build_service.render_model()


@pytest.mark.parametrize("size", [2, 100])
def test_recorded_ring_uses_one_prebuild_capture_and_round_trips(canvas, size):
    _draw_chain(canvas, size)
    before = _document(canvas)
    history = canvas.services.history_service
    service = canvas.services.structure_build_service
    captured_atom_counts = []
    capture = DocumentSavepoint.capture

    def capture_before_mutation(*args, **kwargs):
        captured_atom_counts.append(len(canvas.model.atoms))
        return capture(*args, **kwargs)

    with mock.patch.object(
        DocumentSavepoint,
        "capture",
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
    service = canvas.services.structure_build_service
    history = canvas.services.history_service
    service.sprout_regular_ring_from_atom(0, 5)
    service.sprout_regular_ring_from_atom(1, 6)
    history.undo()
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
        target = canvas.services.canvas_history_recording_service
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


def test_failed_build_capture_propagates_before_the_document_changes(canvas):
    service = canvas.services.structure_build_service
    _draw_chain(canvas, 3)
    service.sprout_regular_ring_from_atom(0, 6)
    before = _document(canvas)
    history = canvas.services.history_service
    history_before = tuple(history.state.history)
    scene_items = tuple(canvas.scene().items())
    primary = RuntimeError("build capture failed")

    with mock.patch.object(DocumentSavepoint, "capture", side_effect=primary):
        with pytest.raises(RuntimeError) as raised:
            service.sprout_regular_ring_from_atom(1, 5)

    assert raised.value is primary
    assert not getattr(primary, "__notes__", ())
    assert _document(canvas) == before
    assert tuple(canvas.scene().items()) == scene_items
    assert tuple(history.state.history) == history_before


def _document_with_undo_and_redo(canvas):
    _draw_chain(canvas, 3)
    service = canvas.services.structure_build_service
    service.sprout_regular_ring_from_atom(0, 5)
    service.sprout_regular_ring_from_atom(2, 6)
    canvas.services.history_service.undo()


def _sprout_ring(canvas):
    canvas.services.structure_build_service.sprout_regular_ring_from_atom(2, 6)


def _insert_ring_template(canvas):
    request = TemplateInsertRequest(6, (80.0, 60.0), atom_id=2)
    plan = plan_template_commit(request)
    resolution = TemplateGeometryResolverService(canvas).resolve_insert(request, plan)
    assert apply_template_commit_resolution(canvas, request, plan, resolution)


def _draw_free_bond(canvas):
    assert canvas.services.structure_build_service.add_bond_between_points(
        QPointF(300.0, 300.0), QPointF(340.0, 300.0), "single", 1
    )


@pytest.mark.parametrize(
    ("build", "failure_point"),
    [
        (_sprout_ring, "push"),
        (_insert_ring_template, "push"),
        (_draw_free_bond, "recording"),
    ],
)
def test_failed_recorded_build_is_restored_by_its_savepoint(
    canvas, build, failure_point
):
    _document_with_undo_and_redo(canvas)
    history = canvas.services.history_service
    before = _document(canvas)
    model = canvas.model
    scene_items = tuple(canvas.scene().items())
    ring_items = tuple(canvas.runtime_state.ring_items())
    mark_items = tuple(canvas.runtime_state.scene_items("mark_items"))
    history_list = history.state.history
    redo_list = history.state.redo_stack
    history_before = tuple(history_list)
    redo_before = tuple(redo_list)
    failure = RuntimeError(f"build {failure_point} failure")
    if failure_point == "recording":
        failing = mock.patch.object(
            canvas.services.canvas_history_recording_service,
            "record_additions",
            side_effect=failure,
        )
    else:
        failing = mock.patch.object(history, "push", side_effect=failure)

    with failing, pytest.raises(RuntimeError) as raised:
        build(canvas)

    assert raised.value is failure
    assert canvas.model is model
    assert _document(canvas) == before
    assert tuple(canvas.scene().items()) == scene_items
    assert tuple(canvas.runtime_state.ring_items()) == ring_items
    assert tuple(canvas.runtime_state.scene_items("mark_items")) == mark_items
    assert history.state.history is history_list
    assert history.state.redo_stack is redo_list
    assert tuple(history_list) == history_before
    assert tuple(redo_list) == redo_before

    build(canvas)
    assert len(history_list) == len(history_before) + 1
    assert redo_list == []
    history.undo()
    assert _document(canvas) == before


def test_abandoned_build_is_restored_by_its_savepoint(canvas):
    _document_with_undo_and_redo(canvas)
    service = canvas.services.structure_build_service
    history = canvas.services.history_service
    before = _document(canvas)
    scene_items = tuple(canvas.scene().items())
    ring_items = tuple(canvas.runtime_state.ring_items())
    history_before = tuple(history.state.history)
    redo_before = tuple(history.state.redo_stack)
    ring_points = [QPointF(200.0 + 30.0 * index, 200.0) for index in range(3)]
    built_ring_items = []

    def abandon_after_building_a_ring():
        service.add_ring_from_points(ring_points, elements=["N", "C", "O"])
        built_ring_items.extend(canvas.runtime_state.ring_items())
        return None

    assert service.run_recorded_build(abandon_after_building_a_ring) == []

    assert len(built_ring_items) == len(ring_items) + 1
    assert _document(canvas) == before
    assert tuple(canvas.scene().items()) == scene_items
    assert tuple(canvas.runtime_state.ring_items()) == ring_items
    assert tuple(history.state.history) == history_before
    assert tuple(history.state.redo_stack) == redo_before


@pytest.mark.parametrize("build_failed", [False, True])
def test_failed_build_restore_is_not_preceded_by_relative_repair(canvas, build_failed):
    _draw_chain(canvas, 2)
    committer = canvas.services.structure_build_service.committer
    snapshot = committer.begin_recorded_change()
    atom_id = committer.add_atom("N", 160.0, 80.0)
    ring_item = committer.add_ring_fill(
        [QPointF(160.0, 80.0), QPointF(200.0, 80.0), QPointF(180.0, 120.0)],
        [atom_id, 0, 1],
    )
    restore_error = RuntimeError("build restore failed")
    primary = RuntimeError("build failed")

    with mock.patch.object(
        DocumentSavepoint,
        "restore",
        autospec=True,
        return_value=RestoreOutcome(authoritative=False, errors=(restore_error,)),
    ) as restore:
        if build_failed:
            committer.abort_recorded_change(snapshot, original_error=primary)
        else:
            with pytest.raises(RuntimeError) as raised:
                committer.abort_recorded_change(snapshot)
            assert raised.value is restore_error

    restore.assert_called_once()
    if build_failed:
        assert any("build restore failed" in note for note in primary.__notes__)
    # Nothing but the savepoint undoes the build: when its restore is not
    # authoritative, the half-built atom and ring fill stay for the user to see.
    assert canvas.model.atom_for_id(atom_id) is not None
    assert ring_item in canvas.runtime_state.ring_items()
    assert ring_item.scene() is canvas.scene()


def _bond_items(canvas):
    return {
        bond_id: tuple(items)
        for bond_id, items in canvas.runtime_state.bond_graphics_state.bond_items.items()
    }


def _bond_shapes(canvas):
    return {
        bond_id: [item.shape() for item in items]
        for bond_id, items in _bond_items(canvas).items()
    }


def _draw_double_over_first_bond(canvas):
    # Both ends land on existing atoms, so the build updates bond 0 in place.
    assert canvas.services.structure_build_service.add_bond_between_points(
        QPointF(0.0, 0.0), QPointF(40.0, 0.0), "double", 2
    ) == (0, 1)


def _fail_on_call(canvas, method, call_number, failure):
    """Fail one call of a bond renderer method after it has redrawn."""

    original = getattr(canvas.bond_renderer, method)
    calls = []

    def redraw(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(args)
        if len(calls) == call_number:
            raise failure
        return result

    return mock.patch.object(canvas.bond_renderer, method, side_effect=redraw)


@pytest.mark.parametrize("failure_point", ["bond redraw", "connected redraw", "push"])
def test_failed_bond_overlay_is_restored_by_its_savepoint(canvas, failure_point):
    _document_with_undo_and_redo(canvas)
    history = canvas.services.history_service
    before = _document(canvas)
    model = canvas.model
    bond = model.bonds[0]
    scene_items = tuple(canvas.scene().items())
    bond_items = _bond_items(canvas)
    bond_shapes = _bond_shapes(canvas)
    history_list = history.state.history
    redo_list = history.state.redo_stack
    history_before = tuple(history_list)
    redo_before = tuple(redo_list)
    failure = RuntimeError(f"bond overlay {failure_point} failure")
    if failure_point == "bond redraw":
        failing = _fail_on_call(canvas, "redraw_bond", 1, failure)
    elif failure_point == "connected redraw":
        failing = _fail_on_call(canvas, "redraw_connected_bonds", 2, failure)
    else:
        failing = mock.patch.object(history, "push", side_effect=failure)

    with failing, pytest.raises(RuntimeError) as raised:
        _draw_double_over_first_bond(canvas)

    assert raised.value is failure
    assert canvas.model is model
    assert model.bonds[0] is bond
    assert (bond.order, bond.style) == (1, "single")
    assert _document(canvas) == before
    assert tuple(canvas.scene().items()) == scene_items
    assert _bond_items(canvas) == bond_items
    assert _bond_shapes(canvas) == bond_shapes
    assert history.state.history is history_list
    assert history.state.redo_stack is redo_list
    assert tuple(history_list) == history_before
    assert tuple(redo_list) == redo_before

    _draw_double_over_first_bond(canvas)
    assert (bond.order, bond.style) == (2, "double")
    assert len(history_list) == len(history_before) + 1
    assert redo_list == []
    history.undo()
    assert _document(canvas) == before
    assert _bond_shapes(canvas) == bond_shapes


def test_failed_bond_overlay_restore_is_not_preceded_by_relative_repair(canvas):
    _draw_chain(canvas, 2)
    bond = canvas.model.bonds[0]
    restore_error = RuntimeError("bond overlay restore failed")
    failure = RuntimeError("bond overlay push failed")

    with (
        mock.patch.object(
            DocumentSavepoint,
            "restore",
            autospec=True,
            return_value=RestoreOutcome(authoritative=False, errors=(restore_error,)),
        ) as restore,
        mock.patch.object(canvas.services.history_service, "push", side_effect=failure),
        pytest.raises(RuntimeError) as raised,
    ):
        _draw_double_over_first_bond(canvas)

    assert raised.value is failure
    restore.assert_called_once()
    assert any("bond overlay restore failed" in note for note in failure.__notes__)
    # Nothing but the savepoint undoes the overlay: when its restore is not
    # authoritative, the bond keeps the order and style the build gave it.
    assert (bond.order, bond.style) == (2, "double")
