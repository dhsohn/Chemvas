from __future__ import annotations

from types import SimpleNamespace

from core.model import Bond
from ui.canvas_graph_state import CanvasGraphState
from ui.selection_rotation_planarity import (
    bond_in_cycle_for,
    flatten_planar_fragments_for,
)


def test_bond_in_cycle_for_caches_result_until_graph_version_changes() -> None:
    canvas = SimpleNamespace(
        model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
        graph_state=CanvasGraphState(
            atom_neighbors={1: {2, 3}, 2: {1, 3}, 3: {1, 2}},
            atom_bond_ids={1: {0}, 2: {0}, 3: set()},
            graph_version=4,
        ),
    )

    assert bond_in_cycle_for(canvas, 0)
    assert canvas.graph_state.bond_cycle_cache[0] == (4, True)

    canvas.graph_state.atom_neighbors = {1: {2}, 2: {1}}
    assert bond_in_cycle_for(canvas, 0)

    canvas.graph_state.graph_version = 5
    assert not bond_in_cycle_for(canvas, 0)
    assert canvas.graph_state.bond_cycle_cache[0] == (5, False)


def test_flatten_planar_fragments_for_preserves_coords_without_selected_atoms() -> None:
    coords = {1: (1.0, 2.0, 3.0)}

    assert flatten_planar_fragments_for(SimpleNamespace(), set(), coords) == coords
    assert flatten_planar_fragments_for(SimpleNamespace(), set(), coords) is not coords
