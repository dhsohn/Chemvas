"""Changing the drawing camera must not flatten another molecule's depth."""

from __future__ import annotations

import math
from itertools import combinations, pairwise
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import read_document
from chemvas.ui.atom_coords_access import (
    atom_coords_3d_for,
    current_atom_coords_3d_for,
    set_atom_coords_3d_for_id,
    stored_atom_coords_3d_matches_projection_for,
)
from chemvas.ui.bond_graphics_access import project_point_3d_for
from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.scene_item_state_serialization import scene_item_state_for
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


def _chains(canvas):
    chains = []
    for origin in (-250.0, 180.0):
        atoms = [
            add_atom_for(canvas, "C", origin + index * 30.0, (index % 2) * 18.0)
            for index in range(6)
        ]
        bonds = [add_bond_for(canvas, a, b) for a, b in pairwise(atoms)]
        chains.append((atoms, bonds))
    canvas.services.structure.structure_build_service.render_model()
    return chains


def _select(canvas, atoms):
    canvas.scene().clearSelection()
    for atom_id in atoms:
        item = atom_items_for(canvas).get(atom_id) or atom_dots_for(canvas)[atom_id]
        item.setSelected(True)


def _begin(canvas, chain, *, axis=False):
    atoms, bonds = chain
    _select(canvas, atoms)
    controller = canvas.services.interaction.selection_rotation_controller
    atom = canvas.model.atoms[atoms[2]]
    assert controller.begin_selection_3d_rotation(
        axis_hint=bonds[2] if axis else None, press_pos=QPointF(atom.x, atom.y)
    )
    assert controller.rotation.mode == ("bond" if axis else "rigid")
    return controller


def _rotate(canvas, chain, delta=60.0, *, axis=False):
    controller = _begin(canvas, chain, axis=axis)
    controller.update_selection_3d_rotation(delta, 0.0)
    controller.end_selection_3d_rotation()


def _positions(canvas, atoms):
    return {
        aid: (canvas.model.atoms[aid].x, canvas.model.atoms[aid].y) for aid in atoms
    }


def _depths(canvas, atoms):
    return {aid: atom_coords_3d_for(canvas)[aid][2] for aid in atoms}


def _assert_live_depth(canvas, atoms):
    for aid in atoms:
        coords = atom_coords_3d_for(canvas)[aid]
        assert stored_atom_coords_3d_matches_projection_for(canvas, aid, coords)
        assert current_atom_coords_3d_for(canvas, aid) == coords


@pytest.mark.parametrize("axis", [False, True])
def test_other_component_depth_survives_preview_save_reopen_and_exact_history(
    canvas, tmp_path, axis
):
    first, second = _chains(canvas)
    atom = canvas.model.atoms[first[0][1]]
    offset = QPointF(13.7, -9.3)
    mark = canvas.services.scene_decoration.scene_decoration_service.add_mark(
        QPointF(atom.x, atom.y) + offset,
        kind="plus",
        atom_id=first[0][1],
        offset=offset,
        record=False,
    )
    assert mark is not None
    _rotate(canvas, first)
    documents = canvas.services.document.canvas_document_session_service
    before = documents.snapshot_state()
    before_cache = dict(atom_coords_3d_for(canvas))
    positions = _positions(canvas, first[0])
    depths = _depths(canvas, first[0])
    mark_before = scene_item_state_for(canvas, mark)
    assert any(abs(z) > 1.0 for z in depths.values())
    history = canvas.services.history_service
    count = len(history.state.history)

    controller = _begin(canvas, second, axis=axis)
    expected_cached_ids = set(controller.rotation.coord_atom_ids)
    _assert_live_depth(canvas, first[0])
    controller.update_selection_3d_rotation(40.0, 0.0)
    _assert_live_depth(canvas, first[0])
    assert _positions(canvas, first[0]) == positions
    assert _depths(canvas, first[0]) == depths
    assert scene_item_state_for(canvas, mark) == mark_before
    controller.end_selection_3d_rotation()
    after = documents.snapshot_state()
    after_cache = dict(atom_coords_3d_for(canvas))
    assert set(after["perspective"]["atom_coords_3d"]) == expected_cached_ids
    assert set(first[0]) <= expected_cached_ids
    assert len(history.state.history) == count + 1
    history.undo()
    assert documents.snapshot_state() == before
    assert atom_coords_3d_for(canvas) == before_cache
    assert scene_item_state_for(canvas, mark) == mark_before
    history.redo()
    assert documents.snapshot_state() == after
    assert atom_coords_3d_for(canvas) == after_cache
    assert scene_item_state_for(canvas, mark) == mark_before

    output = tmp_path / "two-molecules.chemvas"
    documents.save_to_file(str(output))
    documents.apply_state(read_document(output).state)
    assert documents.snapshot_state() == after
    assert atom_coords_3d_for(canvas) == after_cache
    _assert_live_depth(canvas, expected_cached_ids)


