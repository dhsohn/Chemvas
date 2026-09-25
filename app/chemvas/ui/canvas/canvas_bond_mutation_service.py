from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.domain.document import Bond
from chemvas.ui.canvas.canvas_bond_graphics_state import pop_bond_items_for
from chemvas.ui.scene.scene_item_access import remove_items_from_canvas_scene

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.ui.canvas.canvas_view import CanvasView


class CanvasBondMutationService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        hit_testing_service,
        graph_service,
        atom_label_relayout: Callable[[set[int], set[int]], None],
    ) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.graph_service = graph_service
        self._atom_label_relayout = atom_label_relayout

    def add_bond(self, a: int, b: int, order: int = 1) -> int:
        graph_service = self.graph_service
        # This is the one write site where a stale index entry would let a
        # duplicate bond into the model and poison every later save, so use
        # the graph service's self-repairing lookup instead of the fast path.
        existing_id = graph_service.bond_id_between_with_repair(a, b)
        if existing_id is not None:
            return existing_id
        bond_id = self.canvas.model.add_bond(a, b, order)
        graph_service.add_bond_neighbors(a, b)
        graph_service.add_bond_index(bond_id, a, b)
        self._relayout_atom_labels(
            {a, b}, refresh_ring_bonds=graph_service.bond_in_cycle(bond_id)
        )
        self.hit_testing_service.mark_spatial_index_dirty()
        return bond_id

    def restore_bond_from_state(self, bond_id: int, bond_state: dict) -> None:
        if not bond_state:
            return
        graph_service = self.graph_service
        existing_bond = self.canvas.model.bond_for_id(bond_id)
        bond = Bond(
            a=bond_state.get("a", 0),
            b=bond_state.get("b", 0),
            order=bond_state.get("order", 1),
            style=bond_state.get("style", "single"),
            color=bond_state.get("color", "#000000"),
        )
        old_atom_ids = (
            {existing_bond.a, existing_bond.b} if existing_bond is not None else set()
        )
        topology_changed = existing_bond is None or old_atom_ids != {bond.a, bond.b}
        refresh_rings = (
            existing_bond is not None
            and topology_changed
            and graph_service.bond_in_cycle(bond_id)
        )
        if existing_bond is not None and (
            existing_bond.a != bond.a or existing_bond.b != bond.b
        ):
            graph_service.remove_bond_index(bond_id, existing_bond.a, existing_bond.b)
            graph_service.remove_bond_neighbors(
                existing_bond.a, existing_bond.b, skip_bond_id=bond_id
            )
        self.canvas.model.set_bond(bond_id, bond)
        if existing_bond is None or (
            existing_bond.a != bond.a or existing_bond.b != bond.b
        ):
            graph_service.add_bond_neighbors(bond.a, bond.b)
            graph_service.add_bond_index(bond_id, bond.a, bond.b)
        # Reuse the forward-edit refresh: it transfers the live selected flag
        # before discarding old graphics. Chemistry exports consume that flag.
        self.canvas.bond_renderer.redraw_bond(bond_id)
        if topology_changed:
            refresh_rings = graph_service.bond_in_cycle(bond_id) or refresh_rings
        self._relayout_atom_labels(
            old_atom_ids | {bond.a, bond.b}, refresh_ring_bonds=refresh_rings
        )
        self.hit_testing_service.mark_spatial_index_dirty()

    def remove_bond_by_id(self, bond_id: int) -> None:
        if not self.canvas.model.has_bond_slot(bond_id):
            return
        bond = self.canvas.model.bond_for_id(bond_id)
        refresh_rings = bond is not None and self.graph_service.bond_in_cycle(bond_id)
        self._clear_bond_graphics(bond_id)
        if bond is not None:
            graph_service = self.graph_service
            graph_service.remove_bond_index(bond_id, bond.a, bond.b)
            graph_service.remove_bond_neighbors(bond.a, bond.b, skip_bond_id=bond_id)
        self.canvas.model.clear_bond(bond_id)
        if bond is not None:
            self._relayout_atom_labels(
                {bond.a, bond.b}, refresh_ring_bonds=refresh_rings
            )
        self.hit_testing_service.mark_spatial_index_dirty()

    def trim_bonds_to_length(self, length: int) -> None:
        if length < 0 or length >= len(self.canvas.model.bonds):
            return
        graph_service = self.graph_service
        trimmed_bonds = [
            (bond_id, self.canvas.model.bond_for_id(bond_id))
            for bond_id in self.canvas.model.bond_ids_from(length)
        ]
        affected_atom_ids = {
            atom_id
            for _bond_id, bond in trimmed_bonds
            if bond is not None
            for atom_id in (bond.a, bond.b)
        }
        self.canvas.model.trim_bonds(length)
        for bond_id, bond in trimmed_bonds:
            if bond is not None:
                graph_service.remove_bond_index(bond_id, bond.a, bond.b)
                graph_service.remove_bond_neighbors(
                    bond.a, bond.b, skip_bond_id=bond_id
                )
            self._clear_bond_graphics(bond_id)
        self._relayout_atom_labels(affected_atom_ids, refresh_ring_bonds=True)
        self.hit_testing_service.mark_spatial_index_dirty()

    def _relayout_atom_labels(
        self, atom_ids: set[int], *, refresh_ring_bonds: bool = False
    ) -> None:
        if atom_ids:
            graph = self.canvas.runtime_state.graph_state
            bond_ids = {
                bond_id
                for atom_id in atom_ids
                for bond_id in graph.atom_bond_ids.get(atom_id, ())
            }
            # Closing/opening a cycle changes the side of double bonds even far
            # from the edited endpoints. Refresh live ring-dependent graphics;
            # creation/restoration still owns any not-yet-built bond items.
            if refresh_ring_bonds:
                bond_ids.update(
                    bond_id
                    for bond_id, bond in enumerate(self.canvas.model.bonds)
                    if bond is not None
                    and (bond.order == 2 or bond.style in {"bold_in", "bold_out"})
                )
            self._atom_label_relayout(atom_ids, bond_ids)
            for bond_id in sorted(bond_ids):
                if self.canvas.runtime_state.bond_graphics_state.bond_items.get(
                    bond_id, []
                ):
                    self.canvas.bond_renderer.update_bond_geometry(
                        bond_id, allow_topology_rebuild=True
                    )

    def _clear_bond_graphics(self, bond_id: int) -> None:
        remove_items_from_canvas_scene(
            self.canvas,
            self.canvas.runtime_state.bond_graphics_state.bond_items.get(bond_id, []),
        )
        pop_bond_items_for(self.canvas, bond_id)


__all__ = ["CanvasBondMutationService"]
