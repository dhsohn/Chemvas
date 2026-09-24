from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, kw_only=True)
class CanvasSpatialIndexState:
    dirty: bool = True
    cell_size: float = 0.0
    atom_grid: dict[tuple[int, int], set[int]] = field(default_factory=dict)
    bond_grid: dict[tuple[int, int], set[int]] = field(default_factory=dict)
    indexed_atom_count: int = -1
    indexed_bond_slot_count: int = -1


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
    state = canvas.runtime_state.spatial_index_state
    if state.dirty or abs(state.cell_size - cell_size) >= 1e-6:
        return False
    if atom_count is not None and state.indexed_atom_count != atom_count:
        return False
    return not (
        bond_slot_count is not None and state.indexed_bond_slot_count != bond_slot_count
    )


def set_spatial_index_for(
    canvas,
    *,
    atom_grid: dict[tuple[int, int], set[int]],
    bond_grid: dict[tuple[int, int], set[int]],
    cell_size: float,
    atom_count: int = -1,
    bond_slot_count: int = -1,
) -> None:
    state = canvas.runtime_state.spatial_index_state
    state.atom_grid = atom_grid
    state.bond_grid = bond_grid
    state.cell_size = cell_size
    state.indexed_atom_count = atom_count
    state.indexed_bond_slot_count = bond_slot_count
    state.dirty = False


def spatial_cell_size_or_for(canvas, fallback: float) -> float:
    return canvas.runtime_state.spatial_index_state.cell_size or fallback


def mark_spatial_index_dirty_for(canvas) -> None:
    state = canvas.runtime_state.spatial_index_state
    state.dirty = True


__all__ = [
    "CanvasSpatialIndexState",
    "has_fresh_spatial_index_for",
    "mark_spatial_index_dirty_for",
    "set_spatial_index_for",
    "spatial_cell_size_or_for",
]
