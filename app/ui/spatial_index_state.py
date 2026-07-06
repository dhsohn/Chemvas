from __future__ import annotations

from dataclasses import dataclass, field

from ui.canvas_state_lookup import ensure_canvas_state


@dataclass(slots=True)
class CanvasSpatialIndexState:
    dirty: bool = True
    cell_size: float = 0.0
    atom_grid: dict[tuple[int, int], set[int]] = field(default_factory=dict)
    bond_grid: dict[tuple[int, int], set[int]] = field(default_factory=dict)
    indexed_atom_count: int = -1
    indexed_bond_slot_count: int = -1


def spatial_index_state_for(canvas) -> CanvasSpatialIndexState:
    return ensure_canvas_state(canvas, "spatial_index_state", CanvasSpatialIndexState)


def has_fresh_spatial_index_for(
    canvas,
    cell_size: float,
    *,
    atom_count: int | None = None,
    bond_slot_count: int | None = None,
) -> bool:
    """True when the index can be trusted for the current model.

    The dirty flag relies on every mutation path calling
    ``mark_spatial_index_dirty_for``; the count comparison is a cheap
    self-heal that catches a missed mark whenever atoms or bond slots were
    added or removed (coordinate-only drift still needs the flag).
    """
    state = spatial_index_state_for(canvas)
    if state.dirty or abs(state.cell_size - cell_size) >= 1e-6:
        return False
    if atom_count is not None and state.indexed_atom_count != atom_count:
        return False
    return not (bond_slot_count is not None and state.indexed_bond_slot_count != bond_slot_count)


def set_spatial_index_for(
    canvas,
    *,
    atom_grid: dict[tuple[int, int], set[int]],
    bond_grid: dict[tuple[int, int], set[int]],
    cell_size: float,
    atom_count: int = -1,
    bond_slot_count: int = -1,
) -> None:
    state = spatial_index_state_for(canvas)
    state.atom_grid = atom_grid
    state.bond_grid = bond_grid
    state.cell_size = cell_size
    state.indexed_atom_count = atom_count
    state.indexed_bond_slot_count = bond_slot_count
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
