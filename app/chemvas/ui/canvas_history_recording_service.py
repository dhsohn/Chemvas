from __future__ import annotations

from chemvas.core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    HistoryCommand,
    UpdateBondCommand,
)
from chemvas.domain.transactions import run_rollback_step
from chemvas.ui.atom_coords_access import atom_coords_3d_for
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    bond_count_for,
    bond_for_id,
    next_atom_id_for,
)
from chemvas.ui.canvas_smiles_input_state import last_smiles_input_for
from chemvas.ui.history_commands import AddSceneItemsCommand, GroupSceneItemsCommand
from chemvas.ui.scene_group_operations import (
    group_extensions_for_added_bonds,
    group_updates_for_atom_merge,
)
from chemvas.ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)


class CanvasHistoryRecordingService:
    def __init__(self, canvas, history_service=None) -> None:
        self.canvas = canvas
        self.history = history_service

    def push_history(
        self,
        command: HistoryCommand,
        *,
        merged_atom_id: int | None = None,
        merged_atom_ids=(),
    ) -> None:
        self._push_history(
            command, merged_atom_id=merged_atom_id, merged_atom_ids=merged_atom_ids
        )

    def _push_history(
        self,
        command: HistoryCommand,
        *,
        added_bond_ids=(),
        merged_atom_id: int | None = None,
        merged_atom_ids=(),
    ) -> None:
        try:
            group_updates = []
            if added_bond_ids:
                group_updates.extend(
                    group_extensions_for_added_bonds(self.canvas, added_bond_ids)
                )
            if merged_atom_id is not None and merged_atom_ids:
                group_updates.extend(
                    group_updates_for_atom_merge(
                        self.canvas, merged_atom_id, set(merged_atom_ids)
                    )
                )
            if group_updates:
                command = CompositeCommand([command, *group_updates])
                for update in group_updates:
                    update.redo(self.canvas)
            if self.history.push(command) is False and self.history.is_enabled():
                raise ValueError("History did not accept the edit.")
        except Exception as original_error:
            # ``command.undo`` is looked up inside the callable, so a command
            # without an inverse is noted rather than escaping past the step and
            # masking the push failure.
            run_rollback_step(
                original_error,
                "inverting a recorded mutation that failed to publish",
                lambda: command.undo(self.canvas),
            )
            raise

    def record_additions(
        self,
        before_next_atom_id: int,
        before_bond_count: int,
        before_smiles_input: str | None,
        added_scene_items: list | None = None,
        added_groups: list[GroupSceneItemsCommand] | None = None,
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
        if added_groups:
            commands.extend(added_groups)
        if not commands:
            return
        command = commands[0] if len(commands) == 1 else CompositeCommand(commands)
        self._push_history(
            command,
            added_bond_ids=range(before_bond_count, bond_count_for(self.canvas)),
        )

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
