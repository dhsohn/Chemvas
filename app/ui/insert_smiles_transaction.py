from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    HistoryCommand,
)
from ui.history_commands import DeleteSceneItemsCommand

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class SmilesLoadSnapshot:
    before_smiles_input: str | None
    before_next_atom_id: int
    atom_states: dict[int, dict]
    bond_states: dict[int, dict]
    mark_states_for_atoms: list[dict]
    scene_items: list[object] = field(default_factory=list)
    scene_item_states: list[dict] = field(default_factory=list)

    def build_command(
        self,
        canvas: CanvasView,
        *,
        after_clear_next_atom_id: int,
        after_smiles_input: str,
    ) -> HistoryCommand | None:
        commands: list[HistoryCommand] = []
        for bond_id, bond_state in self.bond_states.items():
            commands.append(
                DeleteBondCommand(
                    bond_id=bond_id,
                    bond_state=bond_state,
                    before_smiles_input=self.before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        if self.atom_states:
            commands.append(
                DeleteAtomsCommand(
                    atom_states=self.atom_states,
                    mark_states=self.mark_states_for_atoms,
                    before_next_atom_id=self.before_next_atom_id,
                    after_next_atom_id=after_clear_next_atom_id,
                    before_smiles_input=self.before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        if self.scene_item_states:
            commands.append(
                DeleteSceneItemsCommand(
                    item_states=self.scene_item_states,
                    items=list(self.scene_items),
                )
            )
        new_atom_states = {atom_id: canvas._atom_state_dict(atom_id) for atom_id in canvas.model.atoms}
        if new_atom_states:
            commands.append(
                AddAtomsCommand(
                    atom_states=new_atom_states,
                    before_next_atom_id=after_clear_next_atom_id,
                    after_next_atom_id=canvas.model.next_atom_id,
                    before_smiles_input=self.before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        for bond_id, bond in enumerate(canvas.model.bonds):
            if bond is None:
                continue
            commands.append(
                AddBondCommand(
                    bond_id=bond_id,
                    bond_state=canvas._bond_state_dict(bond),
                    previous_bond_count=bond_id,
                    before_smiles_input=self.before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        if not commands:
            return None
        if len(commands) == 1:
            return commands[0]
        return CompositeCommand(commands)


class SmilesLoadTransactionBuilder:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def capture(self) -> SmilesLoadSnapshot:
        atom_states = {atom_id: self.canvas._atom_state_dict(atom_id) for atom_id in self.canvas.model.atoms}
        bond_states = {
            bond_id: self.canvas._bond_state_dict(bond)
            for bond_id, bond in enumerate(self.canvas.model.bonds)
            if bond is not None
        }
        mark_states_for_atoms: list[dict] = []
        for atom_id in atom_states:
            for mark in self.canvas._marks_by_atom.get(atom_id, []):
                mark_states_for_atoms.append(self.canvas._mark_state_dict(mark))
        scene_items = self._scene_items_for_delete(set(atom_states))
        scene_item_states = [self.canvas.scene_item_state(item) for item in scene_items]
        return SmilesLoadSnapshot(
            before_smiles_input=self.canvas.last_smiles_input,
            before_next_atom_id=self.canvas.model.next_atom_id,
            atom_states=atom_states,
            bond_states=bond_states,
            mark_states_for_atoms=mark_states_for_atoms,
            scene_items=scene_items,
            scene_item_states=scene_item_states,
        )

    def build_command(
        self,
        snapshot: SmilesLoadSnapshot,
        *,
        after_clear_next_atom_id: int,
        after_smiles_input: str,
    ) -> HistoryCommand | None:
        return snapshot.build_command(
            self.canvas,
            after_clear_next_atom_id=after_clear_next_atom_id,
            after_smiles_input=after_smiles_input,
        )

    def _scene_items_for_delete(self, atom_ids: set[int]) -> list[object]:
        scene_items = list(self.canvas.ring_items)
        scene_items.extend(self._free_mark_items(atom_ids))
        scene_items.extend(self.canvas.note_items)
        scene_items.extend(self.canvas.arrow_items)
        scene_items.extend(self.canvas.ts_bracket_items)
        scene_items.extend(self.canvas.orbital_items)
        return scene_items

    def _free_mark_items(self, atom_ids: set[int]) -> list[object]:
        free_mark_items: list[object] = []
        for item in self.canvas.mark_items:
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if not isinstance(atom_id, int) or atom_id not in atom_ids:
                free_mark_items.append(item)
        return free_mark_items


__all__ = ["SmilesLoadSnapshot", "SmilesLoadTransactionBuilder"]
