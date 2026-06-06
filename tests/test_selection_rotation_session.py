from __future__ import annotations

from types import SimpleNamespace

from ui.atom_coords_access import CanvasAtomCoords3DState
from ui.canvas_rotation_state import CanvasRotationState
from ui.selection_rotation_session import (
    begin_rigid_rotation_session,
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


def test_explicit_rotation_atom_ids_from_items_promotes_valid_mark_targets_only() -> None:
    assert explicit_rotation_atom_ids_from_items(
        {1},
        [
            _Item("atom", {"atom_id": 2}),
            _Item("mark", {"atom_id": "bad"}),
            _Item("mark", {"atom_id": 3}),
            _Item("mark", None),
        ],
    ) == {1, 3}


def test_begin_rigid_rotation_session_populates_rotation_state_and_canvas_coords() -> None:
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
