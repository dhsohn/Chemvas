from __future__ import annotations

from core.history import AddAtomsCommand, AddBondCommand, AddSceneItemsCommand, UpdateBondCommand, CompositeCommand


class CanvasHistoryRecordingService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def record_additions(
        self,
        before_next_atom_id: int,
        before_bond_count: int,
        before_smiles_input: str | None,
        added_scene_items: list | None = None,
    ) -> None:
        commands = []
        after_next_atom_id = self.canvas.model.next_atom_id
        if after_next_atom_id > before_next_atom_id:
            atom_states = {
                atom_id: self.canvas._atom_state_dict(atom_id)
                for atom_id in range(before_next_atom_id, after_next_atom_id)
                if atom_id in self.canvas.model.atoms
            }
            if atom_states:
                commands.append(
                    AddAtomsCommand(
                        atom_states=atom_states,
                        before_next_atom_id=before_next_atom_id,
                        after_next_atom_id=after_next_atom_id,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=self.canvas.last_smiles_input,
                    )
                )
        for bond_id in range(before_bond_count, len(self.canvas.model.bonds)):
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                continue
            bond_state = self.canvas._bond_state_dict(bond)
            commands.append(
                AddBondCommand(
                    bond_id=bond_id,
                    bond_state=bond_state,
                    previous_bond_count=bond_id,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=self.canvas.last_smiles_input,
                )
            )
        if added_scene_items:
            states = [self.canvas.scene_item_state(item) for item in added_scene_items if item is not None]
            if states:
                commands.append(AddSceneItemsCommand(item_states=states, items=list(added_scene_items)))
        if not commands:
            return
        if len(commands) == 1:
            self.canvas._push_command(commands[0])
            return
        self.canvas._push_command(CompositeCommand(commands))

    def record_bond_update(
        self,
        bond_id: int,
        before_state: dict,
        after_state: dict,
        before_smiles_input: str | None,
        after_smiles_input: str | None,
    ) -> None:
        if not self.canvas._history_enabled:
            return
        if before_state == after_state and before_smiles_input == after_smiles_input:
            return
        self.canvas._push_command(
            UpdateBondCommand(
                bond_id=bond_id,
                before_state=before_state,
                after_state=after_state,
                before_smiles_input=before_smiles_input,
                after_smiles_input=after_smiles_input,
            )
        )


__all__ = ["CanvasHistoryRecordingService"]
