from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.atom_label_access import add_or_update_atom_label, atom_label_service
from ui.canvas_model_access import atoms_for, bonds_for
from ui.canvas_smiles_input_state import (
    clear_last_smiles_input_for,
    last_smiles_input_for,
)
from ui.renderer_style_access import bond_length_px_for
from ui.structure_insert_access import (
    add_insert_atom_for,
    add_insert_bond_for,
    add_insert_bond_graphics_for,
    ensure_insert_carbon_dot_for,
    insert_atom_for_id,
    insert_bond_count_for,
    insert_next_atom_id_for,
    new_insert_bond_ids_from,
    record_insert_additions_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class StructureBuildHistorySnapshot:
    before_smiles_input: str | None
    before_next_atom_id: int
    before_bond_count: int


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
        )
        clear_last_smiles_input_for(self.canvas)
        return snapshot

    def record_additions(
        self,
        snapshot: StructureBuildHistorySnapshot,
        *,
        added_scene_items: list | None = None,
    ) -> None:
        kwargs = {
            "before_next_atom_id": snapshot.before_next_atom_id,
            "before_bond_count": snapshot.before_bond_count,
            "before_smiles_input": snapshot.before_smiles_input,
        }
        if added_scene_items is not None:
            kwargs["added_scene_items"] = added_scene_items
        record_insert_additions_for(self.canvas, **kwargs)

    def add_bond_graphics(self, bond_id: int) -> None:
        add_insert_bond_graphics_for(self.canvas, bond_id)

    def add_atom(self, element: str, x: float, y: float) -> int:
        return add_insert_atom_for(self.canvas, element, x, y)

    def add_bond(self, a_id: int, b_id: int, order: int = 1) -> int:
        return add_insert_bond_for(self.canvas, a_id, b_id, order)

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
    ) -> list[int]:
        merge = merge or []
        atom_ids = []
        for idx, point in enumerate(points):
            element = elements[idx] if elements else "C"
            atom_ids.append(self.add_atom_with_merge(point, element, merge))
        bonds_start = insert_bond_count_for(self.canvas)
        for index in range(len(atom_ids)):
            self.add_bond(atom_ids[index], atom_ids[(index + 1) % len(atom_ids)])
        self.add_bond_graphics_range(bonds_start)
        self.label_non_carbon_atoms(atom_ids, elements or ["C"] * len(atom_ids))
        return atom_ids

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
