"""Selection moves preserve drawing depth without moving the camera frame."""

from __future__ import annotations

import json
from itertools import pairwise
from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.domain.document.perspective import unproject_point_3d
from chemvas.ui.molecule.atom_coords_access import (
    current_atom_coords_3d_for,
    stored_atom_coords_3d_matches_projection_for,
)
from chemvas.ui.molecule.bond_graphics_access import project_point_3d_for
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
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
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _select_atoms(canvas, atom_ids):
    canvas.scene().clearSelection()
    for atom_id in atom_ids:
        item = (
            canvas.runtime_state.atom_graphics_state.atom_items.get(atom_id)
            or canvas.runtime_state.atom_graphics_state.atom_dots[atom_id]
        )
        item.setSelected(True)


def _rotated_chain(canvas):
    atom_ids = [
        canvas.services.canvas_atom_mutation_service.add_atom("C", x, 0.0)
        for x in (-80.0, 0.0, 80.0)
    ]
    for first, second in pairwise(atom_ids):
        add_bond_for(canvas, first, second)
    canvas.services.structure_build_service.render_model()
    _select_atoms(canvas, atom_ids)
    controller = canvas.services.selection_rotation_controller
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


def _bond_segments(canvas):
    segments = {}
    for bond_id, items in canvas.runtime_state.bond_graphics_state.bond_items.items():
        segments[bond_id] = [
            (point.x(), point.y())
            for item in items
            for point in (
                item.mapToScene(item.line().p1()),
                item.mapToScene(item.line().p2()),
            )
        ]
    return segments


@pytest.mark.parametrize("style", ["double", "double_center", "double_outer"])
@pytest.mark.parametrize("clamped", [False, True])
@pytest.mark.parametrize("labelled", [False, True])
def test_moving_perspective_benzene_preserves_every_bond_segment(
    canvas, tmp_path, style, clamped, labelled
):
    canvas.services.structure_build_service.add_benzene_ring(QPointF())
    atoms = set(canvas.model.atoms)
    if labelled:
        canvas.model.atoms[min(atoms)].element = "N"
    for bond in canvas.model.bonds:
        if bond is not None and bond.order == 2:
            bond.style = style
    canvas.services.structure_build_service.add_benzene_ring(QPointF(-140, -80))
    fixed_bonds = {
        index
        for index, bond in enumerate(canvas.model.bonds)
        if bond is not None and bond.a not in atoms
    }
    canvas.services.structure_build_service.render_model()
    _select_atoms(canvas, atoms)
    rotation = canvas.services.selection_rotation_controller
    assert rotation.begin_selection_3d_rotation(press_pos=QPointF())
    rotation.update_selection_3d_rotation(160.0, 110.0)
    rotation.end_selection_3d_rotation()
    frame = canvas.runtime_state.rotation_state
    camera = (frame.projection_center_3d, frame.projection_anchor_2d)
    if clamped:
        for index, atom_id in enumerate(sorted(atoms)):
            atom = canvas.model.atoms[atom_id]
            canvas.runtime_state.atom_coords_3d_state.atom_coords_3d[atom_id] = (
                unproject_point_3d(
                    (atom.x, atom.y),
                    (index - 2) * 200.0,
                    bond_length_px=canvas.renderer.style.bond_length_px,
                    center_3d=frame.projection_center_3d,
                    anchor_2d=frame.projection_anchor_2d,
                )
            )
    canvas.services.structure_build_service.render_model()
    before = _bond_segments(canvas)
    before_positions = _positions(canvas)
    tool, start = _start_drag(canvas, atoms)
    event = _event_at(canvas, start + QPointF(200, 110))
    assert tool.on_mouse_move(event)
    assert tool.on_mouse_release(event)
    atom_id = min(atoms)
    dx = canvas.model.atoms[atom_id].x - before_positions[atom_id][0]
    dy = canvas.model.atoms[atom_id].y - before_positions[atom_id][1]
    canvas.services.structure_build_service.render_model()
    after = _bond_segments(canvas)
    for bond_id, points in before.items():
        for old, new in zip(points, after[bond_id], strict=True):
            delta = (0, 0) if bond_id in fixed_bonds else (dx, dy)
            assert new == pytest.approx(
                (old[0] + delta[0], old[1] + delta[1]), abs=1e-8
            )
    assert (frame.projection_center_3d, frame.projection_anchor_2d) == camera
    history = canvas.services.history_service
    history.undo()
    for bond_id, points in _bond_segments(canvas).items():
        for actual, expected in zip(points, before[bond_id], strict=True):
            assert actual == pytest.approx(expected, abs=1e-8)
    history.redo()
    for bond_id, points in _bond_segments(canvas).items():
        for actual, expected in zip(points, after[bond_id], strict=True):
            assert actual == pytest.approx(expected, abs=1e-8)
    path = tmp_path / "moved-perspective.chemvas"
    session = canvas.services.canvas_document_session_service
    write_document(path, session.snapshot_state(), CANVAS_FILE_VERSION)
    session.apply_state(read_document(path).state)
    for bond_id, points in _bond_segments(canvas).items():
        for actual, expected in zip(points, after[bond_id], strict=True):
            assert actual == pytest.approx(expected, abs=1e-8)


