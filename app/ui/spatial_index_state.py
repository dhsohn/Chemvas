from __future__ import annotations

from dataclasses import dataclass, field

from ui.canvas_state_lookup import canvas_state_object


@dataclass(slots=True)
class CanvasSpatialIndexState:
    dirty: bool = True
    cell_size: float = 0.0
    atom_grid: dict[tuple[int, int], set[int]] = field(default_factory=dict)
    bond_grid: dict[tuple[int, int], set[int]] = field(default_factory=dict)


def spatial_index_state_for(canvas) -> CanvasSpatialIndexState:
    state = canvas_state_object(canvas, "spatial_index_state")
    if state is not None:
        return state
    state = CanvasSpatialIndexState()
    canvas.spatial_index_state = state
    return state


def has_fresh_spatial_index_for(canvas, cell_size: float) -> bool:
    state = spatial_index_state_for(canvas)
    return not state.dirty and abs(state.cell_size - cell_size) < 1e-6


def set_spatial_index_for(
    canvas,
    *,
    atom_grid: dict[tuple[int, int], set[int]],
    bond_grid: dict[tuple[int, int], set[int]],
    cell_size: float,
) -> None:
    state = spatial_index_state_for(canvas)
    state.atom_grid = atom_grid
    state.bond_grid = bond_grid
    state.cell_size = cell_size
    state.dirty = False


def spatial_cell_size_or_for(canvas, fallback: float) -> float:
    return spatial_index_state_for(canvas).cell_size or fallback


def atom_ids_in_spatial_cell_for(canvas, cell: tuple[int, int]):
    return spatial_index_state_for(canvas).atom_grid.get(cell, ())


def bond_ids_in_spatial_cell_for(canvas, cell: tuple[int, int]):
    return spatial_index_state_for(canvas).bond_grid.get(cell, ())


def mark_spatial_index_dirty_for(canvas) -> None:
    state = spatial_index_state_for(canvas)
    state.dirty = True


__all__ = [
    "CanvasSpatialIndexState",
    "atom_ids_in_spatial_cell_for",
    "bond_ids_in_spatial_cell_for",
    "has_fresh_spatial_index_for",
    "mark_spatial_index_dirty_for",
    "set_spatial_index_for",
    "spatial_cell_size_or_for",
    "spatial_index_state_for",
]
