from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


Coords3D = tuple[float, float, float]
Point2D = tuple[float, float]


@dataclass(slots=True)
class CanvasRotationState:
    base_coords: dict[int, Coords3D] = field(default_factory=dict)
    axis_bond_id: int | None = None
    axis_atoms: tuple[int, int] | None = None
    total_angle: float = 0.0
    mode: str | None = None
    free_angle_x: float = 0.0
    free_angle_y: float = 0.0
    base_bond_length: float | None = None
    atom_ids: set[int] = field(default_factory=set)
    center_3d: Coords3D | None = None
    projection_center_3d: Coords3D | None = None
    projection_anchor_2d: Point2D | None = None
    start_projection_center_3d: Coords3D | None = None
    start_projection_anchor_2d: Point2D | None = None
    start_positions: dict[int, Point2D] = field(default_factory=dict)
    start_coords_3d: dict[int, Coords3D] = field(default_factory=dict)
    coord_atom_ids: set[int] = field(default_factory=set)
    selection_ids: tuple[set[int], set[int]] | None = None

    def clear_session(self) -> None:
        self.base_coords = {}
        self.axis_bond_id = None
        self.axis_atoms = None
        self.total_angle = 0.0
        self.mode = None
        self.free_angle_x = 0.0
        self.free_angle_y = 0.0
        self.base_bond_length = None
        self.atom_ids = set()
        self.center_3d = None
        self.start_projection_center_3d = None
        self.start_projection_anchor_2d = None
        self.start_positions = {}
        self.start_coords_3d = {}
        self.coord_atom_ids = set()
        self.selection_ids = None

    def reset_all(self) -> None:
        self.clear_session()
        self.projection_center_3d = None
        self.projection_anchor_2d = None


