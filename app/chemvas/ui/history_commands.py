from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol, override

from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from chemvas.core.history import (
    HistoryCommand,
    SetAtomPositionsCommand,
    UpdateBondLengthCommand,
    capture_history_transaction_for_command,
    history_transaction_scope,
    release_history_transaction_for_command,
    restore_history_transaction_for_command,
)
from chemvas.domain.transactions import run_rollback_step

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from chemvas.ui.transactions.scene_runtime import SceneRuntimeSnapshot

from chemvas.core.history import HistoryPositionOperations, HistorySmilesOperations
from chemvas.ui.canvas_group_state import CanvasGroupState, CanvasSceneGroup
from chemvas.ui.canvas_scene_items_state import SCENE_ITEM_COLLECTION_ATTRS
from chemvas.ui.transactions.scene_rect import (
    capture_scene_rect_snapshot,
    release_scene_rect_snapshot,
)
from chemvas.ui.transactions.scene_runtime import restore_absolute_snapshots


class HistorySceneItemOperations(Protocol):
    def apply_scene_item_state(self, item: object, state: dict) -> None: ...
    def clear_handles_for_target(self, item: object) -> None: ...
    def refresh_selection_outline(self) -> None: ...
    def capture_scene_runtime(self) -> SceneRuntimeSnapshot: ...


class HistorySelectionGeometryOperations(
    HistorySceneItemOperations, HistoryPositionOperations, Protocol
):
    def blocked_scene_signals(self) -> AbstractContextManager[None]: ...
    def pop_atom_coords_3d(self, atom_id: int) -> object: ...


class HistorySceneCollectionOperations(Protocol):
    def scene_item_collection(self, name: str) -> list[Any]: ...
    def create_scene_items(self, states: list[dict], items: list) -> None: ...
    def restore_scene_items(
        self, items: list, *, after_mutation: Callable[[], None] | None = None
    ) -> None: ...
    def remove_scene_items(self, items: list) -> None: ...


class HistoryGroupOperations(Protocol):
    def group_state(self) -> CanvasGroupState: ...
    def remove_group(self, group_id: int) -> CanvasSceneGroup | None: ...
    def register_group(self, atom_ids: set[int], items: list) -> int: ...
    def restore_group(self, group_id: int, group: CanvasSceneGroup) -> None: ...
    def route_scene_selection_group_changed(self) -> None: ...
    def refresh_selection_outline(self) -> None: ...
    def capture_scene_runtime(self) -> SceneRuntimeSnapshot: ...


class HistoryMarkOperations(HistorySceneItemOperations, Protocol):
    def restore_mark_ownership(
        self,
        marks: dict[int, tuple[object, ...]],
        annotations: dict[int, dict[str, int]],
    ) -> None: ...


class HistoryCalculationPlanOperations(Protocol):
    def set_calculation_plan(self, state: dict[str, object] | None) -> None: ...


class HistoryAtomLabelOperations(HistorySmilesOperations, Protocol):
    def restore_atom_label(
        self, atom_id: int, element: str, explicit_label: bool
    ) -> None: ...


@dataclass(slots=True)
class _GroupStateSnapshot:
    state: CanvasGroupState
    groups_object: dict[int, CanvasSceneGroup]
    groups: dict[int, CanvasSceneGroup]
    next_group_id: int
    expanding: bool


def _group_state_snapshot(operations: HistoryGroupOperations) -> _GroupStateSnapshot:
    state = operations.group_state()
    return _GroupStateSnapshot(
        state=state,
        groups_object=state.groups,
        groups=dict(state.groups),
        next_group_id=state.next_group_id,
        expanding=state.expanding,
    )


def _restore_group_state(snapshot: _GroupStateSnapshot) -> None:
    snapshot.groups_object.clear()
    snapshot.groups_object.update(snapshot.groups)
    snapshot.state.groups = snapshot.groups_object
    snapshot.state.next_group_id = snapshot.next_group_id
    snapshot.state.expanding = snapshot.expanding


