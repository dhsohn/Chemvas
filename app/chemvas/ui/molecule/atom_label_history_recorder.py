from __future__ import annotations

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
)
from chemvas.core.model_commands import (
    DeleteAtomsCommand,
    DeleteBondCommand,
    UpdateBondCommand,
)
from chemvas.ui.annotations.state import bond_state_dict
from chemvas.ui.canvas.canvas_history_recording_service import (
    CanvasHistoryRecordingService,
)
from chemvas.ui.history.history_commands import ChangeAtomLabelCommand


class AtomLabelHistoryRecorder:
    def __init__(self, canvas, *, history_service) -> None:
        self.canvas = canvas
        self.history = history_service

    def _push_or_rollback(
        self,
        command: HistoryCommand,
        *,
        merged_atom_id: int | None = None,
        merged_atom_ids=(),
    ) -> None:
        CanvasHistoryRecordingService(
            self.canvas,
            history_service=self.history,
        ).push_history(
            command, merged_atom_id=merged_atom_id, merged_atom_ids=merged_atom_ids
        )

    def record_label_change(
        self,
        atom_id: int,
        *,
        before_element: str,
        after_element: str,
        before_explicit_label: bool,
        after_explicit_label: bool,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        commands: list[HistoryCommand] = []
        if (
            before_element != after_element
            or before_explicit_label != after_explicit_label
        ):
            commands.append(
                ChangeAtomLabelCommand(
                    atom_id=atom_id,
                    before_element=before_element,
                    after_element=after_element,
                    before_explicit_label=before_explicit_label,
                    after_explicit_label=after_explicit_label,
                )
            )
        if merge_ids:
            commands.extend(
                self._merge_history_commands(
                    merge_info=merge_info,
                )
            )
        if not commands:
            return
        if merge_ids:
            command = commands[0] if len(commands) == 1 else CompositeCommand(commands)
            self._push_or_rollback(
                command, merged_atom_id=atom_id, merged_atom_ids=merge_ids
            )
            return
        if len(commands) == 1:
            self._push_or_rollback(commands[0])
            return
        self._push_or_rollback(CompositeCommand(commands))

    def _merge_history_commands(self, *, merge_info: dict) -> list[HistoryCommand]:
        commands: list[HistoryCommand] = []
        bond_before_states = merge_info.get("bond_before_states", {})
        deleted_bond_ids = set(merge_info.get("deleted_bond_ids", []))
        for bond_id, before_state in bond_before_states.items():
            if bond_id in deleted_bond_ids:
                commands.append(
                    DeleteBondCommand(
                        bond_id=bond_id,
                        bond_state=before_state,
                    )
                )
                continue
            bond = self.canvas.model.bond_for_id(bond_id)
            if bond is None:
                continue
            after_state = bond_state_dict(bond)
            if before_state != after_state:
                commands.append(
                    UpdateBondCommand(
                        bond_id=bond_id,
                        before_state=before_state,
                        after_state=after_state,
                    )
                )
        atom_states = merge_info.get("atom_states", {})
        if atom_states:
            commands.append(
                DeleteAtomsCommand(
                    atom_states=atom_states,
                    mark_states=[],
                    before_next_atom_id=int(self.canvas.model.next_atom_id),
                    after_next_atom_id=int(self.canvas.model.next_atom_id),
                    remove_marks=False,
                    atom_coords_3d=merge_info.get("atom_coords_3d") or None,
                )
            )
        return commands


__all__ = ["AtomLabelHistoryRecorder"]
