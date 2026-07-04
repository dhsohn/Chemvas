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

from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import atoms_for, bonds_for, next_atom_id_for
from ui.canvas_scene_items_state import (
    arrow_items_for,
    mark_items_for,
    note_items_for,
    orbital_items_for,
    ring_items_for,
    ts_bracket_items_for,
)
from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.history_commands import AddSceneItemsCommand, DeleteSceneItemsCommand
from ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    mark_state_dict_for,
    scene_item_state_for,
)

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
        added_scene_items: list | None = None,
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
        new_atom_states = {atom_id: atom_state_dict_for(canvas, atom_id) for atom_id in atoms_for(canvas)}
        if new_atom_states:
            commands.append(
                AddAtomsCommand(
                    atom_states=new_atom_states,
                    before_next_atom_id=after_clear_next_atom_id,
                    after_next_atom_id=next_atom_id_for(canvas),
                    before_smiles_input=self.before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        for bond_id, bond in enumerate(bonds_for(canvas)):
            if bond is None:
                continue
            commands.append(
                AddBondCommand(
                    bond_id=bond_id,
                    bond_state=bond_state_dict(bond),
                    previous_bond_count=bond_id,
                    before_smiles_input=self.before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        if added_scene_items:
            item_states = []
            stateful_items = []
            for item in added_scene_items:
                if item is None:
                    continue
                state = scene_item_state_for(canvas, item)
                if not state:
                    continue
                item_states.append(state)
                stateful_items.append(item)
            if item_states:
                commands.append(AddSceneItemsCommand(item_states=item_states, items=stateful_items))
        if not commands:
            return None
        if len(commands) == 1:
            return commands[0]
        return CompositeCommand(commands)


class SmilesLoadTransactionBuilder:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas
        self.marks = mark_registry_for(canvas)

    def capture(self) -> SmilesLoadSnapshot:
        atom_states = {atom_id: atom_state_dict_for(self.canvas, atom_id) for atom_id in atoms_for(self.canvas)}
        bond_states = {
            bond_id: bond_state_dict(bond)
            for bond_id, bond in enumerate(bonds_for(self.canvas))
            if bond is not None
        }
        mark_states_for_atoms: list[dict] = []
        for atom_id in atom_states:
            for mark in self.marks.get_for_atom(atom_id) or []:
                mark_states_for_atoms.append(mark_state_dict_for(self.canvas, mark))
        scene_items = self._scene_items_for_delete(set(atom_states))
        scene_item_states = [scene_item_state_for(self.canvas, item) for item in scene_items]
        return SmilesLoadSnapshot(
            before_smiles_input=last_smiles_input_for(self.canvas),
            before_next_atom_id=next_atom_id_for(self.canvas),
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
        added_scene_items: list | None = None,
    ) -> HistoryCommand | None:
        return snapshot.build_command(
            self.canvas,
            after_clear_next_atom_id=after_clear_next_atom_id,
            after_smiles_input=after_smiles_input,
            added_scene_items=added_scene_items,
        )

    def _scene_items_for_delete(self, atom_ids: set[int]) -> list[object]:
        scene_items = list(ring_items_for(self.canvas))
        scene_items.extend(self._free_mark_items(atom_ids))
        scene_items.extend(note_items_for(self.canvas))
        scene_items.extend(arrow_items_for(self.canvas))
        scene_items.extend(ts_bracket_items_for(self.canvas))
        scene_items.extend(orbital_items_for(self.canvas))
        return scene_items

    def _free_mark_items(self, atom_ids: set[int]) -> list[object]:
        free_mark_items: list[object] = []
        for item in mark_items_for(self.canvas):
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if not isinstance(atom_id, int) or atom_id not in atom_ids:
                free_mark_items.append(item)
        return free_mark_items


__all__ = ["SmilesLoadSnapshot", "SmilesLoadTransactionBuilder"]