@dataclass
class SetAnnotationStyleCommand[StyleState](HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    before_state: StyleState
    after_state: StyleState
    apply_style: Callable[[StyleState], None]

    def _apply(self, operations, state, rollback_state) -> None:
        transaction = capture_history_transaction_for_command(operations)
        try:
            self.apply_style(state)
            release_history_transaction_for_command(operations, transaction)
        except Exception as original_error:
            result = restore_history_transaction_for_command(
                operations, transaction, original_error
            )
            if result.fallback_to_inverse:
                run_rollback_step(
                    original_error,
                    "restoring annotation settings",
                    lambda: self.apply_style(rollback_state),
                )
            raise

    @override
    def undo(self, operations) -> None:
        self._apply(operations, self.before_state, self.after_state)

    @override
    def redo(self, operations) -> None:
        self._apply(operations, self.after_state, self.before_state)


@dataclass
class SetSheetSetupCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    before: tuple[str, str]
    after: tuple[str, str]
    apply_setup: Callable[[str, str], None]

    def _apply(self, operations, state) -> None:
        transaction = capture_history_transaction_for_command(operations)
        try:
            self.apply_setup(*state)
            release_history_transaction_for_command(operations, transaction)
        except Exception as original_error:
            restore_history_transaction_for_command(
                operations, transaction, original_error
            )
            raise

    @override
    def undo(self, operations) -> None:
        self._apply(operations, self.before)

    @override
    def redo(self, operations) -> None:
        self._apply(operations, self.after)


@dataclass
class SetCalculationPlanCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    before_state: dict[str, object] | None
    after_state: dict[str, object] | None

    def _apply(
        self, operations: HistoryCalculationPlanOperations, state, rollback_state
    ) -> None:
        transaction = capture_history_transaction_for_command(operations)
        try:
            operations.set_calculation_plan(state)
            release_history_transaction_for_command(operations, transaction)
        except Exception as original_error:
            result = restore_history_transaction_for_command(
                operations, transaction, original_error
            )
            if result.fallback_to_inverse:
                run_rollback_step(
                    original_error,
                    "restoring the previous calculation plan",
                    lambda: operations.set_calculation_plan(rollback_state),
                )
            raise

    @override
    def undo(self, operations: HistoryCalculationPlanOperations) -> None:
        self._apply(operations, self.before_state, self.after_state)

    @override
    def redo(self, operations: HistoryCalculationPlanOperations) -> None:
        self._apply(operations, self.after_state, self.before_state)


@dataclass
class RebindMarkCommand(HistoryCommand):
    """One explicit transfer; geometry and both electronic owners replay together."""

    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    item: object
    before_state: dict
    after_state: dict
    before_marks: dict[int, tuple[object, ...]]
    after_marks: dict[int, tuple[object, ...]]
    before_annotations: dict[int, dict[str, int]]
    after_annotations: dict[int, dict[str, int]]

    def _apply(self, operations: HistoryMarkOperations, *, undo: bool) -> None:
        transaction = capture_history_transaction_for_command(operations)
        try:
            state = self.before_state if undo else self.after_state
            marks = self.before_marks if undo else self.after_marks
            annotations = self.before_annotations if undo else self.after_annotations
            operations.apply_scene_item_state(self.item, state)
            operations.restore_mark_ownership(marks, annotations)
            operations.refresh_selection_outline()
            release_history_transaction_for_command(operations, transaction)
        except Exception as original_error:
            restore_history_transaction_for_command(
                operations, transaction, original_error
            )
            raise

    @override
    def undo(self, operations: HistoryMarkOperations) -> None:
        self._apply(operations, undo=True)

    @override
    def redo(self, operations: HistoryMarkOperations) -> None:
        self._apply(operations, undo=False)


@dataclass
class UpdateSceneItemCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item: object
    before_state: dict
    after_state: dict

    def _apply(
        self, operations: HistorySceneItemOperations, state: dict, rollback_state: dict
    ) -> None:
        runtime_snapshot = operations.capture_scene_runtime()
        scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            operations.apply_scene_item_state(self.item, state)
            operations.clear_handles_for_target(self.item)
            operations.refresh_selection_outline()
            release_scene_rect_snapshot(scene_rect_snapshot)
        except Exception as original_error:
            run_rollback_step(
                original_error,
                "restoring a scene item's prior state",
                lambda: operations.apply_scene_item_state(self.item, rollback_state),
            )
            run_rollback_step(
                original_error,
                "refreshing the selection outline after a scene-item update",
                lambda: operations.refresh_selection_outline(),
            )
            # Outline refresh clears the old scene items before rebuilding. If
            # that rebuild raises, applying the item state back is insufficient:
            # restore the exact pre-command outline membership/list identity and
            # other selection runtime state as well.
            restore_absolute_snapshots(
                runtime_snapshot, scene_rect_snapshot, original_error
            )
            raise

    @override
    def undo(self, operations: HistorySceneItemOperations) -> None:
        self._apply(operations, self.before_state, self.after_state)

    @override
    def redo(self, operations: HistorySceneItemOperations) -> None:
        self._apply(operations, self.after_state, self.before_state)


@dataclass
class SetSceneGeometryCommand(HistoryCommand):
    """Exact geometry payload; dependent items follow atoms in both directions.

    This is a selected-geometry command, not a savepoint. Failure recovery and
    stack policy still belong to the shared document/history transaction owner.
    """

    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    atom_commands: list[SetAtomPositionsCommand]
    item_commands: list[UpdateSceneItemCommand]

    def _apply_geometry(
        self, operations: HistorySelectionGeometryOperations, *, undo: bool
    ) -> None:
        with history_transaction_scope(operations), operations.blocked_scene_signals():
            atom_commands = reversed(self.atom_commands) if undo else self.atom_commands
            for command in atom_commands:
                positions = (
                    command.before_positions if undo else command.after_positions
                )
                coords = command.before_coords_3d if undo else command.after_coords_3d
                # Our command records the full inventory for its positioned atoms,
                # unlike the general setter's optional partial coordinate update.
                if coords is not None:
                    for atom_id in positions.keys() - coords.keys():
                        operations.pop_atom_coords_3d(atom_id)
                if undo:
                    command.undo(operations)
                else:
                    command.redo(operations)
            item_commands = reversed(self.item_commands) if undo else self.item_commands
            for item_command in item_commands:
                state = item_command.before_state if undo else item_command.after_state
                operations.apply_scene_item_state(item_command.item, state)
                operations.clear_handles_for_target(item_command.item)
        operations.refresh_selection_outline()

    def _apply(
        self, operations: HistorySelectionGeometryOperations, *, undo: bool
    ) -> None:
        transaction = capture_history_transaction_for_command(operations)
        try:
            self._apply_geometry(operations, undo=undo)
            release_history_transaction_for_command(operations, transaction)
        except Exception as original_error:
            result = restore_history_transaction_for_command(
                operations, transaction, original_error
            )
            if result.fallback_to_inverse:
                run_rollback_step(
                    original_error,
                    "restoring the previous selection geometry",
                    lambda: self._apply_geometry(operations, undo=not undo),
                )
            raise

    @override
    def undo(self, operations: HistorySelectionGeometryOperations) -> None:
        self._apply(operations, undo=True)

    @override
    def redo(self, operations: HistorySelectionGeometryOperations) -> None:
        self._apply(operations, undo=False)


@dataclass
class SetBondLengthGeometryCommand(SetSceneGeometryCommand):
    """Restore style before atom and exact dependent-mark geometry both ways."""

    length_command: UpdateBondLengthCommand

    @override
    def _apply_geometry(self, operations, *, undo: bool) -> None:
        if undo:
            self.length_command.undo(operations)
        else:
            self.length_command.redo(operations)
        super()._apply_geometry(operations, undo=undo)


@dataclass
class AddSceneItemsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item_states: list[dict]
    items: list = field(default_factory=list)

    @override
    def redo(self, operations: HistorySceneCollectionOperations) -> None:
        if not self.items:
            operations.create_scene_items(self.item_states, self.items)
            return
        operations.restore_scene_items(self.items)

    @override
    def undo(self, operations: HistorySceneCollectionOperations) -> None:
        operations.remove_scene_items(self.items)


@dataclass
class _DeletedSceneItemOrder:
    """History payload for ordering only; rollback remains in scene_runtime."""

    collections: dict[str, list[tuple[int, Any]]]
    siblings: list[list[QGraphicsItem]]

    @classmethod
    def capture(
        cls, operations: HistorySceneCollectionOperations, items: list
    ) -> _DeletedSceneItemOrder:
        item_ids = {id(item) for item in items}
        collections = {
            name: [
                (index, item)
                for index, item in enumerate(operations.scene_item_collection(name))
                if id(item) in item_ids
            ]
            for name in SCENE_ITEM_COLLECTION_ATTRS
            if name != "selected_notes"
        }
        cohorts: set[tuple[QGraphicsScene, QGraphicsItem | None, float]] = set()
        for item in items:
            if not isinstance(item, QGraphicsItem):
                continue
            scene = item.scene()
            if scene is not None:
                key = (scene, item.parentItem(), item.zValue())
                cohorts.add(key)
        siblings = []
        for scene, parent, z_value in cohorts:
            siblings.append(
                [
                    item
                    for item in scene.items(Qt.SortOrder.AscendingOrder)
                    if item.parentItem() is parent and item.zValue() == z_value
                ]
            )
        return cls(collections, siblings)

    def restore(self, operations: HistorySceneCollectionOperations) -> None:
        for name, entries in self.collections.items():
            collection = operations.scene_item_collection(name)
            for _, item in entries:
                collection.remove(item)
            for index, item in entries:
                collection.insert(index, item)
        for siblings in self.siblings:
            attached = [
                item
                for item in siblings
                if not sip.isdeleted(item) and item.scene() is not None
            ]
            for index in range(len(attached) - 2, -1, -1):
                attached[index].stackBefore(attached[index + 1])


@dataclass
class DeleteSceneItemsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item_states: list[dict]
    items: list = field(default_factory=list)
    _order: _DeletedSceneItemOrder | None = field(default=None, repr=False)

    @classmethod
    def capture(
        cls,
        operations: HistorySceneCollectionOperations,
        item_states: list[dict],
        items: list,
    ) -> DeleteSceneItemsCommand:
        """Capture ordering before the first item is detached."""
        return cls(
            item_states, items, _DeletedSceneItemOrder.capture(operations, items)
        )

    @override
    def redo(self, operations: HistorySceneCollectionOperations) -> None:
        operations.remove_scene_items(self.items)

    @override
    def undo(self, operations: HistorySceneCollectionOperations) -> None:
        if not self.items:
            operations.create_scene_items(self.item_states, self.items)
            return
        operations.restore_scene_items(
            self.items,
            after_mutation=partial(self._order.restore, operations)
            if self._order
            else None,
        )


def _run_group_state_transaction(
    operations: HistoryGroupOperations,
    apply_change,
    *,
    outline_rollback_note: str,
    on_rollback=None,
) -> None:
    """The capture / apply / roll-back scaffold every group command shares.

    The rollback order is the contract, and it is the reason this exists once
    rather than four times: group state first, then the command's own
    compensation, then the selection outline, then the absolute scene/runtime
    snapshot, and the scene rect last. Failures inside those steps are
    recorded as notes on the original error in that same order.
    """

    snapshot = _group_state_snapshot(operations)
    runtime_snapshot = operations.capture_scene_runtime()
    scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
    try:
        apply_change()
        # Pasted scene items regain selection before their group is restored.
        # Membership changes emit no Qt selectionChanged signal; reconcile now
        # so the next drag cannot move a ring while leaving its sidechain behind.
        operations.route_scene_selection_group_changed()
        # The dashed group box is part of the selection outline; without a
        # refresh, undo/redo would leave a stale box (and its hit-test area).
        operations.refresh_selection_outline()
        release_scene_rect_snapshot(scene_rect_snapshot)
    except Exception as original_error:
        run_rollback_step(
            original_error,
            "restoring group state",
            lambda: _restore_group_state(snapshot),
        )
        if on_rollback is not None:
            on_rollback()
        run_rollback_step(
            original_error,
            outline_rollback_note,
            lambda: operations.refresh_selection_outline(),
        )
        restore_absolute_snapshots(
            runtime_snapshot, scene_rect_snapshot, original_error
        )
        raise


@dataclass
class GroupSceneItemsCommand(HistoryCommand):
    atom_ids: set[int]
    items: list
    absorbed: list[tuple[int, CanvasSceneGroup]] = field(default_factory=list)
    group_id: int | None = None

    @override
    def redo(self, operations: HistoryGroupOperations) -> None:
        previous_group_id = self.group_id

        def apply_change() -> None:
            for absorbed_id, _ in self.absorbed:
                operations.remove_group(absorbed_id)
            if self.group_id is None:
                self.group_id = operations.register_group(self.atom_ids, self.items)
            else:
                operations.restore_group(
                    self.group_id,
                    CanvasSceneGroup(set(self.atom_ids), list(self.items)),
                )

        def restore_group_id() -> None:
            # Only this command mints an id, so only this command has one to
            # give back when the mint half-succeeded.
            self.group_id = previous_group_id

        _run_group_state_transaction(
            operations,
            apply_change,
            outline_rollback_note="refreshing the selection outline after grouping",
            on_rollback=restore_group_id,
        )

    @override
    def undo(self, operations: HistoryGroupOperations) -> None:
        def apply_change() -> None:
            if self.group_id is not None:
                operations.remove_group(self.group_id)
            for absorbed_id, group in self.absorbed:
                operations.restore_group(absorbed_id, group)

        _run_group_state_transaction(
            operations,
            apply_change,
            outline_rollback_note="refreshing the selection outline after ungrouping",
        )


@dataclass
class UngroupSceneItemsCommand(HistoryCommand):
    removed: list[tuple[int, CanvasSceneGroup]]

    @override
    def redo(self, operations: HistoryGroupOperations) -> None:
        def apply_change() -> None:
            for group_id, _ in self.removed:
                operations.remove_group(group_id)

        _run_group_state_transaction(
            operations,
            apply_change,
            outline_rollback_note="refreshing the selection outline after ungrouping",
        )

    @override
    def undo(self, operations: HistoryGroupOperations) -> None:
        def apply_change() -> None:
            for group_id, group in self.removed:
                operations.restore_group(group_id, group)

        _run_group_state_transaction(
            operations,
            apply_change,
            outline_rollback_note="refreshing the selection outline after grouping",
        )


@dataclass(kw_only=True)
class ChangeAtomLabelCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    atom_id: int
    before_element: str
    after_element: str
    before_explicit_label: bool
    after_explicit_label: bool
    before_smiles_input: str | None
    after_smiles_input: str | None

    def _apply(
        self,
        operations: HistoryAtomLabelOperations,
        element: str,
        explicit_label: bool,
        smiles_input: str | None,
        rollback_element: str,
        rollback_explicit_label: bool,
        rollback_smiles_input: str | None,
    ) -> None:
        transaction = capture_history_transaction_for_command(operations)
        try:
            operations.restore_atom_label(self.atom_id, element, explicit_label)
            operations.set_last_smiles_input_for_history(smiles_input)
            release_history_transaction_for_command(operations, transaction)
        except Exception as original_error:
            result = restore_history_transaction_for_command(
                operations, transaction, original_error
            )
            if result.fallback_to_inverse:
                run_rollback_step(
                    original_error,
                    "restoring the prior atom label",
                    lambda: operations.restore_atom_label(
                        self.atom_id, rollback_element, rollback_explicit_label
                    ),
                )
                run_rollback_step(
                    original_error,
                    "restoring the prior SMILES input",
                    lambda: operations.set_last_smiles_input_for_history(
                        rollback_smiles_input
                    ),
                )
            raise

    @override
    def undo(self, operations: HistoryAtomLabelOperations) -> None:
        self._apply(
            operations,
            self.before_element,
            self.before_explicit_label,
            self.before_smiles_input,
            self.after_element,
            self.after_explicit_label,
            self.after_smiles_input,
        )

    @override
    def redo(self, operations: HistoryAtomLabelOperations) -> None:
        self._apply(
            operations,
            self.after_element,
            self.after_explicit_label,
            self.after_smiles_input,
            self.before_element,
            self.before_explicit_label,
            self.before_smiles_input,
        )


__all__ = [
    "AddSceneItemsCommand",
    "ChangeAtomLabelCommand",
    "DeleteSceneItemsCommand",
    "GroupSceneItemsCommand",
    "HistoryAtomLabelOperations",
    "HistoryCalculationPlanOperations",
    "HistoryGroupOperations",
    "HistoryMarkOperations",
    "HistorySceneCollectionOperations",
    "HistorySceneItemOperations",
    "HistorySelectionGeometryOperations",
    "SetAnnotationStyleCommand",
    "SetCalculationPlanCommand",
    "SetSceneGeometryCommand",
    "SetSheetSetupCommand",
    "UngroupSceneItemsCommand",
    "UpdateSceneItemCommand",
]
