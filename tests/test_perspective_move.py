"""Selection moves preserve drawing depth without moving the camera frame."""

from __future__ import annotations

import json
from itertools import pairwise
from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from chemvas.ui.atom_coords_access import (
    atom_coords_3d_for,
    current_atom_coords_3d_for,
    stored_atom_coords_3d_matches_projection_for,
)
from chemvas.ui.bond_graphics_access import project_point_3d_for
from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
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


def _select_atoms(canvas, atom_ids):
    canvas.scene().clearSelection()
    for atom_id in atom_ids:
        item = atom_items_for(canvas).get(atom_id) or atom_dots_for(canvas)[atom_id]
        item.setSelected(True)


def _rotated_chain(canvas):
    atom_ids = [add_atom_for(canvas, "C", x, 0.0) for x in (-80.0, 0.0, 80.0)]
    for first, second in pairwise(atom_ids):
        add_bond_for(canvas, first, second)
    canvas.services.structure.structure_build_service.render_model()
    _select_atoms(canvas, atom_ids)
    controller = canvas.services.interaction.selection_rotation_controller
    assert controller.begin_selection_3d_rotation(press_pos=QPointF())
    controller.update_selection_3d_rotation(200.0, 0.0)
    controller.end_selection_3d_rotation()
    return atom_ids


def _event_at(canvas, point):
    position = QPointF(canvas.mapFromScene(point))
    return SimpleNamespace(
        position=lambda: position,
        button=lambda: Qt.MouseButton.LeftButton,
        modifiers=lambda: Qt.KeyboardModifier.NoModifier,
    )


def _start_drag(canvas, atom_ids):
    _select_atoms(canvas, atom_ids)
    canvas.services.tool_controller.set_active("select")
    tool = canvas.services.tool_controller.active
    atom = canvas.model.atoms[min(atom_ids)]
    start = QPointF(atom.x, atom.y)
    assert tool.on_mouse_press(_event_at(canvas, start))
    assert tool._selection_atom_ids == set(atom_ids)
    return tool, start


def _positions(canvas):
    return {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()}


def _assert_points_match(actual, expected):
    assert actual.keys() == expected.keys()
    for key in actual:
        assert actual[key] == pytest.approx(expected[key], abs=1e-10)


