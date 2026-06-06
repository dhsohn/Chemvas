from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ui.canvas_state_lookup import canvas_state_object


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


def graph_state_for(canvas: Any) -> CanvasGraphState:
    state = canvas_state_object(canvas, "graph_state")
    if state is not None:
        return state
    state = CanvasGraphState()
    canvas.graph_state = state
    return state


__all__ = ["CanvasGraphState", "graph_state_for"]
