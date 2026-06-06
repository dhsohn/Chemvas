from __future__ import annotations

from core.history import (
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    HistoryCommand,
    UpdateBondCommand,
)

from ui.canvas_model_access import bond_for_id, next_atom_id_for
from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.history_commands import ChangeAtomLabelCommand
from ui.scene_item_state import bond_state_dict


class AtomLabelHistoryRecorder:
    def __init__(self, canvas, *, history_service) -> None:
        self.canvas = canvas
        self.history = history_service

    def record_label_change(
        self,
        atom_id: int,
        *,
        before_element: str,
        after_element: str,
        before_explicit_label: bool,
        after_explicit_label: bool,
        before_smiles_input: str | None,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        if not self.history.is_enabled():
            return
        after_smiles_input = last_smiles_input_for(self.canvas)
        commands: list[HistoryCommand] = []
        if (
            before_element != after_element
            or before_explicit_label != after_explicit_label
            or before_smiles_input != after_smiles_input
        ):
            commands.append(
                ChangeAtomLabelCommand(
                    atom_id=atom_id,
                    before_element=before_element,
                    after_element=after_element,
                    before_explicit_label=before_explicit_label,
                    after_explicit_label=after_explicit_label,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        if merge_ids:
            commands.extend(
                self._merge_history_commands(
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=after_smiles_input,
                    merge_info=merge_info,
                )
            )
        if not commands:
            return
        if len(commands) == 1:
            self.history.push(commands[0])
            return
        self.history.push(CompositeCommand(commands))

    def _merge_history_commands(
        self,
        *,
        before_smiles_input: str | None,
        after_smiles_input: str | None,
        merge_info: dict,
    ) -> list[HistoryCommand]:
        commands: list[HistoryCommand] = []
        bond_before_states = merge_info.get("bond_before_states", {})
        deleted_bond_ids = set(merge_info.get("deleted_bond_ids", []))
        for bond_id, before_state in bond_before_states.items():
            if bond_id in deleted_bond_ids:
                commands.append(
                    DeleteBondCommand(
                        bond_id=bond_id,
                        bond_state=before_state,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=after_smiles_input,
                    )
                )
                continue
            bond = bond_for_id(self.canvas, bond_id)
            if bond is None:
                continue
            after_state = bond_state_dict(bond)
            if before_state != after_state:
                commands.append(
                    UpdateBondCommand(
                        bond_id=bond_id,
                        before_state=before_state,
                        after_state=after_state,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=after_smiles_input,
                    )
                )
        atom_states = merge_info.get("atom_states", {})
        if atom_states:
            commands.append(
                DeleteAtomsCommand(
                    atom_states=atom_states,
                    mark_states=[],
                    before_next_atom_id=next_atom_id_for(self.canvas),
                    after_next_atom_id=next_atom_id_for(self.canvas),
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=after_smiles_input,
                    remove_marks=False,
                )
            )
        return commands


__all__ = ["AtomLabelHistoryRecorder"]