@pytest.mark.parametrize("whole", [False, True])
def test_move_gesture_preserves_depth_for_history_copy_paste_and_next_rotation(
    canvas, whole
):
    atom_ids = _rotated_chain(canvas)
    moving = set(atom_ids if whole else atom_ids[:1])
    rotation = canvas.runtime_state.rotation_state
    frame = (rotation.projection_center_3d, rotation.projection_anchor_2d)
    before_positions = _positions(canvas)
    before_coords = dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d)
    history = canvas.services.history_service
    before_commands = len(history.state.history)
    tool, start = _start_drag(canvas, moving)
    end_event = _event_at(canvas, start + QPointF(100.0, 30.0))
    assert tool.on_mouse_move(end_event)
    assert tool.on_mouse_release(end_event)

    assert len(history.state.history) == before_commands + 1
    assert (rotation.projection_center_3d, rotation.projection_anchor_2d) == frame
    moved_positions = _positions(canvas)
    moved_coords = dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d)
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
    _assert_points_match(
        canvas.runtime_state.atom_coords_3d_state.atom_coords_3d, before_coords
    )
    history.redo()
    _assert_points_match(_positions(canvas), moved_positions)
    _assert_points_match(
        canvas.runtime_state.atom_coords_3d_state.atom_coords_3d, moved_coords
    )

    _select_atoms(canvas, moving)
    clipboard = canvas.services.scene_clipboard_controller
    payload = clipboard.selection_payload_for_clipboard()
    assert payload is not None
    copied = payload["perspective"]["atom_coords_3d"]
    assert {entry["atom_id"] for entry in copied} == moving
    assert clipboard.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, json.dumps(payload))
    )
    pasted_ids = set(canvas.model.atoms) - set(atom_ids)
    assert len(pasted_ids) == len(moving)
    assert sorted(
        canvas.runtime_state.atom_coords_3d_state.atom_coords_3d[aid][2]
        for aid in pasted_ids
    ) == sorted(moved_coords[aid][2] for aid in moving)
    for atom_id in pasted_ids:
        assert stored_atom_coords_3d_matches_projection_for(
            canvas,
            atom_id,
            canvas.runtime_state.atom_coords_3d_state.atom_coords_3d[atom_id],
        )
    assert (rotation.projection_center_3d, rotation.projection_anchor_2d) == frame

    _select_atoms(canvas, atom_ids)
    controller = canvas.services.selection_rotation_controller
    assert controller.begin_selection_3d_rotation(press_pos=QPointF())
    for atom_id in atom_ids:
        assert rotation.start_coords_3d[atom_id][2] == moved_coords[atom_id][2]
    controller.update_selection_3d_rotation(5.0, -3.0)
    controller.end_selection_3d_rotation()
    for atom_id in atom_ids:
        assert stored_atom_coords_3d_matches_projection_for(
            canvas,
            atom_id,
            canvas.runtime_state.atom_coords_3d_state.atom_coords_3d[atom_id],
        )


def test_move_keeps_stale_depth_stale_instead_of_realigning_it(canvas):
    atom_ids = _rotated_chain(canvas)
    atom_id = atom_ids[0]
    coords = canvas.runtime_state.atom_coords_3d_state.atom_coords_3d[atom_id]
    atom = canvas.model.atoms[atom_id]
    atom.x += 100.0
    before_error = project_point_3d_for(canvas, coords)[0] - atom.x
    assert not stored_atom_coords_3d_matches_projection_for(canvas, atom_id, coords)

    canvas.services.move_controller.move_atoms({atom_id}, 100.0, 30.0)

    after_coords = canvas.runtime_state.atom_coords_3d_state.atom_coords_3d[atom_id]
    after_error = project_point_3d_for(canvas, after_coords)[0] - atom.x
    assert after_error == pytest.approx(before_error)
    assert after_coords[2] == coords[2]
    assert not stored_atom_coords_3d_matches_projection_for(
        canvas, atom_id, after_coords
    )
    assert current_atom_coords_3d_for(canvas, atom_id)[2] == 0.0


@pytest.mark.parametrize("failure_phase", ["frame", "disabled"])
def test_failed_perspective_move_restores_scoped_document(canvas, failure_phase):
    atom_ids = _rotated_chain(canvas)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    before_coords = dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d)
    tool, start = _start_drag(canvas, {atom_ids[0]})
    event = _event_at(canvas, start + QPointF(100.0, 30.0))
    if failure_phase == "frame":
        with (
            mock.patch.object(
                canvas.services.selection,
                "shift_selection_outlines",
                side_effect=RuntimeError("failed frame"),
            ),
            pytest.raises(RuntimeError, match="failed frame"),
        ):
            tool.on_mouse_move(event)
    else:
        tool.on_mouse_move(event)
        with (
            mock.patch.object(canvas.services.history_service.state, "enabled", False),
            pytest.raises(RuntimeError, match="History is disabled"),
        ):
            tool.on_mouse_release(event)
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d == before_coords