@pytest.mark.parametrize("axis", [False, True])
@pytest.mark.parametrize("previous_axis", [False, True])
def test_next_rotation_is_independent_of_other_component_rotation(
    canvas, axis, previous_axis
):
    first, second = _chains(canvas)
    _rotate(canvas, first)
    if previous_axis:
        _rotate(canvas, first, 40.0, axis=True)
    documents = canvas.services.document.canvas_document_session_service
    first_rotated = documents.snapshot_state()
    controller = _begin(canvas, first, axis=axis)
    expected_local_coords = dict(controller.rotation.base_coords)
    controller.update_selection_3d_rotation(-60.0, 0.0)
    controller.end_selection_3d_rotation()
    expected_positions = _positions(canvas, first[0])
    expected_depths = _depths(canvas, first[0])

    documents.apply_state(first_rotated)
    _rotate(canvas, second, 40.0)
    controller = _begin(canvas, first, axis=axis)
    # Stored XY is expressed in the current drawing camera, not a scientific
    # conformer. Compare the local rotation geometry after changing back to A.
    local_coords = controller.rotation.base_coords
    for a, b in combinations(expected_local_coords, 2):
        assert math.dist(local_coords[a], local_coords[b]) == pytest.approx(
            math.dist(expected_local_coords[a], expected_local_coords[b]), abs=1e-10
        )
    controller.update_selection_3d_rotation(-60.0, 0.0)
    controller.end_selection_3d_rotation()
    for aid in first[0]:
        assert _positions(canvas, first[0])[aid] == pytest.approx(
            expected_positions[aid], abs=1e-10
        )
        assert _depths(canvas, first[0])[aid] == pytest.approx(expected_depths[aid])
    _assert_live_depth(canvas, first[0] + second[0])


def test_reframing_failure_restores_existing_begin_savepoint(canvas):
    first, second = _chains(canvas)
    _rotate(canvas, first)
    documents = canvas.services.document.canvas_document_session_service
    before = documents.snapshot_state()
    before_cache = dict(atom_coords_3d_for(canvas))
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()

    def fail_after_reframing_one_atom(view, atom_id, coords):
        set_atom_coords_3d_for_id(view, atom_id, coords)
        if atom_id == first[0][0]:
            raise RuntimeError("failed reframe")

    with (
        mock.patch(
            "chemvas.ui.selection_rotation_session.set_atom_coords_3d_for_id",
            side_effect=fail_after_reframing_one_atom,
        ),
        pytest.raises(RuntimeError, match="failed reframe"),
    ):
        _begin(canvas, second)
    assert documents.snapshot_state() == before
    assert atom_coords_3d_for(canvas) == before_cache
    history.verify_stack_snapshot(stacks)
    _rotate(canvas, second, 40.0)
    _assert_live_depth(canvas, first[0] + second[0])


@pytest.mark.parametrize("ending", ["cancel", "no-motion", "push-false", "push-error"])
def test_cancel_or_failed_commit_restores_all_original_coordinates(canvas, ending):
    first, second = _chains(canvas)
    _rotate(canvas, first)
    documents = canvas.services.document.canvas_document_session_service
    before = documents.snapshot_state()
    before_cache = dict(atom_coords_3d_for(canvas))
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    controller = _begin(canvas, second)
    if ending != "no-motion":
        controller.update_selection_3d_rotation(40.0, 0.0)
    if ending == "cancel":
        controller.cancel_selection_3d_rotation()
    elif ending == "no-motion":
        controller.end_selection_3d_rotation()
    else:
        with (
            mock.patch.object(
                history,
                "push",
                return_value=False,
                side_effect=RuntimeError("failed push")
                if ending == "push-error"
                else None,
            ),
            pytest.raises(RuntimeError, match="failed push|did not commit"),
        ):
            controller.end_selection_3d_rotation()
    assert documents.snapshot_state() == before
    assert atom_coords_3d_for(canvas) == before_cache
    history.verify_stack_snapshot(stacks)


def test_reframing_does_not_heal_an_already_stale_coordinate(canvas):
    first, second = _chains(canvas)
    _rotate(canvas, first)
    aid = first[0][0]
    canvas.model.atoms[aid].x += 100.0
    stored = atom_coords_3d_for(canvas)[aid]
    previous_error = project_point_3d_for(canvas, stored)[0] - canvas.model.atoms[aid].x
    _rotate(canvas, second, 40.0)
    stored = atom_coords_3d_for(canvas)[aid]
    assert project_point_3d_for(canvas, stored)[0] - canvas.model.atoms[
        aid
    ].x == pytest.approx(previous_error)
    assert not stored_atom_coords_3d_matches_projection_for(canvas, aid, stored)
    assert current_atom_coords_3d_for(canvas, aid)[2] == 0.0
    _assert_live_depth(canvas, first[0][1:] + second[0])
