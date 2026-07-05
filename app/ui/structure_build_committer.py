from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF

from ui.atom_label_access import add_or_update_atom_label, atom_label_service
from ui.canvas_model_access import atom_for_id, atoms_for, bonds_for
from ui.canvas_ring_fill_scene_access import create_ring_fill_item_for
from ui.canvas_scene_items_state import (
    SCENE_ITEM_COLLECTION_ATTRS,
    ring_items_for,
    scene_item_collection_for,
)
from ui.canvas_smiles_input_state import (
    clear_last_smiles_input_for,
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from ui.graph_algorithms import find_rings
from ui.renderer_style_access import bond_length_px_for
from ui.scene_item_access import attach_scene_item, remove_scene_item
from ui.structure_insert_access import (
    add_insert_atom_for,
    add_insert_bond_for,
    add_insert_bond_graphics_for,
    ensure_insert_carbon_dot_for,
    insert_atom_for_id,
    insert_bond_count_for,
    insert_bond_for_id,
    insert_next_atom_id_for,
    new_insert_bond_ids_from,
    record_insert_additions_for,
    rollback_insert_mutation_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class StructureBuildHistorySnapshot:
    before_smiles_input: str | None
    before_next_atom_id: int
    before_bond_count: int
    before_scene_items: dict[str, tuple[Any, ...]]


class StructureBuildCommitter:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def begin_recorded_change(
        self,
        *,
        before_smiles_input: str | None = None,
    ) -> StructureBuildHistorySnapshot:
        if before_smiles_input is None:
            before_smiles_input = last_smiles_input_for(self.canvas)
        snapshot = StructureBuildHistorySnapshot(
            before_smiles_input=before_smiles_input,
            before_next_atom_id=insert_next_atom_id_for(self.canvas),
            before_bond_count=insert_bond_count_for(self.canvas),
            before_scene_items=self._scene_item_snapshot(),
        )
        clear_last_smiles_input_for(self.canvas)
        return snapshot

    def record_additions(
        self,
        snapshot: StructureBuildHistorySnapshot,
        *,
        added_scene_items: list | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "before_next_atom_id": snapshot.before_next_atom_id,
            "before_bond_count": snapshot.before_bond_count,
            "before_smiles_input": snapshot.before_smiles_input,
        }
        merged_scene_items = self._merged_added_scene_items(snapshot, added_scene_items)
        if merged_scene_items is not None:
            kwargs["added_scene_items"] = merged_scene_items
        record_insert_additions_for(self.canvas, **kwargs)

    def abort_recorded_change(self, snapshot: StructureBuildHistorySnapshot) -> None:
        self._remove_new_scene_items(snapshot)
        rollback_insert_mutation_for(
            self.canvas,
            before_next_atom_id=snapshot.before_next_atom_id,
            before_bond_count=snapshot.before_bond_count,
        )
        set_last_smiles_input_for(self.canvas, snapshot.before_smiles_input)

    def _scene_item_snapshot(self) -> dict[str, tuple[Any, ...]]:
        return {
            name: tuple(scene_item_collection_for(self.canvas, name))
            for name in SCENE_ITEM_COLLECTION_ATTRS
        }

    def _new_scene_items_since(self, snapshot: StructureBuildHistorySnapshot) -> list[Any]:
        items: list[Any] = []
        seen_ids: set[int] = set()
        before_ids = {
            id(item)
            for collection in snapshot.before_scene_items.values()
            for item in collection
        }
        for name in SCENE_ITEM_COLLECTION_ATTRS:
            for item in scene_item_collection_for(self.canvas, name):
                item_id = id(item)
                if item_id in before_ids or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                items.append(item)
        return items

    def _merged_added_scene_items(
        self,
        snapshot: StructureBuildHistorySnapshot,
        added_scene_items: list | None,
    ) -> list | None:
        merged: list[Any] = []
        seen_ids: set[int] = set()
        for item in [*(added_scene_items or []), *self._new_scene_items_since(snapshot)]:
            item_id = id(item)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            merged.append(item)
        if added_scene_items is None and not merged:
            return None
        return merged

    def _remove_new_scene_items(self, snapshot: StructureBuildHistorySnapshot) -> None:
        for item in reversed(self._new_scene_items_since(snapshot)):
            try:
                remove_scene_item(self.canvas, item)
            except AttributeError:
                for name in SCENE_ITEM_COLLECTION_ATTRS:
                    collection = scene_item_collection_for(self.canvas, name)
                    if item in collection:
                        collection.remove(item)

    def add_bond_graphics(self, bond_id: int) -> None:
        add_insert_bond_graphics_for(self.canvas, bond_id)

    def add_atom(self, element: str, x: float, y: float) -> int:
        return add_insert_atom_for(self.canvas, element, x, y)

    def add_bond(self, a_id: int, b_id: int, order: int = 1, *, style: str = "single") -> int:
        bond_id = add_insert_bond_for(self.canvas, a_id, b_id, order)
        bond = insert_bond_for_id(self.canvas, bond_id)
        if bond is not None:
            bond.style = style
        return bond_id

    def bond_id_between(self, a_id: int, b_id: int) -> int | None:
        for bond_id, bond in enumerate(bonds_for(self.canvas)):
            if bond is None:
                continue
            if (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id):
                return bond_id
        return None

    def add_bond_graphics_range(self, start_bond_id: int) -> None:
        for bond_id in new_insert_bond_ids_from(self.canvas, start_bond_id):
            self.add_bond_graphics(bond_id)

    def add_atom_label(
        self,
        atom_id: int,
        element: str,
        *,
        record: bool = True,
        show_carbon: bool = False,
    ) -> None:
        kwargs = {"record": record}
        if show_carbon:
            kwargs["show_carbon"] = True
        atom_label_service(self.canvas).add_or_update_atom_label(atom_id, element, **kwargs)

    def label_non_carbon_atoms(self, atom_ids: list[int], elements: list[str]) -> None:
        for atom_id, element in zip(atom_ids, elements, strict=False):
            if element != "C":
                atom = insert_atom_for_id(self.canvas, atom_id)
                if atom is None:
                    continue
                add_or_update_atom_label(
                    self.canvas,
                    atom_id,
                    atom.element,
                    record=False,
                )

    def add_atom_with_merge(self, point: QPointF, element: str, merge: list) -> int:
        tol = bond_length_px_for(self.canvas) * 0.2
        for entry in merge:
            atom_id, x, y = entry
            if abs(point.x() - x) < tol and abs(point.y() - y) < tol:
                return atom_id
        atom_id = self.add_atom(element, point.x(), point.y())
        merge.append((atom_id, point.x(), point.y()))
        return atom_id

    def add_ring_from_points(
        self,
        points,
        elements: list[str] | None = None,
        merge: list | None = None,
        bond_orders: list[int] | None = None,
    ) -> list[int]:
        if merge is None:
            merge = []
        atom_ids = []
        for idx, point in enumerate(points):
            element = elements[idx] if elements else "C"
            atom_ids.append(self.add_atom_with_merge(point, element, merge))
        resolved_bond_orders = self.resolved_ring_bond_orders(atom_ids, bond_orders)
        bonds_start = insert_bond_count_for(self.canvas)
        for index in range(len(atom_ids)):
            order = resolved_bond_orders[index]
            a_id = atom_ids[index]
            b_id = atom_ids[(index + 1) % len(atom_ids)]
            if self.bond_id_between(a_id, b_id) is not None:
                continue
            self.add_bond(a_id, b_id, order)
        self.add_bond_graphics_range(bonds_start)
        self.label_non_carbon_atoms(atom_ids, elements or ["C"] * len(atom_ids))
        if len(points) >= 3:
            ring_item = create_ring_fill_item_for(self.canvas, list(points), atom_ids)
            attach_scene_item(self.canvas, ring_item)
        return atom_ids

    def resolved_ring_bond_orders(self, atom_ids: list[int], bond_orders: list[int] | None) -> list[int]:
        if not bond_orders:
            return [1] * len(atom_ids)
        resolved = [bond_orders[index] if index < len(bond_orders) else 1 for index in range(len(atom_ids))]
        if not self._is_alternating_single_double_pattern(resolved):
            return resolved
        inverted = [1 if order == 2 else 2 for order in resolved]
        valid_candidates = [
            (self._projected_ring_double_bond_count(atom_ids, candidate), index, candidate)
            for index, candidate in enumerate((resolved, inverted))
            if self._max_projected_bond_order_sum(atom_ids, candidate) <= 4
        ]
        exact_benzene_candidates = [candidate for candidate in valid_candidates if candidate[0] == 3]
        if exact_benzene_candidates:
            return min(exact_benzene_candidates, key=lambda candidate: candidate[1])[2]
        under_benzene_candidates = [candidate for candidate in valid_candidates if candidate[0] < 3]
        if under_benzene_candidates:
            return max(under_benzene_candidates, key=lambda candidate: (candidate[0], -candidate[1]))[2]
        if valid_candidates:
            return min(valid_candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]
        return resolved

    @staticmethod
    def _is_alternating_single_double_pattern(bond_orders: list[int]) -> bool:
        return all(order in (1, 2) for order in bond_orders) and all(
            bond_orders[index] != bond_orders[(index + 1) % len(bond_orders)] for index in range(len(bond_orders))
        )

    def _max_projected_bond_order_sum(self, atom_ids: list[int], bond_orders: list[int]) -> int:
        sums = {atom_id: 0 for atom_id in atom_ids}
        for bond in bonds_for(self.canvas):
            if bond is None:
                continue
            if bond.a in sums:
                sums[bond.a] += max(1, int(bond.order or 1))
            if bond.b in sums:
                sums[bond.b] += max(1, int(bond.order or 1))
        for index, order in enumerate(bond_orders):
            a_id = atom_ids[index]
            b_id = atom_ids[(index + 1) % len(atom_ids)]
            if self.bond_id_between(a_id, b_id) is not None:
                continue
            sums[a_id] += order
            sums[b_id] += order
        return max(sums.values(), default=0)

    def _projected_ring_double_bond_count(self, atom_ids: list[int], bond_orders: list[int]) -> int:
        double_count = 0
        for index, order in enumerate(bond_orders):
            a_id = atom_ids[index]
            b_id = atom_ids[(index + 1) % len(atom_ids)]
            existing_bond = insert_bond_for_id(self.canvas, self.bond_id_between(a_id, b_id))
            if existing_bond is not None:
                if existing_bond.order >= 2:
                    double_count += 1
            elif order == 2:
                double_count += 1
        return double_count

    def add_linear_chain(self, points: list[QPointF], elements: list[str], bonds: list[int]) -> list[int]:
        atom_ids = []
        for point, element in zip(points, elements, strict=False):
            atom_ids.append(self.add_atom(element, point.x(), point.y()))
        bonds_start = insert_bond_count_for(self.canvas)
        for index, order in enumerate(bonds):
            self.add_bond(atom_ids[index], atom_ids[index + 1], order)
        self.add_bond_graphics_range(bonds_start)
        self.label_non_carbon_atoms(atom_ids, elements)
        return atom_ids

    def ensure_ring_fills_for_model(self) -> list:
        rings = find_rings(bonds_for(self.canvas))
        if not rings:
            return []
        existing: set[frozenset[int]] = set()
        for ring_item in ring_items_for(self.canvas):
            ring_atom_ids = ring_item.data(2)
            if isinstance(ring_atom_ids, list):
                existing.add(frozenset(a for a in ring_atom_ids if isinstance(a, int)))
        created: list = []
        for ring in rings:
            if frozenset(ring) in existing:
                continue
            points = []
            for atom_id in ring:
                atom = atom_for_id(self.canvas, atom_id)
                if atom is None:
                    break
                points.append(QPointF(atom.x, atom.y))
            if len(points) != len(ring) or len(points) < 3:
                continue
            item = create_ring_fill_item_for(self.canvas, points, list(ring))
            attach_scene_item(self.canvas, item)
            created.append(item)
        return created

    def render_model(self) -> None:
        for bond_id, bond in enumerate(bonds_for(self.canvas)):
            if bond is None:
                continue
            self.add_bond_graphics(bond_id)

        for atom_id, atom in atoms_for(self.canvas).items():
            if atom.element == "C":
                if atom.explicit_label:
                    add_or_update_atom_label(
                        self.canvas,
                        atom_id,
                        atom.element,
                        clear_smiles=False,
                        record=False,
                        show_carbon=True,
                    )
                else:
                    ensure_insert_carbon_dot_for(self.canvas, atom_id)
            else:
                add_or_update_atom_label(
                    self.canvas,
                    atom_id,
                    atom.element,
                    clear_smiles=False,
                    record=False,
                )


__all__ = ["StructureBuildCommitter", "StructureBuildHistorySnapshot"]
