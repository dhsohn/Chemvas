"""Real-canvas edit round trips and bounded selection redraw work."""

from __future__ import annotations

import math
from itertools import pairwise
from pathlib import Path
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.ui.atom_coords_access import (
    atom_coords_3d_for,
    stored_atom_coords_3d_matches_projection_for,
)
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.scene_decoration_access import (
    add_arrow_for,
    add_mark_for_atom_for,
    add_shape_for,
)
from chemvas.ui.scene_signal_blocking import blocked_scene_signals
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.selection_service_access import (
    refresh_selection_outline_for,
    selection_service_from_canvas,
)
from chemvas.ui.structure_mutation_access import (
    add_atom_for,
    add_benzene_ring_for,
    add_bond_for,
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
    view.resize(800, 600)
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _chain(canvas, count=6, *, offset=0.0):
    ids = [
        add_atom_for(
            canvas, "C", offset + index * math.sqrt(3) * 10, (index % 2) * 10.0
        )
        for index in range(count)
    ]
    for first, second in pairwise(ids):
        add_bond_for(canvas, first, second)
    canvas.services.structure.structure_build_service.render_model()
    select_all_scene_items_for(canvas)
    return ids


def _perspective(canvas):
    rotation = canvas.services.interaction.selection_rotation_controller
    assert rotation.begin_selection_3d_rotation(press_pos=QPointF())
    rotation.update_selection_3d_rotation(80.0, 0.0)
    rotation.end_selection_3d_rotation()


def _transform(canvas, kind):
    controller = canvas.services.scene_operations.scene_transform_controller
    if kind == "nudge":
        assert controller.translate_selected_items(10.0, 0.0)
    elif kind == "align":
        assert controller.align_selected_items("right")
    elif kind == "horizontal":
        controller.flip_selected_items(True)
    elif kind == "vertical":
        controller.flip_selected_items(False)
    else:
        controller.rotate_selected_items(15.0)


def test_nudge_and_undo_restore_exact_saved_example(canvas):
    source = Path(__file__).resolve().parents[1] / "examples/first-scheme.chemvas"
    restore_canvas_state_for(canvas, read_document(source).state)
    select_all_scene_items_for(canvas)
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    controller = canvas.services.scene_operations.scene_transform_controller
    history = canvas.services.history_service
    for dx, dy in ((10.0, 0.0), (0.0, 10.0), (10.0, 0.0)):
        assert controller.translate_selected_items(dx, dy)
    after = snapshot_canvas_state_for(canvas)
    for _ in range(3):
        history.undo()
    assert not history.can_undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
    for _ in range(3):
        history.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("mode", ["top", "left", "right", "middle", "center", "bottom"])
def test_align_and_undo_restore_exact_coordinates(canvas, mode):
    _chain(canvas, 3, offset=112.06166949243676)
    ids = [
        add_atom_for(canvas, "C", x, y)
        for x, y in (
            (5.18518518518518, 73.356),
            (21.78518518518518, 83.356),
            (38.38518518518518, 73.356),
        )
    ]
    for first, second in pairwise(ids):
        add_bond_for(canvas, first, second)
    select_all_scene_items_for(canvas)
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    assert canvas.services.scene_operations.scene_transform_controller.align_selected_items(
        mode
    )
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("kind", ["nudge", "horizontal", "vertical", "rotate"])
def test_2d_transforms_preserve_depth_and_exact_history(canvas, tmp_path, kind):
    ids = _chain(canvas)
    _perspective(canvas)
    before = snapshot_canvas_state_for(canvas)
    before_coords = dict(atom_coords_3d_for(canvas))
    mark_document_clean_for(canvas, before)
    _transform(canvas, kind)
    after = snapshot_canvas_state_for(canvas)
    after_coords = dict(atom_coords_3d_for(canvas))
    assert after_coords.keys() == before_coords.keys()
    for atom_id in ids:
        assert after_coords[atom_id][2] == before_coords[atom_id][2]
        assert stored_atom_coords_3d_matches_projection_for(
            canvas, atom_id, after_coords[atom_id]
        )
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert atom_coords_3d_for(canvas) == before_coords
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    assert atom_coords_3d_for(canvas) == after_coords
    path = tmp_path / "transformed.chemvas"
    write_document(path, after, CANVAS_FILE_VERSION)
    reopened = read_document(path)
    assert len(reopened.state["perspective"]["atom_coords_3d"]) == len(ids)
    rotation = canvas.services.interaction.selection_rotation_controller
    assert rotation.begin_selection_3d_rotation(press_pos=QPointF())
    assert {
        aid: point[2]
        for aid, point in rotation_state_for(canvas).start_coords_3d.items()
    } == {aid: point[2] for aid, point in after_coords.items()}
    rotation.update_selection_3d_rotation(-80.0, 0.0)
    rotation.end_selection_3d_rotation()


def test_nudge_and_history_batch_outline_work(canvas):
    _chain(canvas, 32)
    outline = selection_service_from_canvas(canvas).outline_service
    history = canvas.services.history_service
    for action in (lambda: _transform(canvas, "nudge"), history.undo, history.redo):
        with mock.patch.object(
            outline,
            "add_selection_component_overlay",
            wraps=outline.add_selection_component_overlay,
        ) as rebuild:
            action()
        assert rebuild.call_count == 1


@pytest.mark.parametrize("kind", ["align", "horizontal", "rotate"])
def test_disconnected_transform_and_history_refresh_outline_once(canvas, kind):
    for index in range(16):
        first = add_atom_for(canvas, "C", index * 43.1234, index * 12.789)
        second = add_atom_for(canvas, "C", index * 43.1234 + 20.0, index * 12.789)
        add_bond_for(canvas, first, second)
    select_all_scene_items_for(canvas)
    outline = selection_service_from_canvas(canvas).outline_service
    history = canvas.services.history_service
    for action in (lambda: _transform(canvas, kind), history.undo, history.redo):
        with mock.patch.object(
            outline, "update_selection_outline", wraps=outline.update_selection_outline
        ) as refresh:
            action()
        assert refresh.call_count == 1


def _mixed_drawing(canvas):
    ring = add_benzene_ring_for(canvas, QPointF(112.06166949243676, 19.379951921598458))
    assert ring is not None
    atom_ids = list(ring.data(2))
    select_all_scene_items_for(canvas)
    _perspective(canvas)
    atom = canvas.model.atoms[atom_ids[0]]
    add_mark_for_atom_for(
        canvas, atom_ids[0], QPointF(atom.x + 8.3, atom.y - 7.1), kind="plus"
    )
    arrow = add_arrow_for(
        canvas,
        QPointF(-40.67611574296892, 60.379951921598458),
        QPointF(45.18518518518518, 60.379951921598458),
        "arrow",
    )
    add_shape_for(canvas, QRectF(-100.3, 80.7, 30.2, 20.1), shape_kind="rectangle")
    canvas.services.interaction.note_controller.create_text_note(
        QPointF(-100.3, 110.7), "Keep this note"
    )
    select_all_scene_items_for(canvas)
    return atom_ids, arrow


@pytest.mark.parametrize("kind", ["nudge", "align", "horizontal", "vertical", "rotate"])
def test_mixed_geometry_roundtrip_is_exact_and_captures_once(canvas, kind):
    _mixed_drawing(canvas)
    before = snapshot_canvas_state_for(canvas)
    before_coords = dict(atom_coords_3d_for(canvas))
    history = canvas.services.history_service
    with mock.patch.object(
        DocumentSavepoint, "capture", wraps=DocumentSavepoint.capture
    ) as capture:
        _transform(canvas, kind)
    assert capture.call_count == 1
    after = snapshot_canvas_state_for(canvas)
    for action, expected in ((history.undo, before), (history.redo, after)):
        with mock.patch.object(
            DocumentSavepoint, "capture", wraps=DocumentSavepoint.capture
        ) as capture:
            action()
        assert capture.call_count == 1
        assert snapshot_canvas_state_for(canvas) == expected
    history.undo()
    assert atom_coords_3d_for(canvas) == before_coords


@pytest.mark.parametrize("kind", ["nudge", "horizontal", "vertical", "rotate"])
def test_partial_transform_preserves_boundary_bond_and_unselected_depth(canvas, kind):
    ids = _chain(canvas)
    _perspective(canvas)
    with blocked_scene_signals(canvas.scene()):
        canvas.scene().clearSelection()
        for atom_id in ids[:2]:
            visible_atom_item_for(canvas, atom_id).setSelected(True)
    refresh_selection_outline_for(canvas)
    before = snapshot_canvas_state_for(canvas)
    untouched_coords = {aid: atom_coords_3d_for(canvas)[aid] for aid in ids[2:]}
    boundary_items = tuple(bond_items_for_id(canvas, 1))
    _transform(canvas, kind)
    after = snapshot_canvas_state_for(canvas)
    assert tuple(bond_items_for_id(canvas, 1)) == boundary_items
    assert {aid: atom_coords_3d_for(canvas)[aid] for aid in ids[2:]} == untouched_coords
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("kind", ["nudge", "align", "horizontal", "rotate"])
@pytest.mark.parametrize("phase", ["mutation", "push", "undo", "redo"])
def test_transform_failure_restores_geometry_and_retryable_history(canvas, kind, phase):
    _mixed_drawing(canvas)
    history = canvas.services.history_service
    if phase in {"undo", "redo"}:
        _transform(canvas, kind)
        if phase == "redo":
            history.undo()
    before = snapshot_canvas_state_for(canvas)
    before_coords = dict(atom_coords_3d_for(canvas))
    before_scene = set(canvas.scene().items())
    before_stacks = history.capture_stack_snapshot()
    controller = canvas.services.scene_operations.scene_transform_controller
    if phase == "push":
        failure = mock.patch.object(history, "push", return_value=False)
    elif phase in {"undo", "redo"}:
        # Rebuilding a dependent item can fail after the atoms have changed.
        failure = mock.patch(
            "chemvas.ui.history_commands._apply_scene_item_state",
            side_effect=RuntimeError("item render failed"),
        )
    elif kind in {"nudge", "align"}:
        failure = mock.patch(
            "chemvas.ui.scene_transform_controller.move_item_for",
            side_effect=RuntimeError("item render failed"),
        )
    else:
        failure = mock.patch.object(
            controller,
            "_apply_scene_item_state",
            side_effect=RuntimeError("item render failed"),
        )
    action = (
        getattr(history, phase)
        if phase in {"undo", "redo"}
        else lambda: _transform(canvas, kind)
    )
    with failure, pytest.raises(RuntimeError):
        action()
    assert snapshot_canvas_state_for(canvas) == before
    assert atom_coords_3d_for(canvas) == before_coords
    assert set(canvas.scene().items()) == before_scene
    history.verify_stack_snapshot(before_stacks)
    assert not canvas.scene().signalsBlocked()
    action()


def test_rotation_handle_return_to_start_restores_exact_depth(canvas):
    _chain(canvas)
    _perspective(canvas)
    controller = canvas.services.scene_operations.scene_transform_controller
    before = snapshot_canvas_state_for(canvas)
    before_coords = dict(atom_coords_3d_for(canvas))
    session = controller.begin_rotation_drag(QPointF(120.0, 40.0))
    assert session is not None
    controller.update_rotation_drag(session, QPointF(110.0, 70.0))
    assert snapshot_canvas_state_for(canvas) != before
    controller.update_rotation_drag(session, session.press_pos)
    assert snapshot_canvas_state_for(canvas) == before
    assert atom_coords_3d_for(canvas) == before_coords
    assert controller.rotation_drag_command(session) is None


def test_rotation_handle_commit_restores_exact_geometry_and_depth(canvas):
    _mixed_drawing(canvas)
    controller = canvas.services.scene_operations.scene_transform_controller
    before = snapshot_canvas_state_for(canvas)
    before_coords = dict(atom_coords_3d_for(canvas))
    session = controller.begin_rotation_drag(QPointF(120.0, 40.0))
    assert session is not None
    controller.update_rotation_drag(session, QPointF(110.0, 70.0))
    after = snapshot_canvas_state_for(canvas)
    after_coords = dict(atom_coords_3d_for(canvas))
    command = controller.rotation_drag_command(session)
    assert command is not None
    history = canvas.services.history_service
    history.push(command)
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert atom_coords_3d_for(canvas) == before_coords
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    assert atom_coords_3d_for(canvas) == after_coords


@pytest.mark.parametrize("kind", ["horizontal", "rotate"])
def test_2d_transform_does_not_launder_stale_projection_coordinates(canvas, kind):
    ids = _chain(canvas)
    _perspective(canvas)
    stale_id = ids[0]
    coords = atom_coords_3d_for(canvas)
    x, y, z = coords[stale_id]
    coords[stale_id] = (x + 100.0, y, z)
    before_coords = dict(coords)
    assert not stored_atom_coords_3d_matches_projection_for(
        canvas, stale_id, coords[stale_id]
    )
    _transform(canvas, kind)
    assert coords[stale_id][2] == z
    assert not stored_atom_coords_3d_matches_projection_for(
        canvas, stale_id, coords[stale_id]
    )
    canvas.services.history_service.undo()
    assert atom_coords_3d_for(canvas) == before_coords


def test_exact_geometry_command_restores_absent_depth_only_in_its_footprint(canvas):
    from chemvas.core.history import SetAtomPositionsCommand
    from chemvas.ui.history_commands import SetSceneGeometryCommand

    ids = _chain(canvas)
    _perspective(canvas)
    before = dict(atom_coords_3d_for(canvas))
    atom = canvas.model.atoms[ids[0]]
    command = SetSceneGeometryCommand(
        [
            SetAtomPositionsCommand(
                before_positions={ids[0]: (atom.x, atom.y)},
                after_positions={ids[0]: (atom.x, atom.y)},
                before_coords_3d={},
                after_coords_3d={ids[0]: before[ids[0]]},
            )
        ],
        [],
    )
    command.undo(canvas)
    assert atom_coords_3d_for(canvas) == {
        aid: point for aid, point in before.items() if aid != ids[0]
    }
    command.redo(canvas)
    assert atom_coords_3d_for(canvas) == before
