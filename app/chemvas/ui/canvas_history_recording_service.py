from __future__ import annotations

import inspect
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from chemvas.core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    HistoryCommand,
    UpdateBondCommand,
)
from chemvas.domain.transactions import HistoryAuthoritySnapshot
from chemvas.ui.atom_coords_access import atom_coords_3d_for
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    bond_count_for,
    bond_for_id,
    next_atom_id_for,
)
from chemvas.ui.canvas_smiles_input_state import last_smiles_input_for
from chemvas.ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
)
from chemvas.ui.history_commands import AddSceneItemsCommand
from chemvas.ui.history_push_failure_recovery import (
    RecordingHistoryPolicySnapshot,
    recover_failed_recording_push,
)
from chemvas.ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)
from chemvas.ui.transactions.history_command import HistoryCommandSnapshot

_MISSING_BASELINE_VALUE = object()


@dataclass(slots=True)
class CallbackFreeHistoryBaseline:
    """The history stacks and policy frozen at capture, restored in place."""

    state: Any
    history: list
    history_items: tuple
    redo_stack: list
    redo_items: tuple
    enabled: object
    limit: object

    @classmethod
    def capture(
        cls,
        history: object,
        *,
        canvas: object = None,
    ) -> CallbackFreeHistoryBaseline | None:
        del canvas
        state = getattr(history, "state", None)
        if state is None:
            return None
        history_list = getattr(state, "history", None)
        redo_list = getattr(state, "redo_stack", None)
        if not isinstance(history_list, list) or not isinstance(redo_list, list):
            return None
        return cls(
            state=state,
            history=history_list,
            history_items=tuple(history_list),
            redo_stack=redo_list,
            redo_items=tuple(redo_list),
            enabled=getattr(state, "enabled", _MISSING_BASELINE_VALUE),
            limit=getattr(state, "limit", _MISSING_BASELINE_VALUE),
        )

    @staticmethod
    def _verify_items(actual: list, expected: tuple, *, name: str) -> None:
        if len(actual) != len(expected) or any(
            current is not item for current, item in zip(actual, expected, strict=False)
        ):
            raise RuntimeError(f"history {name} changed from its baseline")

    def verify(self) -> None:
        self._verify_items(self.history, self.history_items, name="undo stack")
        self._verify_items(self.redo_stack, self.redo_items, name="redo stack")

    def restore(self) -> None:
        self.history[:] = self.history_items
        self.redo_stack[:] = self.redo_items
        for name, value in (("enabled", self.enabled), ("limit", self.limit)):
            if value is not _MISSING_BASELINE_VALUE and (
                getattr(self.state, name, _MISSING_BASELINE_VALUE) != value
            ):
                setattr(self.state, name, value)

    def bind_snapshot(self, history_snapshot, policy_snapshot) -> None:
        del history_snapshot, policy_snapshot

    def verify_published_commands(self, publications) -> None:
        expected_history = list(self.history_items)
        expected_redo: tuple = self.redo_items
        for command, accepted in publications:
            if not accepted:
                continue
            expected_history.append(command)
            expected_redo = ()
            if type(self.limit) is int and len(expected_history) > self.limit:
                expected_history.pop(0)
        self._verify_items(
            self.history,
            tuple(expected_history),
            name="published undo stack",
        )
        self._verify_items(
            self.redo_stack,
            expected_redo,
            name="published redo stack",
        )


_MISSING_STATE_ROOT = object()


def _history_snapshot_service(history: object) -> object:
    """Adapt a duck history exposing ``state`` only through ``__getattr__``.

    Stack-port binding needs a plain attribute; the original service still
    owns the actual push operation.
    """

    if history is None:
        return history
    if (
        inspect.getattr_static(history, "state", _MISSING_STATE_ROOT)
        is not _MISSING_STATE_ROOT
    ):
        return history
    state = getattr(history, "state", None)
    if state is None:
        return history
    notify_change = getattr(history, "notify_change", None)
    return SimpleNamespace(
        state=state,
        notify_change=notify_change if callable(notify_change) else None,
    )


class CanvasHistoryRecordingService:
    def __init__(self, canvas, history_service=None) -> None:
        self.canvas = canvas
        self.history = history_service

    def push_history(self, command: HistoryCommand) -> None:
        self._push_history(command)

    def _push_history(self, command: HistoryCommand) -> None:
        # The canvas is already mutated when a recorded push starts, so a
        # capture failure (Qt teardown, malformed history state) must run the
        # inverse-only recovery before propagating.
        command_snapshot: HistoryCommandSnapshot | None = None
        after_runtime_snapshot: object | None = None
        try:
            command_snapshot = HistoryCommandSnapshot.capture(command)
            history_snapshot = HistoryAuthoritySnapshot.capture(
                _history_snapshot_service(self.history)
            )
            policy_snapshot = (
                RecordingHistoryPolicySnapshot.capture(history_snapshot)
                if history_snapshot is not None
                else None
            )
            enabled_before_push = getattr(
                getattr(self.history, "state", None),
                "enabled",
                None,
            )
            # This savepoint is the exact already-mutated canvas authority; a
            # push failure restores it before running the command inverse.
            # Lightweight history-only test doubles expose no canvas
            # transaction protocol and keep their inverse-only compatibility.
            try:
                after_runtime_snapshot = capture_history_transaction_for_history(
                    self.canvas,
                    history_service=None,
                    guard_scene_rect=False,
                )
            except BaseException:
                if getattr(self.canvas, "model", None) is not None:
                    raise
                after_runtime_snapshot = None
            else:
                verify = getattr(after_runtime_snapshot, "verify_exact", None)
                initial_errors = tuple(verify()) if callable(verify) else ()
                if initial_errors:
                    if getattr(self.canvas, "model", None) is not None:
                        raise BaseExceptionGroup(
                            "recorded history publication did not capture an "
                            "exact after-runtime",
                            list(initial_errors),
                        )
                    release_history_transaction_for_history(
                        self.canvas,
                        after_runtime_snapshot,
                    )
                    after_runtime_snapshot = None
        except BaseException as capture_error:
            recover_failed_recording_push(
                self.canvas,
                command,
                None,
                capture_error,
                phase="recorded canvas mutation capture",
                command_snapshot=command_snapshot,
            )
            raise
        try:
            push_result = self.history.push(command)
            if push_result is False and enabled_before_push is not False:
                # A push that reports rejection without an explicitly disabled
                # pre-push policy has silently dropped the command; the
                # mutation must roll back.
                raise RuntimeError(
                    "recording history push reported an explicitly disabled "
                    "policy while recording is enabled"
                )
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
