from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, override

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
from chemvas.ui.atom_coords_access import pop_atom_coords_3d_for
from chemvas.ui.atom_label_access import add_or_update_atom_label
from chemvas.ui.canvas_calculation_plan_state import set_calculation_plan_for
from chemvas.ui.canvas_group_state import (
    CanvasSceneGroup,
    group_state_for,
    register_group_for,
    remove_group_for,
    restore_group_for,
)
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import (
    atom_annotations_for,
)
from chemvas.ui.canvas_scene_items_state import (
    SCENE_ITEM_COLLECTION_ATTRS,
    scene_item_collection_for,
)
from chemvas.ui.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.canvas_view_event_router import route_scene_selection_group_changed
from chemvas.ui.handle_overlay_access import clear_handles_for
from chemvas.ui.move_access import (
    refresh_selection_outline_for_canvas,
)
from chemvas.ui.scene_item_access import (
    apply_scene_item_state as _apply_scene_item_state,
)
from chemvas.ui.scene_item_access import (
    remove_scene_item as _remove_scene_item,
)
from chemvas.ui.scene_item_access import (
    restore_scene_item as _restore_scene_item,
)
from chemvas.ui.scene_signal_blocking import blocked_scene_signals
from chemvas.ui.transactions.scene_rect import (
    capture_scene_rect_snapshot,
    release_scene_rect_snapshot,
)
from chemvas.ui.transactions.scene_runtime import (
    capture_scene_runtime,
    create_scene_items_atomically,
    mutate_existing_scene_items_atomically,
    restore_absolute_snapshots,
)


@dataclass(slots=True)
class _GroupStateSnapshot:
    state: Any
    groups_object: dict[int, CanvasSceneGroup]
    groups: dict[int, CanvasSceneGroup]
    next_group_id: int
    expanding: bool


def _group_state_snapshot(canvas) -> _GroupStateSnapshot:
    state = group_state_for(canvas)
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


def _clear_handles_for_target(canvas, item) -> None:
    """Drop handles that were placed from the geometry this command replaced.

    A lightweight canvas without a runtime container is simply a canvas
    with no handles rather than an error inside an undo.
    """
    runtime_state = getattr(canvas, "runtime_state", None)
    handle_state = getattr(runtime_state, "handle_state", None)
    if handle_state is None or getattr(handle_state, "target", None) is not item:
        return
    clear_handles_for(canvas)


