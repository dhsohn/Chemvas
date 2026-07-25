from __future__ import annotations

from chemvas.core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    HistoryCommand,
    UpdateBondCommand,
)
from chemvas.ui.atom_coords_access import atom_coords_3d_for
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    bond_count_for,
    bond_for_id,
    next_atom_id_for,
)
from chemvas.ui.canvas_smiles_input_state import last_smiles_input_for
from chemvas.ui.history_commands import AddSceneItemsCommand
from chemvas.ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)


class CanvasHistoryRecordingService:
    def __init__(self, canvas, history_service=None) -> None:
        self.canvas = canvas
        self.history = history_service

    def push_history(self, command: HistoryCommand) -> None:
        self._push_history(command)

    def _push_history(self, command: HistoryCommand) -> None:
        try:
            self.history.push(command)
        except Exception as original_error:
            try:
                command.undo(self.canvas)
            except Exception as inverse_error:
                original_error.add_note(
                    "Recorded mutation inverse also failed: "
                    f"{type(inverse_error).__name__}: {inverse_error}"
                )
            raise

    def record_additions(
        self,
        before_next_atom_id: int,
        before_bond_count: int,
        before_smiles_input: str | None,
        added_scene_items: list | None = None,
    ) -> None:
        commands: list[HistoryCommand] = []
        after_next_atom_id = next_atom_id_for(self.canvas)
        if after_next_atom_id > before_next_atom_id:
            atom_states = {
                atom_id: atom_state_dict_for(self.canvas, atom_id)
                for atom_id in range(before_next_atom_id, after_next_atom_id)
                if atom_for_id(self.canvas, atom_id) is not None
            }
            if atom_states:
                stored_coords_3d = atom_coords_3d_for(self.canvas)
                atom_coords_3d = {
                    atom_id: stored_coords_3d[atom_id]
                    for atom_id in atom_states
                    if atom_id in stored_coords_3d
                }
                commands.append(
                    AddAtomsCommand(
                        atom_states=atom_states,
                        before_next_atom_id=before_next_atom_id,
                        after_next_atom_id=after_next_atom_id,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=last_smiles_input_for(self.canvas),
                        atom_coords_3d=atom_coords_3d or None,
                    )
                )
        for bond_id in range(before_bond_count, bond_count_for(self.canvas)):
            bond = bond_for_id(self.canvas, bond_id)
            if bond is None:
                continue
            bond_state = bond_state_dict(bond)
            commands.append(
                AddBondCommand(
                    bond_id=bond_id,
                    bond_state=bond_state,
                    previous_bond_count=bond_id,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=last_smiles_input_for(self.canvas),
                )
            )
        if added_scene_items:
            states = [
                scene_item_state_for(self.canvas, item)
                for item in added_scene_items
                if item is not None
            ]
            if states:
                commands.append(
                    AddSceneItemsCommand(
                        item_states=states, items=list(added_scene_items)
                    )
                )
        if not commands:
            return
        if len(commands) == 1:
            self._push_history(commands[0])
            return
        self._push_history(CompositeCommand(commands))

    def record_bond_update(
        self,
        bond_id: int,
        before_state: dict,
        after_state: dict,
        before_smiles_input: str | None,
        after_smiles_input: str | None,
    ) -> None:
        if before_state == after_state and before_smiles_input == after_smiles_input:
            return
        self._push_history(
            UpdateBondCommand(
                bond_id=bond_id,
                before_state=before_state,
                after_state=after_state,
                before_smiles_input=before_smiles_input,
                after_smiles_input=after_smiles_input,
            )
        )


__all__ = ["CanvasHistoryRecordingService"]
