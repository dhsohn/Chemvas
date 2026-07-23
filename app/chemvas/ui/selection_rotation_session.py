from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any

from PyQt6.QtCore import QPointF

from chemvas.features.selection import (
    bounding_box_center_for_atoms,
    selected_rotation_atom_ids,
)
from chemvas.ui.atom_coords_access import (
    atom_coords_3d_for,
    set_atom_coords_3d_for,
    set_atom_coords_3d_for_id,
)
from chemvas.ui.canvas_rotation_state import CanvasRotationState

Coords2D = tuple[float, float]
Coords3D = tuple[float, float, float]


def _copied_state_value(value: object) -> object:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, set):
        return set(value)
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], set):
        return (set(value[0]), set(value[1]))
    return value


@dataclass(slots=True)
class _SelectionRotationBeginSnapshot:
    """Begin-phase savepoint: rotation-state fields and 3D coordinates.

    Beginning a rotation writes flattened 3D coordinates into the document
    and republishes the rotation-state fields; a failed begin restores both.
    """

    canvas: object
    state: CanvasRotationState
    state_fields: dict[str, object]
    coords_3d: dict[int, Coords3D]

    @classmethod
    def capture(
        cls,
        canvas,
        state: CanvasRotationState,
    ) -> _SelectionRotationBeginSnapshot:
        return cls(
            canvas=canvas,
            state=state,
            state_fields={
                state_field.name: _copied_state_value(getattr(state, state_field.name))
                for state_field in fields(state)
            },
            coords_3d=dict(atom_coords_3d_for(canvas)),
        )

    def restore(self) -> None:
        for name, value in self.state_fields.items():
            setattr(self.state, name, _copied_state_value(value))
        set_atom_coords_3d_for(self.canvas, dict(self.coords_3d))


def _add_rotation_begin_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                "Selection-rotation begin rollback also encountered "
                f"{type(rollback_error).__name__}: {rollback_error}"
            )
    except BaseException:
        return


def explicit_rotation_atom_ids_from_items(
    atom_ids: set[int], selected_items
) -> set[int]:
    explicit_atom_ids = set(atom_ids)
    for item in selected_items:
        if item.data(0) != "mark":
            continue
        data = item.data(1) or {}
        atom_id = data.get("atom_id")
        if isinstance(atom_id, int):
            explicit_atom_ids.add(atom_id)
    return explicit_atom_ids


def begin_axis_rotation_session(
    ports: Any,
    state: CanvasRotationState,
    *,
    bond_id: int,
    rotate_ids: set[int],
    selection_ids: tuple[set[int], set[int]],
    start_projection_center_3d: Coords3D | None,
    start_projection_anchor_2d: Coords2D | None,
) -> bool:
    bond = ports.bond(bond_id)
    if bond is None:
        return False
    axis_a = bond.a
    axis_b = bond.b
    state.selection_ids = (set(selection_ids[0]), set(selection_ids[1]))
    state.base_coords = {}
    for atom_id in rotate_ids | {axis_a, axis_b}:
        coords = ports.current_atom_coords_3d(atom_id)
        if coords is None:
            continue
        state.base_coords[atom_id] = coords
        state.start_coords_3d[atom_id] = coords
    relevant_atom_ids = rotate_ids | {axis_a, axis_b}
    state.coord_atom_ids = set(state.base_coords)
    state.base_coords = ports.flatten_planar_fragments(
        relevant_atom_ids, state.base_coords
    )
    for atom_id in relevant_atom_ids:
        coords = state.base_coords.get(atom_id)
        if coords is not None:
            set_atom_coords_3d_for_id(ports.canvas, atom_id, coords)
    if not state.base_coords:
        return False
    axis_center = (
        (state.base_coords[axis_a][0] + state.base_coords[axis_b][0]) * 0.5,
        (state.base_coords[axis_a][1] + state.base_coords[axis_b][1]) * 0.5,
        (state.base_coords[axis_a][2] + state.base_coords[axis_b][2]) * 0.5,
    )
    state.axis_bond_id = bond_id
    state.axis_atoms = (axis_a, axis_b)
    state.total_angle = 0.0
    state.mode = "bond"
    state.free_angle_x = 0.0
    state.free_angle_y = 0.0
    state.atom_ids = set(rotate_ids)
    state.start_positions = ports.atom_positions(state.atom_ids)
    state.center_3d = axis_center
    state.projection_center_3d = state.center_3d
    atom_a = ports.atom(axis_a)
    atom_b = ports.atom(axis_b)
    if atom_a is not None and atom_b is not None:
        state.projection_anchor_2d = (
            (atom_a.x + atom_b.x) * 0.5,
            (atom_a.y + atom_b.y) * 0.5,
        )
    else:
        state.projection_anchor_2d = (axis_center[0], axis_center[1])
    state.start_projection_center_3d = start_projection_center_3d
    state.start_projection_anchor_2d = start_projection_anchor_2d
    scale_atom_ids = set(state.atom_ids)
    scale_atom_ids.update((axis_a, axis_b))
    state.base_bond_length = ports.average_bond_length_for_atoms(
        scale_atom_ids, state.base_coords
    )
    return True