@pytest.mark.parametrize("whole", [False, True])
def test_move_gesture_preserves_depth_for_history_copy_paste_and_next_rotation(
    canvas, whole
):
    atom_ids = _rotated_chain(canvas)
    moving = set(atom_ids if whole else atom_ids[:1])
    rotation = rotation_state_for(canvas)
    frame = (rotation.projection_center_3d, rotation.projection_anchor_2d)
    before_positions = _positions(canvas)
    before_coords = dict(atom_coords_3d_for(canvas))
    history = canvas.services.history_service
    before_commands = len(history.state.history)
    tool, start = _start_drag(canvas, moving)
    end_event = _event_at(canvas, start + QPointF(100.0, 30.0))
    assert tool.on_mouse_move(end_event)
    assert tool.on_mouse_release(end_event)

    assert len(history.state.history) == before_commands + 1
    assert (rotation.projection_center_3d, rotation.projection_anchor_2d) == frame
    moved_positions = _positions(canvas)
    moved_coords = dict(atom_coords_3d_for(canvas))
    for atom_id in atom_ids:
        assert moved_coords[atom_id][2] == before_coords[atom_id][2]
        assert stored_atom_coords_3d_matches_projection_for(
            canvas, atom_id, moved_coords[atom_id]
        )
        if atom_id not in moving:
            assert moved_positions[atom_id] == before_positions[atom_id]
            assert moved_coords[atom_id] == before_coords[atom_id]
    history.undo()
    _assert_points_match(_positions(canvas), before_positions)
    _assert_points_match(atom_coords_3d_for(canvas), before_coords)
    history.redo()
    _assert_points_match(_positions(canvas), moved_positions)
    _assert_points_match(atom_coords_3d_for(canvas), moved_coords)

    _select_atoms(canvas, moving)
    clipboard = canvas.services.scene_operations.scene_clipboard_controller
    payload = clipboard.selection_payload_for_clipboard()
    assert payload is not None
    copied = payload["perspective"]["atom_coords_3d"]
    assert {entry["atom_id"] for entry in copied} == moving
    assert clipboard.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, json.dumps(payload))
    )
    pasted_ids = set(canvas.model.atoms) - set(atom_ids)
    assert len(pasted_ids) == len(moving)
    assert sorted(atom_coords_3d_for(canvas)[aid][2] for aid in pasted_ids) == sorted(
        moved_coords[aid][2] for aid in moving
    )
    for atom_id in pasted_ids:
        assert stored_atom_coords_3d_matches_projection_for(
            canvas, atom_id, atom_coords_3d_for(canvas)[atom_id]
        )
    assert (rotation.projection_center_3d, rotation.projection_anchor_2d) == frame

    _select_atoms(canvas, atom_ids)
    controller = canvas.services.interaction.selection_rotation_controller
    assert controller.begin_selection_3d_rotation(press_pos=QPointF())
    for atom_id in atom_ids:
        assert rotation.start_coords_3d[atom_id][2] == moved_coords[atom_id][2]
    controller.update_selection_3d_rotation(5.0, -3.0)
    controller.end_selection_3d_rotation()
    for atom_id in atom_ids:
        assert stored_atom_coords_3d_matches_projection_for(
            canvas, atom_id, atom_coords_3d_for(canvas)[atom_id]
        )


def test_move_keeps_stale_depth_stale_instead_of_realigning_it(canvas):
    atom_ids = _rotated_chain(canvas)
    atom_id = atom_ids[0]
    coords = atom_coords_3d_for(canvas)[atom_id]
    atom = canvas.model.atoms[atom_id]
    atom.x += 100.0
    before_error = project_point_3d_for(canvas, coords)[0] - atom.x
    assert not stored_atom_coords_3d_matches_projection_for(canvas, atom_id, coords)

    canvas.services.interaction.move_controller.move_atoms({atom_id}, 100.0, 30.0)

    after_coords = atom_coords_3d_for(canvas)[atom_id]
    after_error = project_point_3d_for(canvas, after_coords)[0] - atom.x
    assert after_error == pytest.approx(before_error)
    assert after_coords[2] == coords[2]
    assert not stored_atom_coords_3d_matches_projection_for(
        canvas, atom_id, after_coords
    )
    assert current_atom_coords_3d_for(canvas, atom_id)[2] == 0.0


@pytest.mark.parametrize("failure_phase", ["frame", "push"])
def test_failed_perspective_move_restores_scoped_document(canvas, failure_phase):
    atom_ids = _rotated_chain(canvas)
    before = canvas.services.document.canvas_document_session_service.snapshot_state()
    before_coords = dict(atom_coords_3d_for(canvas))
    tool, start = _start_drag(canvas, {atom_ids[0]})
    event = _event_at(canvas, start + QPointF(100.0, 30.0))
    if failure_phase == "frame":
        with (
            mock.patch(
                "chemvas.ui.selection_drag_tool.shift_selection_outlines_for",
                side_effect=RuntimeError("failed frame"),
            ),
            pytest.raises(RuntimeError, match="failed frame"),
        ):
            tool.on_mouse_move(event)
    else:
        tool.on_mouse_move(event)
        with (
            mock.patch.object(
                canvas.services.history_service, "push", return_value=False
            ),
            pytest.raises(RuntimeError, match="did not commit"),
        ):
            tool.on_mouse_release(event)
    assert (
        canvas.services.document.canvas_document_session_service.snapshot_state()
        == before
    )
    assert atom_coords_3d_for(canvas) == before_coords