@dataclass
class SetAnnotationStyleCommand[StyleState](HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    before_state: StyleState
    after_state: StyleState
    apply_style: Callable[[Any, StyleState], None]

    def _apply(self, canvas, state, rollback_state) -> None:
        transaction = capture_history_transaction_for_command(canvas)
        try:
            self.apply_style(canvas, state)
            release_history_transaction_for_command(canvas, transaction)
        except Exception as original_error:
            result = restore_history_transaction_for_command(
                canvas, transaction, original_error
            )
            if result.fallback_to_inverse:
                run_rollback_step(
                    original_error,
                    "restoring annotation settings",
                    lambda: self.apply_style(canvas, rollback_state),
                )
            raise

    @override
    def undo(self, canvas) -> None:
        self._apply(canvas, self.before_state, self.after_state)

    @override
    def redo(self, canvas) -> None:
        self._apply(canvas, self.after_state, self.before_state)


@dataclass
class SetSheetSetupCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    before: tuple[str, str]
    after: tuple[str, str]
    apply_setup: Callable[[Any, str, str], None]

    def _apply(self, canvas, state) -> None:
        transaction = capture_history_transaction_for_command(canvas)
        try:
            self.apply_setup(canvas, *state)
            release_history_transaction_for_command(canvas, transaction)
        except Exception as original_error:
            restore_history_transaction_for_command(canvas, transaction, original_error)
            raise

    @override
    def undo(self, canvas) -> None:
        self._apply(canvas, self.before)

    @override
    def redo(self, canvas) -> None:
        self._apply(canvas, self.after)


@dataclass
class SetCalculationPlanCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    before_state: dict[str, object] | None
    after_state: dict[str, object] | None

    def _apply(self, canvas, state, rollback_state) -> None:
        transaction = capture_history_transaction_for_command(canvas)
        try:
            set_calculation_plan_for(canvas, state)
            release_history_transaction_for_command(canvas, transaction)
        except Exception as original_error:
            result = restore_history_transaction_for_command(
                canvas, transaction, original_error
            )
            if result.fallback_to_inverse:
                run_rollback_step(
                    original_error,
                    "restoring the previous calculation plan",
                    lambda: set_calculation_plan_for(canvas, rollback_state),
                )
            raise

    @override
    def undo(self, canvas) -> None:
        self._apply(canvas, self.before_state, self.after_state)

    @override
    def redo(self, canvas) -> None:
        self._apply(canvas, self.after_state, self.before_state)


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

    def _apply(self, canvas, *, undo: bool) -> None:
        transaction = capture_history_transaction_for_command(canvas)
        try:
            state = self.before_state if undo else self.after_state
            marks = self.before_marks if undo else self.after_marks
            annotations = self.before_annotations if undo else self.after_annotations
            _apply_scene_item_state(canvas, self.item, state)
            registry = mark_registry_for(canvas)
            model_annotations = atom_annotations_for(canvas)
            for atom_id, items in marks.items():
                if items:
                    registry.by_atom.setdefault(atom_id, [])[:] = items
                else:
                    registry.by_atom.pop(atom_id, None)
                if atom_id in annotations:
                    model_annotations[atom_id] = dict(annotations[atom_id])
                else:
                    model_annotations.pop(atom_id, None)
            refresh_selection_outline_for_canvas(canvas)
            release_history_transaction_for_command(canvas, transaction)
        except Exception as original_error:
            restore_history_transaction_for_command(canvas, transaction, original_error)
            raise

    @override
    def undo(self, canvas) -> None:
        self._apply(canvas, undo=True)

    @override
    def redo(self, canvas) -> None:
        self._apply(canvas, undo=False)


@dataclass
class UpdateSceneItemCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item: object
    before_state: dict
    after_state: dict

    def _apply(self, canvas, state: dict, rollback_state: dict) -> None:
        runtime_snapshot = capture_scene_runtime(canvas)
        scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            _apply_scene_item_state(canvas, self.item, state)
            _clear_handles_for_target(canvas, self.item)
            refresh_selection_outline_for_canvas(canvas)
            release_scene_rect_snapshot(scene_rect_snapshot)
        except Exception as original_error:
            run_rollback_step(
                original_error,
                "restoring a scene item's prior state",
                lambda: _apply_scene_item_state(canvas, self.item, rollback_state),
            )
            run_rollback_step(
                original_error,
                "refreshing the selection outline after a scene-item update",
                lambda: refresh_selection_outline_for_canvas(canvas),
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
    def undo(self, canvas) -> None:
        self._apply(canvas, self.before_state, self.after_state)

    @override
    def redo(self, canvas) -> None:
        self._apply(canvas, self.after_state, self.before_state)


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

    def _apply_geometry(self, canvas, *, undo: bool) -> None:
        with history_transaction_scope(canvas), blocked_scene_signals(canvas.scene()):
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
                        pop_atom_coords_3d_for(canvas, atom_id)
                if undo:
                    command.undo(canvas)
                else:
                    command.redo(canvas)
            item_commands = reversed(self.item_commands) if undo else self.item_commands
            for item_command in item_commands:
                state = item_command.before_state if undo else item_command.after_state
                _apply_scene_item_state(canvas, item_command.item, state)
                _clear_handles_for_target(canvas, item_command.item)
        refresh_selection_outline_for_canvas(canvas)

    def _apply(self, canvas, *, undo: bool) -> None:
        transaction = capture_history_transaction_for_command(canvas)
        try:
            self._apply_geometry(canvas, undo=undo)
            release_history_transaction_for_command(canvas, transaction)
        except Exception as original_error:
            result = restore_history_transaction_for_command(
                canvas, transaction, original_error
            )
            if result.fallback_to_inverse:
                run_rollback_step(
                    original_error,
                    "restoring the previous selection geometry",
                    lambda: self._apply_geometry(canvas, undo=not undo),
                )
            raise

    @override
    def undo(self, canvas) -> None:
        self._apply(canvas, undo=True)

    @override
    def redo(self, canvas) -> None:
        self._apply(canvas, undo=False)


@dataclass
class SetBondLengthGeometryCommand(SetSceneGeometryCommand):
    """Restore style before atom and exact dependent-mark geometry both ways."""

    length_command: UpdateBondLengthCommand

    @override
    def _apply_geometry(self, canvas, *, undo: bool) -> None:
        if undo:
            self.length_command.undo(canvas)
        else:
            self.length_command.redo(canvas)
        super()._apply_geometry(canvas, undo=undo)


@dataclass
class AddSceneItemsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item_states: list[dict]
    items: list = field(default_factory=list)

    @override
    def redo(self, canvas) -> None:
        if not self.items:
            create_scene_items_atomically(canvas, self.item_states, self.items)
            return
        mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _restore_scene_item,
            unknown_was_attached=False,
        )

    @override
    def undo(self, canvas) -> None:
        mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _remove_scene_item,
            unknown_was_attached=True,
        )


@dataclass
class _DeletedSceneItemOrder:
    """History payload for ordering only; rollback remains in scene_runtime."""

    collections: dict[str, list[tuple[int, Any]]]
    siblings: list[list[QGraphicsItem]]

    @classmethod
    def capture(cls, canvas, items: list) -> _DeletedSceneItemOrder:
        item_ids = {id(item) for item in items}
        collections = {
            name: [
                (index, item)
                for index, item in enumerate(scene_item_collection_for(canvas, name))
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

    def restore(self, canvas) -> None:
        for name, entries in self.collections.items():
            collection = scene_item_collection_for(canvas, name)
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
        cls, canvas, item_states: list[dict], items: list
    ) -> DeleteSceneItemsCommand:
        """Capture ordering before the first item is detached."""
        return cls(item_states, items, _DeletedSceneItemOrder.capture(canvas, items))

    @override
    def redo(self, canvas) -> None:
        mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _remove_scene_item,
            unknown_was_attached=True,
        )

    @override
    def undo(self, canvas) -> None:
        if not self.items:
            create_scene_items_atomically(canvas, self.item_states, self.items)
            return
        mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _restore_scene_item,
            unknown_was_attached=False,
            after_mutation=partial(self._order.restore, canvas)
            if self._order
            else None,
        )


