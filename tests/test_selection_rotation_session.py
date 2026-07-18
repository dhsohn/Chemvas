from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace
from unittest import mock

import pytest
from chemvas.ui import selection_rotation_session as rotation_session
from chemvas.ui.atom_coords_access import CanvasAtomCoords3DState
from chemvas.ui.canvas_rotation_state import CanvasRotationState
from chemvas.ui.selection_rotation_session import (
    begin_rigid_rotation_session,
    begin_selection_rotation_session,
    explicit_rotation_atom_ids_from_items,
)


class _Item:
    def __init__(self, kind: str, payload=None) -> None:
        self.kind = kind
        self.payload = payload

    def data(self, key: int):
        if key == 0:
            return self.kind
        if key == 1:
            return self.payload
        return None


class _RigidPorts:
    def __init__(self) -> None:
        self.canvas = SimpleNamespace(atom_coords_3d_state=CanvasAtomCoords3DState())
        self.atoms = {
            1: SimpleNamespace(x=0.0, y=0.0),
            2: SimpleNamespace(x=10.0, y=4.0),
        }
        self.current_coords = {
            1: (0.0, 0.0, 0.0),
            2: (10.0, 4.0, 2.0),
        }
        self.unproject_calls = []
        self.average_calls = []

    def atom(self, atom_id: int):
        return self.atoms.get(atom_id)

    def atom_positions(self, atom_ids: set[int]) -> dict[int, tuple[float, float]]:
        return {
            atom_id: (atom.x, atom.y)
            for atom_id in atom_ids
            for atom in [self.atom(atom_id)]
            if atom is not None
        }

    def current_atom_coords_3d(self, atom_id: int):
        return self.current_coords.get(atom_id)

    def flatten_planar_fragments(self, atom_ids, coords):
        return dict(coords)

    def average_bond_length_for_atoms(self, atom_ids, coords):
        self.average_calls.append((set(atom_ids), dict(coords)))
        return 8.0

    def unproject_scene_point_3d(self, point, z, *, center_3d, anchor_2d):
        self.unproject_calls.append(((point.x(), point.y()), z, center_3d, anchor_2d))
        return point.x() + 1.0, point.y() - 1.0, z + 0.5


class _SelectionPorts(_RigidPorts):
    def __init__(self) -> None:
        super().__init__()
        self.selected_atom_ids = {1, 2}
        self.selected_bond_ids: set[int] = set()
        self.bonds = [SimpleNamespace(a=1, b=2)]
        self.axis = None
        self.failure_stage: str | None = None
        self.failure: BaseException | None = None

    def _raise_at(self, stage: str) -> None:
        if self.failure_stage == stage and self.failure is not None:
            raise self.failure

    def selected_ids(self):
        self._raise_at("selected_ids")
        return set(self.selected_atom_ids), set(self.selected_bond_ids)

    def selected_scene_items(self):
        self._raise_at("selected_scene_items")
        return []

    def axis_from_rotation_hint(self, axis_hint, rotation_atom_ids, *, press_pos=None):
        del axis_hint, rotation_atom_ids, press_pos
        self._raise_at("axis")
        return self.axis

    def bond(self, bond_id: int):
        if 0 <= bond_id < len(self.bonds):
            return self.bonds[bond_id]
        return None

    def flatten_planar_fragments(self, atom_ids, coords):
        del atom_ids
        self._raise_at("flatten")
        return dict(coords)

    def atom_positions(self, atom_ids: set[int]) -> dict[int, tuple[float, float]]:
        self._raise_at("atom_positions")
        return super().atom_positions(atom_ids)

    def average_bond_length_for_atoms(self, atom_ids, coords):
        self._raise_at("average")
        return super().average_bond_length_for_atoms(atom_ids, coords)


def _rotation_prestate() -> tuple[CanvasRotationState, CanvasAtomCoords3DState]:
    selection_atom_ids = {701}
    selection_bond_ids = {702}
    state = CanvasRotationState(
        base_coords={700: (7.0, 8.0, 9.0)},
        axis_bond_id=700,
        axis_atoms=(700, 701),
        total_angle=1.25,
        mode="old-mode",
        free_angle_x=2.5,
        free_angle_y=3.5,
        base_bond_length=17.0,
        atom_ids={700, 701},
        center_3d=(10.0, 11.0, 12.0),
        projection_center_3d=(13.0, 14.0, 15.0),
        projection_anchor_2d=(16.0, 17.0),
        start_projection_center_3d=(18.0, 19.0, 20.0),
        start_projection_anchor_2d=(21.0, 22.0),
        start_positions={700: (23.0, 24.0)},
        start_coords_3d={700: (25.0, 26.0, 27.0)},
        coord_atom_ids={700},
        selection_ids=(selection_atom_ids, selection_bond_ids),
    )
    coords_state = CanvasAtomCoords3DState(atom_coords_3d={700: (28.0, 29.0, 30.0)})
    return state, coords_state