def begin_rigid_rotation_session(
    ports: Any,
    state: CanvasRotationState,
    *,
    rotation_atom_ids: set[int],
    selection_ids: tuple[set[int], set[int]],
    start_projection_center_3d: Coords3D | None,
    start_projection_anchor_2d: Coords2D | None,
) -> bool:
    state.selection_ids = (set(selection_ids[0]), set(selection_ids[1]))
    screen_center = bounding_box_center_for_atoms(rotation_atom_ids, atoms=ports.atoms)
    if screen_center is None:
        return False
    anchor_2d = (screen_center.x(), screen_center.y())
    raw_coords: dict[int, Coords3D] = {}
    for atom_id in rotation_atom_ids:
        coords = ports.current_atom_coords_3d(atom_id)
        if coords is None:
            continue
        raw_coords[atom_id] = coords
    if not raw_coords:
        return False
    state.start_coords_3d = dict(raw_coords)
    state.coord_atom_ids = set(raw_coords)
    center_z = sum(coords[2] for coords in raw_coords.values()) / len(raw_coords)
    center = (screen_center.x(), screen_center.y(), center_z)
    state.base_coords = {}
    for atom_id, coords in raw_coords.items():
        atom = ports.atom(atom_id)
        if atom is None:
            continue
        state.base_coords[atom_id] = ports.unproject_scene_point_3d(
            QPointF(atom.x, atom.y),
            coords[2],
            center_3d=center,
            anchor_2d=anchor_2d,
        )
    state.base_coords = ports.flatten_planar_fragments(
        rotation_atom_ids, state.base_coords
    )
    for atom_id, coords in state.base_coords.items():
        set_atom_coords_3d_for_id(ports.canvas, atom_id, coords)
    state.axis_bond_id = None
    state.axis_atoms = None
    state.total_angle = 0.0
    state.mode = "rigid"
    state.free_angle_x = 0.0
    state.free_angle_y = 0.0
    state.atom_ids = set(rotation_atom_ids)
    state.start_positions = ports.atom_positions(state.atom_ids)
    state.center_3d = center
    state.projection_center_3d = center
    state.projection_anchor_2d = anchor_2d
    state.start_projection_center_3d = start_projection_center_3d
    state.start_projection_anchor_2d = start_projection_anchor_2d
    state.base_bond_length = ports.average_bond_length_for_atoms(
        set(state.atom_ids), state.base_coords
    )
    return True


def begin_selection_rotation_session(
    ports: Any,
    state: CanvasRotationState,
    *,
    axis_hint: int | None = None,
    press_pos: QPointF | None = None,
    on_session_started: Callable[[], None] | None = None,
) -> bool:
    snapshot = _SelectionRotationBeginSnapshot.capture(ports.canvas, state)
    try:
        start_projection_center_3d = state.projection_center_3d
        start_projection_anchor_2d = state.projection_anchor_2d
        atom_ids, bond_ids = ports.selected_ids()
        explicit_atom_ids = explicit_rotation_atom_ids_from_items(
            atom_ids,
            ports.selected_scene_items(),
        )
        rotation_atom_ids = selected_rotation_atom_ids(
            explicit_atom_ids,
            bond_ids,
            bonds=ports.bonds,
        )
        axis = None
        if isinstance(axis_hint, int) and (rotation_atom_ids or bond_ids):
            axis = ports.axis_from_rotation_hint(
                axis_hint,
                rotation_atom_ids,
                press_pos=press_pos,
            )
        if not rotation_atom_ids and not bond_ids:
            rotating = False
        else:
            # Publish a fresh session only after every selection/axis preflight
            # above has completed. The remaining geometry reads and per-atom
            # writes are protected by the exact savepoint.
            state.start_coords_3d = {}
            state.coord_atom_ids = set()
            selection_ids = (set(atom_ids), set(bond_ids))
            if axis is not None:
                bond_id, rotate_ids = axis
                rotating = begin_axis_rotation_session(
                    ports,
                    state,
                    bond_id=bond_id,
                    rotate_ids=rotate_ids,
                    selection_ids=selection_ids,
                    start_projection_center_3d=start_projection_center_3d,
                    start_projection_anchor_2d=start_projection_anchor_2d,
                )
            else:
                rotating = begin_rigid_rotation_session(
                    ports,
                    state,
                    rotation_atom_ids=rotation_atom_ids,
                    selection_ids=selection_ids,
                    start_projection_center_3d=start_projection_center_3d,
                    start_projection_anchor_2d=start_projection_anchor_2d,
                )
        if rotating and on_session_started is not None:
            # The callback publishes the gesture guard. It runs inside the
            # begin savepoint so a failed publication cannot strand a
            # partially published rotation.
            on_session_started()
    except BaseException as original_error:
        try:
            snapshot.restore()
        except BaseException as rollback_error:
            _add_rotation_begin_rollback_note(original_error, rollback_error)
        raise
    if rotating:
        return True
    snapshot.restore()
    return False


__all__ = [
    "begin_axis_rotation_session",
    "begin_rigid_rotation_session",
    "begin_selection_rotation_session",
    "explicit_rotation_atom_ids_from_items",
]
