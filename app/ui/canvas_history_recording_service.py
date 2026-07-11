from __future__ import annotations

import copy
from collections.abc import Callable

from core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    HistoryCommand,
    UpdateBondCommand,
)

from ui.atom_coords_access import atom_coords_3d_for
from ui.canvas_model_access import (
    atom_for_id,
    bond_count_for,
    bond_for_id,
    next_atom_id_for,
)
from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
)
from ui.history_command_snapshot import HistoryCommandSnapshot
from ui.history_commands import AddSceneItemsCommand
from ui.history_push_failure_recovery import (
    RecordingHistoryPolicySnapshot,
    _verify_history_and_policy_authority,
    recover_failed_recording_push,
)
from ui.history_stack_snapshot import HistoryStackSnapshot
from ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)


def _frozen_recorded_after_verifier(
    canvas,
    command: HistoryCommand,
) -> Callable[[], None]:
    """Freeze a command's published payload before an untrusted history push.

    History observers receive the live command and canvas.  Comparing runtime
    with that same mutable command after publication lets an observer rewrite
    both sides and make a corrupt commit appear valid, so retain independent
    copies of every supported after-state first.
    """

    if isinstance(command, CompositeCommand):
        verifiers = tuple(
            _frozen_recorded_after_verifier(canvas, child)
            for child in tuple(command.commands)
        )

        def verify_composite() -> None:
            for verify in verifiers:
                verify()

        return verify_composite

    if isinstance(command, AddAtomsCommand):
        atom_states = copy.deepcopy(command.atom_states)
        after_next_atom_id = command.after_next_atom_id
        after_smiles_input = command.after_smiles_input
        atom_coords_3d = copy.deepcopy(command.atom_coords_3d)

        def verify_atoms() -> None:
            if next_atom_id_for(canvas) != after_next_atom_id:
                raise RuntimeError(
                    "recorded atom next-id changed after history publication"
                )
            if last_smiles_input_for(canvas) != after_smiles_input:
                raise RuntimeError(
                    "recorded atom SMILES changed after history publication"
                )
            for atom_id, expected_state in atom_states.items():
                if (
                    atom_for_id(canvas, atom_id) is None
                    or atom_state_dict_for(canvas, atom_id) != expected_state
                ):
                    raise RuntimeError(
                        "recorded atom state changed after history publication"
                    )
            if atom_coords_3d is not None:
                live_coords = atom_coords_3d_for(canvas)
                if any(
                    live_coords.get(atom_id) != expected
                    for atom_id, expected in atom_coords_3d.items()
                ):
                    raise RuntimeError(
                        "recorded atom coordinates changed after history publication"
                    )

        return verify_atoms

    if isinstance(command, AddBondCommand):
        bond_id = command.bond_id
        bond_state = copy.deepcopy(command.bond_state)
        after_smiles_input = command.after_smiles_input

        def verify_bond_addition() -> None:
            bond = bond_for_id(canvas, bond_id)
            if bond is None or bond_state_dict(bond) != bond_state:
                raise RuntimeError(
                    "recorded bond state changed after history publication"
                )
            if last_smiles_input_for(canvas) != after_smiles_input:
                raise RuntimeError(
                    "recorded bond SMILES changed after history publication"
                )

        return verify_bond_addition

    if isinstance(command, UpdateBondCommand):
        bond_id = command.bond_id
        after_state = copy.deepcopy(command.after_state)
        after_smiles_input = command.after_smiles_input

        def verify_bond_update() -> None:
            bond = bond_for_id(canvas, bond_id)
            if bond is None or bond_state_dict(bond) != after_state:
                raise RuntimeError(
                    "recorded bond update changed after history publication"
                )
            if last_smiles_input_for(canvas) != after_smiles_input:
                raise RuntimeError(
                    "recorded bond-update SMILES changed after history publication"
                )

        return verify_bond_update

    if isinstance(command, AddSceneItemsCommand):
        items = tuple(command.items)
        item_states = copy.deepcopy(command.item_states)

        def verify_scene_items() -> None:
            if len(items) != len(item_states):
                raise RuntimeError(
                    "recorded scene-item payload changed before publication"
                )
            for item, expected_state in zip(items, item_states, strict=True):
                if scene_item_state_for(canvas, item) != expected_state:
                    raise RuntimeError(
                        "recorded scene item changed after history publication"
                    )

        return verify_scene_items

    return lambda: None


class CanvasHistoryRecordingService:
    def __init__(self, canvas, history_service=None) -> None:
        self.canvas = canvas
        self.history = history_service

    def _push_history(self, command: HistoryCommand) -> None:
        history_snapshot: HistoryStackSnapshot | None = None
        policy_snapshot: RecordingHistoryPolicySnapshot | None = None
        command_snapshot: HistoryCommandSnapshot | None = None
        after_runtime_snapshot: object | None = None
        try:
            command_snapshot = HistoryCommandSnapshot.capture(command)
            verify_recorded_after = _frozen_recorded_after_verifier(
                self.canvas,
                command,
            )
            # This savepoint is the exact already-mutated canvas authority.  A
            # history push/observer may mutate unrelated runtime before raising;
            # recovery must restore this state before invoking the command's
            # inverse, rather than blessing the observer's mixed state as the
            # new rollback baseline.
            after_runtime_snapshot = capture_history_transaction_for_history(
                self.canvas,
                history_service=None,
                guard_scene_rect=False,
            )
            runtime_verify = getattr(after_runtime_snapshot, "verify_exact", None)
            if not callable(runtime_verify):
                raise RuntimeError(
                    "recorded history publication has no exact runtime verifier"
                )
            initial_runtime_errors = tuple(runtime_verify())
            if initial_runtime_errors:
                # Lightweight non-canvas test doubles historically expose only
                # a history port and cannot satisfy the production model/scene
                # transaction protocol. Keep their inverse-only compatibility;
                # a real canvas whose capture itself raises still fails closed.
                if getattr(self.canvas, "model", None) is not None:
                    raise BaseExceptionGroup(
                        "recorded history publication did not capture an exact "
                        "after-runtime",
                        list(initial_runtime_errors),
                    )
                release_history_transaction_for_history(
                    self.canvas,
                    after_runtime_snapshot,
                )
                after_runtime_snapshot = None
                runtime_verify = None
            history_snapshot = HistoryStackSnapshot.capture(self.history)
            if history_snapshot is not None:
                policy_snapshot = RecordingHistoryPolicySnapshot.capture(
                    history_snapshot
                )
                _verify_history_and_policy_authority(
                    history_snapshot,
                    policy_snapshot,
                )
            command_snapshot.verify()
            self.history.push(command)
            command_snapshot.verify()
            verify_recorded_after()
            if callable(runtime_verify):
                runtime_errors = tuple(runtime_verify())
                if runtime_errors:
                    raise BaseExceptionGroup(
                        "recorded canvas changed during history publication",
                        list(runtime_errors),
                    )
            # Runtime verification may cross Qt/extension getters. Close on
            # the callback-free command payload so neither side can rewrite
            # the other and then appear self-consistent.
            command_snapshot.verify()
            if after_runtime_snapshot is not None:
                release_history_transaction_for_history(
                    self.canvas,
                    after_runtime_snapshot,
                )
        except BaseException as error:
            recover_failed_recording_push(
                self.canvas,
                command,
                history_snapshot,
                error,
                phase="recorded canvas mutation",
                policy_snapshot=policy_snapshot,
                command_snapshot=command_snapshot,
                after_runtime_snapshot=after_runtime_snapshot,
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
        if not self.history.is_enabled():
            return
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