class CanvasRotationStateAdapter:
    """Compatibility adapter for tests and legacy callers that still expose canvas fields."""

    def __init__(self, canvas: Any) -> None:
        self._canvas = canvas

    def _ensure(self, name: str, default):
        if not hasattr(self._canvas, name):
            setattr(self._canvas, name, default() if callable(default) else default)
        return getattr(self._canvas, name)

    @property
    def base_coords(self) -> dict[int, Coords3D]:
        return self._ensure("_rotation_base_coords", dict)

    @base_coords.setter
    def base_coords(self, value: dict[int, Coords3D]) -> None:
        self._canvas._rotation_base_coords = value

    @property
    def axis_bond_id(self) -> int | None:
        return self._ensure("_rotation_axis_bond_id", None)

    @axis_bond_id.setter
    def axis_bond_id(self, value: int | None) -> None:
        self._canvas._rotation_axis_bond_id = value

    @property
    def axis_atoms(self) -> tuple[int, int] | None:
        return self._ensure("_rotation_axis_atoms", None)

    @axis_atoms.setter
    def axis_atoms(self, value: tuple[int, int] | None) -> None:
        self._canvas._rotation_axis_atoms = value

    @property
    def total_angle(self) -> float:
        return self._ensure("_rotation_total_angle", 0.0)

    @total_angle.setter
    def total_angle(self, value: float) -> None:
        self._canvas._rotation_total_angle = value

    @property
    def mode(self) -> str | None:
        return self._ensure("_rotation_mode", None)

    @mode.setter
    def mode(self, value: str | None) -> None:
        self._canvas._rotation_mode = value

    @property
    def free_angle_x(self) -> float:
        return self._ensure("_rotation_free_angle_x", 0.0)

    @free_angle_x.setter
    def free_angle_x(self, value: float) -> None:
        self._canvas._rotation_free_angle_x = value

    @property
    def free_angle_y(self) -> float:
        return self._ensure("_rotation_free_angle_y", 0.0)

    @free_angle_y.setter
    def free_angle_y(self, value: float) -> None:
        self._canvas._rotation_free_angle_y = value

    @property
    def base_bond_length(self) -> float | None:
        return self._ensure("_rotation_base_bond_length", None)

    @base_bond_length.setter
    def base_bond_length(self, value: float | None) -> None:
        self._canvas._rotation_base_bond_length = value

    @property
    def atom_ids(self) -> set[int]:
        return self._ensure("rotation_atom_ids", set)

    @atom_ids.setter
    def atom_ids(self, value: set[int]) -> None:
        self._canvas.rotation_atom_ids = value

    @property
    def center_3d(self) -> Coords3D | None:
        return self._ensure("rotation_center_3d", None)

    @center_3d.setter
    def center_3d(self, value: Coords3D | None) -> None:
        self._canvas.rotation_center_3d = value

    @property
    def projection_center_3d(self) -> Coords3D | None:
        return self._ensure("_projection_center_3d", None)

    @projection_center_3d.setter
    def projection_center_3d(self, value: Coords3D | None) -> None:
        self._canvas._projection_center_3d = value

    @property
    def projection_anchor_2d(self) -> Point2D | None:
        return self._ensure("_projection_anchor_2d", None)

    @projection_anchor_2d.setter
    def projection_anchor_2d(self, value: Point2D | None) -> None:
        self._canvas._projection_anchor_2d = value

    @property
    def start_projection_center_3d(self) -> Coords3D | None:
        return self._ensure("_rotation_start_projection_center_3d", None)

    @start_projection_center_3d.setter
    def start_projection_center_3d(self, value: Coords3D | None) -> None:
        self._canvas._rotation_start_projection_center_3d = value

    @property
    def start_projection_anchor_2d(self) -> Point2D | None:
        return self._ensure("_rotation_start_projection_anchor_2d", None)

    @start_projection_anchor_2d.setter
    def start_projection_anchor_2d(self, value: Point2D | None) -> None:
        self._canvas._rotation_start_projection_anchor_2d = value

    @property
    def start_positions(self) -> dict[int, Point2D]:
        return self._ensure("_rotation_start_positions", dict)

    @start_positions.setter
    def start_positions(self, value: dict[int, Point2D]) -> None:
        self._canvas._rotation_start_positions = value

    @property
    def start_coords_3d(self) -> dict[int, Coords3D]:
        return self._ensure("_rotation_start_coords_3d", dict)

    @start_coords_3d.setter
    def start_coords_3d(self, value: dict[int, Coords3D]) -> None:
        self._canvas._rotation_start_coords_3d = value

    @property
    def coord_atom_ids(self) -> set[int]:
        return self._ensure("_rotation_coord_atom_ids", set)

    @coord_atom_ids.setter
    def coord_atom_ids(self, value: set[int]) -> None:
        self._canvas._rotation_coord_atom_ids = value

    @property
    def selection_ids(self) -> tuple[set[int], set[int]] | None:
        return self._ensure("_rotation_selection_ids", None)

    @selection_ids.setter
    def selection_ids(self, value: tuple[set[int], set[int]] | None) -> None:
        self._canvas._rotation_selection_ids = value

    def clear_session(self) -> None:
        self.base_coords = {}
        self.axis_bond_id = None
        self.axis_atoms = None
        self.total_angle = 0.0
        self.mode = None
        self.free_angle_x = 0.0
        self.free_angle_y = 0.0
        self.base_bond_length = None
        self.atom_ids = set()
        self.center_3d = None
        self.start_projection_center_3d = None
        self.start_projection_anchor_2d = None
        self.start_positions = {}
        self.start_coords_3d = {}
        self.coord_atom_ids = set()
        self.selection_ids = None

    def reset_all(self) -> None:
        self.clear_session()
        self.projection_center_3d = None
        self.projection_anchor_2d = None


def rotation_state_for(canvas: Any) -> CanvasRotationState | CanvasRotationStateAdapter:
    state = getattr(canvas, "_rotation_state", None)
    if state is not None:
        return state
    return CanvasRotationStateAdapter(canvas)


__all__ = ["CanvasRotationState", "CanvasRotationStateAdapter", "rotation_state_for"]