@pytest.mark.parametrize("stale_offset", [0.0, 3.25])
def test_absolute_and_relative_moves_preserve_the_same_perspective(
    canvas, stale_offset
):
    """Live translation and history placement agree even with stale projection data."""
    atom_ids = _rotated_chain(canvas)
    positions = {
        atom_id: (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y)
        for atom_id in atom_ids
    }
    stored = canvas.runtime_state.atom_coords_3d_state.atom_coords_3d
    first = atom_ids[0]
    x, y, z = stored[first]
    stored[first] = (x + stale_offset, y, z)
    before_coords = dict(stored)
    rotation = canvas.runtime_state.rotation_state
    camera = (rotation.projection_center_3d, rotation.projection_anchor_2d)
    controller = canvas.services.move_controller
    controller.move_atoms(set(atom_ids), 37.0, -19.0)
    expected_coords = dict(stored)
    expected_segments = _bond_segments(canvas)
    expected_positions = {
        atom_id: (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y)
        for atom_id in atom_ids
    }

    controller.set_atom_positions(positions, coords_3d=before_coords)
    assert stored == before_coords
    controller.set_atom_positions(expected_positions)
    assert stored == expected_coords
    for bond_id, segments in _bond_segments(canvas).items():
        for actual, expected in zip(segments, expected_segments[bond_id], strict=True):
            assert actual == pytest.approx(expected, abs=1e-8)
    assert (rotation.projection_center_3d, rotation.projection_anchor_2d) == camera


@pytest.mark.parametrize("style", ["double", "double_center", "double_outer"])
@pytest.mark.parametrize("rotate", [False, True])
def test_pasted_perspective_ring_keeps_segments_through_move_and_history(
    canvas, tmp_path, style, rotate
):
    canvas.services.structure_build_service.add_benzene_ring(QPointF())
    for bond in canvas.model.bonds:
        if bond is not None and bond.order == 2:
            bond.style = style
    canvas.services.structure_build_service.render_model()
    original_ids = set(canvas.model.atoms)
    _select_atoms(canvas, original_ids)
    rotation = canvas.services.selection_rotation_controller
    assert rotation.begin_selection_3d_rotation(press_pos=QPointF())
    if rotate:
        rotation.update_selection_3d_rotation(160.0, 110.0)
    rotation.end_selection_3d_rotation()
    original_segments = _bond_segments(canvas)
    clipboard = canvas.services.scene_clipboard_controller
    payload = clipboard.selection_payload_for_clipboard()
    assert clipboard.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, json.dumps(payload))
    )
    pasted_ids = set(canvas.model.atoms) - original_ids
    original = canvas.model.atoms[min(original_ids)]
    pasted = canvas.model.atoms[min(pasted_ids)]
    delta = (pasted.x - original.x, pasted.y - original.y)
    pasted_bonds = sorted(set(_bond_segments(canvas)) - set(original_segments))

    def assert_copy():
        actual = _bond_segments(canvas)
        for source, target in zip(sorted(original_segments), pasted_bonds, strict=True):
            for old, new in zip(original_segments[source], actual[target], strict=True):
                assert new == pytest.approx(
                    (old[0] + delta[0], old[1] + delta[1]), abs=1e-8
                )

    assert_copy()
    tool, start = _start_drag(canvas, pasted_ids)
    event = _event_at(canvas, start + QPointF(200, 110))
    assert tool.on_mouse_move(event)
    assert tool.on_mouse_release(event)
    delta = (pasted.x - original.x, pasted.y - original.y)
    assert_copy()
    history = canvas.services.history_service
    for _ in range(3):
        history.undo()
        delta = (pasted.x - original.x, pasted.y - original.y)
        assert_copy()
        history.redo()
        delta = (pasted.x - original.x, pasted.y - original.y)
        assert_copy()
    history.undo()
    history.undo()
    assert set(canvas.model.atoms) == original_ids
    history.redo()
    pasted = canvas.model.atoms[min(pasted_ids)]
    delta = (pasted.x - original.x, pasted.y - original.y)
    assert_copy()
    history.redo()
    delta = (pasted.x - original.x, pasted.y - original.y)
    assert_copy()

    path = tmp_path / "pasted-perspective.chemvas"
    session = canvas.services.canvas_document_session_service
    write_document(path, session.snapshot_state(), CANVAS_FILE_VERSION)
    session.apply_state(read_document(path).state)
    assert_copy()