def _capture_exact_rotation_prestate(state, coords_state):
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    containers: dict[int, tuple[object, object]] = {}

    def capture(value: object) -> None:
        if isinstance(value, dict):
            if id(value) in containers:
                return
            containers[id(value)] = (value, tuple(value.items()))
            for key, item in value.items():
                capture(key)
                capture(item)
        elif isinstance(value, set):
            if id(value) in containers:
                return
            containers[id(value)] = (value, frozenset(value))
            for item in value:
                capture(item)
        elif isinstance(value, tuple):
            for item in value:
                capture(item)

    for value in values.values():
        capture(value)
    mapping = coords_state.atom_coords_3d
    capture(mapping)
    return values, tuple(containers.values()), mapping


def _assert_exact_rotation_prestate(
    state,
    coords_state,
    savepoint,
) -> None:
    values, containers, mapping = savepoint
    for name, value in values.items():
        assert getattr(state, name) is value
    for target, contents in containers:
        if isinstance(target, dict):
            assert tuple(target.items()) == contents
        else:
            assert isinstance(target, set)
            assert frozenset(target) == contents
    assert coords_state.atom_coords_3d is mapping


def test_explicit_rotation_atom_ids_from_items_promotes_valid_mark_targets_only() -> (
    None
):
    assert explicit_rotation_atom_ids_from_items(
        {1},
        [
            _Item("atom", {"atom_id": 2}),
            _Item("mark", {"atom_id": "bad"}),
            _Item("mark", {"atom_id": 3}),
            _Item("mark", None),
        ],
    ) == {1, 3}


def test_begin_rigid_rotation_session_populates_rotation_state_and_canvas_coords() -> (
    None
):
    ports = _RigidPorts()
    state = CanvasRotationState(
        projection_center_3d=(100.0, 200.0, 300.0),
        projection_anchor_2d=(40.0, 50.0),
    )

    rotating = begin_rigid_rotation_session(
        ports,
        state,
        rotation_atom_ids={1, 2},
        selection_ids=({1}, {7}),
        start_projection_center_3d=state.projection_center_3d,
        start_projection_anchor_2d=state.projection_anchor_2d,
    )

    assert rotating
    assert state.mode == "rigid"
    assert state.selection_ids == ({1}, {7})
    assert state.atom_ids == {1, 2}
    assert state.coord_atom_ids == {1, 2}
    assert state.start_coords_3d == {1: (0.0, 0.0, 0.0), 2: (10.0, 4.0, 2.0)}
    assert state.center_3d == (5.0, 2.0, 1.0)
    assert state.projection_center_3d == (5.0, 2.0, 1.0)
    assert state.projection_anchor_2d == (5.0, 2.0)
    assert state.start_projection_center_3d == (100.0, 200.0, 300.0)
    assert state.start_projection_anchor_2d == (40.0, 50.0)
    assert state.base_coords == {1: (1.0, -1.0, 0.5), 2: (11.0, 3.0, 2.5)}
    assert ports.canvas.atom_coords_3d_state.atom_coords_3d == state.base_coords
    assert ports.average_calls == [({1, 2}, dict(state.base_coords))]


