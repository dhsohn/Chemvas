from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CanvasGraphState:
    atom_neighbors: dict[int, set[int]] = field(default_factory=dict)
    atom_bond_ids: dict[int, set[int]] = field(default_factory=dict)
    graph_version: int = 0
    selection_component_cache_signature: tuple[frozenset[int], int] | None = None
    selection_component_cache: list[set[int]] = field(default_factory=list)
    rotation_axis_cache: dict[tuple[frozenset[int], frozenset[int], int], tuple[int, set[int]] | None] = field(
        default_factory=dict
    )
    rotation_axis_cache_version: int = 0
    bond_cycle_cache: dict[int, tuple[int, bool]] = field(default_factory=dict)

    def bump_version(self) -> None:
        self.graph_version += 1
        self.selection_component_cache_signature = None

    def reset(self) -> None:
        self.atom_neighbors = {}
        self.atom_bond_ids = {}
        self.graph_version = 0
        self.selection_component_cache_signature = None
        self.selection_component_cache = []
        self.rotation_axis_cache = {}
        self.rotation_axis_cache_version = 0
        self.bond_cycle_cache = {}


class CanvasGraphStateAdapter:
    """Compatibility adapter for tests and legacy callers that still expose canvas fields."""

    def __init__(self, canvas: Any) -> None:
        self._canvas = canvas

    def _ensure(self, name: str, default):
        if not hasattr(self._canvas, name):
            setattr(self._canvas, name, default() if callable(default) else default)
        return getattr(self._canvas, name)

    @property
    def atom_neighbors(self) -> dict[int, set[int]]:
        return self._ensure("_atom_neighbors", dict)

    @atom_neighbors.setter
    def atom_neighbors(self, value: dict[int, set[int]]) -> None:
        self._canvas._atom_neighbors = value

    @property
    def atom_bond_ids(self) -> dict[int, set[int]]:
        return self._ensure("_atom_bond_ids", dict)

    @atom_bond_ids.setter
    def atom_bond_ids(self, value: dict[int, set[int]]) -> None:
        self._canvas._atom_bond_ids = value

    @property
    def graph_version(self) -> int:
        return self._ensure("_graph_version", 0)

    @graph_version.setter
    def graph_version(self, value: int) -> None:
        self._canvas._graph_version = value

    @property
    def selection_component_cache_signature(self) -> tuple[frozenset[int], int] | None:
        return self._ensure("_selection_component_cache_signature", None)

    @selection_component_cache_signature.setter
    def selection_component_cache_signature(self, value: tuple[frozenset[int], int] | None) -> None:
        self._canvas._selection_component_cache_signature = value

    @property
    def selection_component_cache(self) -> list[set[int]]:
        return self._ensure("_selection_component_cache", list)

    @selection_component_cache.setter
    def selection_component_cache(self, value: list[set[int]]) -> None:
        self._canvas._selection_component_cache = value

    @property
    def rotation_axis_cache(self) -> dict[tuple[frozenset[int], frozenset[int], int], tuple[int, set[int]] | None]:
        return self._ensure("_rotation_axis_cache", dict)

    @rotation_axis_cache.setter
    def rotation_axis_cache(
        self,
        value: dict[tuple[frozenset[int], frozenset[int], int], tuple[int, set[int]] | None],
    ) -> None:
        self._canvas._rotation_axis_cache = value

    @property
    def rotation_axis_cache_version(self) -> int:
        return self._ensure("_rotation_axis_cache_version", self.graph_version)

    @rotation_axis_cache_version.setter
    def rotation_axis_cache_version(self, value: int) -> None:
        self._canvas._rotation_axis_cache_version = value

    @property
    def bond_cycle_cache(self) -> dict[int, tuple[int, bool]]:
        return self._ensure("_bond_cycle_cache", dict)

    @bond_cycle_cache.setter
    def bond_cycle_cache(self, value: dict[int, tuple[int, bool]]) -> None:
        self._canvas._bond_cycle_cache = value

    def bump_version(self) -> None:
        self.graph_version = self.graph_version + 1
        self.selection_component_cache_signature = None

    def reset(self) -> None:
        self.atom_neighbors = {}
        self.atom_bond_ids = {}
        self.graph_version = 0
        self.selection_component_cache_signature = None
        self.selection_component_cache = []
        self.rotation_axis_cache = {}
        self.rotation_axis_cache_version = 0
        self.bond_cycle_cache = {}


def graph_state_for(canvas: Any) -> CanvasGraphState | CanvasGraphStateAdapter:
    state = getattr(canvas, "_graph_state", None)
    if state is not None:
        return state
    return CanvasGraphStateAdapter(canvas)


__all__ = ["CanvasGraphState", "CanvasGraphStateAdapter", "graph_state_for"]
