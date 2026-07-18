from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chemvas.ui.canvas_state_lookup import ensure_canvas_state

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


def rotation_state_for(canvas: Any) -> CanvasRotationState:
    return ensure_canvas_state(canvas, "rotation_state", CanvasRotationState)


__all__ = ["CanvasRotationState", "rotation_state_for"]