def test_begin_selection_rotation_restores_exact_state_after_every_failure_stage() -> (
    None
):
    failure_cases = (
        ("selected_ids", SystemExit),
        ("selected_scene_items", KeyboardInterrupt),
        ("axis", SystemExit),
        ("flatten", KeyboardInterrupt),
        ("setter", SystemExit),
        ("atom_positions", KeyboardInterrupt),
        ("average", SystemExit),
    )
    for stage, error_type in failure_cases:
        ports = _SelectionPorts()
        state, coords_state = _rotation_prestate()
        ports.canvas.atom_coords_3d_state = coords_state
        savepoint = _capture_exact_rotation_prestate(state, coords_state)
        primary = error_type(f"{stage} interrupted")
        ports.failure_stage = stage
        ports.failure = primary
        axis_hint = 1 if stage == "axis" else None
        setter_patch = mock.patch.object(
            rotation_session,
            "set_atom_coords_3d_for_id",
            wraps=rotation_session.set_atom_coords_3d_for_id,
        )
        if stage == "setter":
            original_setter = rotation_session.set_atom_coords_3d_for_id
            calls = 0

            def mutate_then_interrupt(
                canvas,
                atom_id,
                coords,
                _setter=original_setter,
                _primary=primary,
            ) -> None:
                nonlocal calls
                calls += 1
                _setter(canvas, atom_id, coords)
                if calls == 1:
                    raise _primary

            setter_patch = mock.patch.object(
                rotation_session,
                "set_atom_coords_3d_for_id",
                side_effect=mutate_then_interrupt,
            )

        with setter_patch:
            with pytest.raises(error_type) as caught:
                begin_selection_rotation_session(
                    ports,
                    state,
                    axis_hint=axis_hint,
                )

        assert caught.value is primary
        _assert_exact_rotation_prestate(state, coords_state, savepoint)

        # The same state/coordinate objects remain valid for a clean retry.
        ports.failure_stage = None
        ports.failure = None
        assert begin_selection_rotation_session(ports, state)
        assert state.mode == "rigid"
        assert state.atom_ids == {1, 2}


def test_begin_selection_rotation_false_paths_restore_exact_state_and_retry() -> None:
    for scenario in (
        "empty_selection",
        "missing_atoms",
        "missing_coords",
        "missing_axis_bond",
        "empty_axis_coords",
    ):
        ports = _SelectionPorts()
        state, coords_state = _rotation_prestate()
        ports.canvas.atom_coords_3d_state = coords_state
        axis_hint = None
        if scenario == "empty_selection":
            ports.selected_atom_ids.clear()
        elif scenario == "missing_atoms":
            ports.atoms.clear()
        elif scenario == "missing_coords":
            ports.current_coords.clear()
        elif scenario == "missing_axis_bond":
            ports.axis = (0, {1})
            ports.bonds[:] = [None]
            axis_hint = 1
        else:
            ports.axis = (0, {1})
            ports.current_coords.clear()
            axis_hint = 1
        savepoint = _capture_exact_rotation_prestate(state, coords_state)

        assert not begin_selection_rotation_session(
            ports,
            state,
            axis_hint=axis_hint,
        )

        _assert_exact_rotation_prestate(state, coords_state, savepoint)

        ports.selected_atom_ids = {1, 2}
        ports.atoms = {
            1: SimpleNamespace(x=0.0, y=0.0),
            2: SimpleNamespace(x=10.0, y=4.0),
        }
        ports.current_coords = {
            1: (0.0, 0.0, 0.0),
            2: (10.0, 4.0, 2.0),
        }
        ports.bonds[:] = [SimpleNamespace(a=1, b=2)]
        assert begin_selection_rotation_session(
            ports,
            state,
            axis_hint=axis_hint,
        )


def test_false_rotation_begin_removes_lazily_created_3d_state_root() -> None:
    ports = _SelectionPorts()
    del ports.canvas.atom_coords_3d_state
    ports.selected_atom_ids.clear()
    state = CanvasRotationState()

    assert not begin_selection_rotation_session(ports, state)

    assert not hasattr(ports.canvas, "atom_coords_3d_state")
    assert not hasattr(ports.canvas, "model")


def test_begin_rotation_restores_replaced_3d_state_root_before_retry() -> None:
    ports = _SelectionPorts()
    state, coords_state = _rotation_prestate()
    ports.canvas.atom_coords_3d_state = coords_state
    coords_mapping = coords_state.atom_coords_3d
    replacement = CanvasAtomCoords3DState(atom_coords_3d={1: (99.0, 99.0, 99.0)})
    primary = KeyboardInterrupt("flatten replaced 3D state root")

    def replace_root_then_fail(_atom_ids, _coords):
        ports.canvas.atom_coords_3d_state = replacement
        coords_mapping[999] = (9.0, 9.0, 9.0)
        raise primary

    ports.flatten_planar_fragments = replace_root_then_fail

    with pytest.raises(KeyboardInterrupt) as caught:
        begin_selection_rotation_session(ports, state)

    assert caught.value is primary
    assert ports.canvas.atom_coords_3d_state is coords_state
    assert coords_state.atom_coords_3d is coords_mapping
    assert coords_mapping == {700: (28.0, 29.0, 30.0)}

    ports.flatten_planar_fragments = lambda _atom_ids, coords: dict(coords)
    assert begin_selection_rotation_session(ports, state)