def _run_group_state_transaction(
    canvas,
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

    snapshot = _group_state_snapshot(canvas)
    runtime_snapshot = capture_scene_runtime(canvas)
    scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
    try:
        apply_change()
        # Pasted scene items regain selection before their group is restored.
        # Membership changes emit no Qt selectionChanged signal; reconcile now
        # so the next drag cannot move a ring while leaving its sidechain behind.
        route_scene_selection_group_changed(canvas)
        # The dashed group box is part of the selection outline; without a
        # refresh, undo/redo would leave a stale box (and its hit-test area).
        refresh_selection_outline_for_canvas(canvas)
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
            lambda: refresh_selection_outline_for_canvas(canvas),
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
    def redo(self, canvas) -> None:
        previous_group_id = self.group_id

        def apply_change() -> None:
            for absorbed_id, _ in self.absorbed:
                remove_group_for(canvas, absorbed_id)
            if self.group_id is None:
                self.group_id = register_group_for(canvas, self.atom_ids, self.items)
            else:
                restore_group_for(
                    canvas,
                    self.group_id,
                    CanvasSceneGroup(set(self.atom_ids), list(self.items)),
                )

        def restore_group_id() -> None:
            # Only this command mints an id, so only this command has one to
            # give back when the mint half-succeeded.
            self.group_id = previous_group_id

        _run_group_state_transaction(
            canvas,
            apply_change,
            outline_rollback_note="refreshing the selection outline after grouping",
            on_rollback=restore_group_id,
        )

    @override
    def undo(self, canvas) -> None:
        def apply_change() -> None:
            if self.group_id is not None:
                remove_group_for(canvas, self.group_id)
            for absorbed_id, group in self.absorbed:
                restore_group_for(canvas, absorbed_id, group)

        _run_group_state_transaction(
            canvas,
            apply_change,
            outline_rollback_note="refreshing the selection outline after ungrouping",
        )


@dataclass
class UngroupSceneItemsCommand(HistoryCommand):
    removed: list[tuple[int, CanvasSceneGroup]]

    @override
    def redo(self, canvas) -> None:
        def apply_change() -> None:
            for group_id, _ in self.removed:
                remove_group_for(canvas, group_id)

        _run_group_state_transaction(
            canvas,
            apply_change,
            outline_rollback_note="refreshing the selection outline after ungrouping",
        )

    @override
    def undo(self, canvas) -> None:
        def apply_change() -> None:
            for group_id, group in self.removed:
                restore_group_for(canvas, group_id, group)

        _run_group_state_transaction(
            canvas,
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
        canvas,
        element: str,
        explicit_label: bool,
        smiles_input: str | None,
        rollback_element: str,
        rollback_explicit_label: bool,
        rollback_smiles_input: str | None,
    ) -> None:
        transaction = capture_history_transaction_for_command(canvas)
        try:
            add_or_update_atom_label(
                canvas,
                self.atom_id,
                element,
                clear_smiles=False,
                record=False,
                allow_merge=False,
                show_carbon=explicit_label,
                literal_label=explicit_label,
            )
            set_last_smiles_input_for(canvas, smiles_input)
            release_history_transaction_for_command(canvas, transaction)
        except Exception as original_error:
            result = restore_history_transaction_for_command(
                canvas, transaction, original_error
            )
            if result.fallback_to_inverse:
                run_rollback_step(
                    original_error,
                    "restoring the prior atom label",
                    lambda: add_or_update_atom_label(
                        canvas,
                        self.atom_id,
                        rollback_element,
                        clear_smiles=False,
                        record=False,
                        allow_merge=False,
                        show_carbon=rollback_explicit_label,
                        literal_label=rollback_explicit_label,
                    ),
                )
                run_rollback_step(
                    original_error,
                    "restoring the prior SMILES input",
                    lambda: set_last_smiles_input_for(canvas, rollback_smiles_input),
                )
            raise

    @override
    def undo(self, canvas) -> None:
        self._apply(
            canvas,
            self.before_element,
            self.before_explicit_label,
            self.before_smiles_input,
            self.after_element,
            self.after_explicit_label,
            self.after_smiles_input,
        )

    @override
    def redo(self, canvas) -> None:
        self._apply(
            canvas,
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
    "SetAnnotationStyleCommand",
    "SetCalculationPlanCommand",
    "SetSceneGeometryCommand",
    "SetSheetSetupCommand",
    "UngroupSceneItemsCommand",
    "UpdateSceneItemCommand",
]
