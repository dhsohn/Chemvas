from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import Any

from chemvas.core.history import (
    HistoryCommand,
    capture_history_transaction_for_command,
    release_history_transaction_for_command,
    restore_history_transaction_for_command,
)
from chemvas.domain.transactions import (
    add_recovery_error_note as _add_rollback_error_note,
)
from chemvas.ui.atom_coords_access import atom_coords_3d_for_id
from chemvas.ui.atom_label_access import add_or_update_atom_label
from chemvas.ui.canvas_group_state import (
    CanvasSceneGroup,
    group_state_for,
    register_group_for,
    remove_group_for,
    restore_group_for,
)
from chemvas.ui.canvas_model_access import atom_for_id, bond_for_id
from chemvas.ui.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.history_atom_position_restore import (
    set_atom_positions_for_history as _set_atom_positions_for_history,
)
from chemvas.ui.move_access import (
    move_item_for,
    refresh_selection_outline_for_canvas,
)
from chemvas.ui.scene_item_access import (
    apply_scene_item_state as _apply_scene_item_state,
)
from chemvas.ui.scene_item_access import (
    item_is_in_canvas_scene as _item_is_in_canvas_scene,
)
from chemvas.ui.scene_item_access import (
    remove_scene_item as _remove_scene_item,
)
from chemvas.ui.scene_item_access import (
    restore_scene_item as _restore_scene_item,
)
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.transactions.scene_runtime import (
    capture_scene_rect_snapshot,
    capture_scene_runtime,
    create_scene_items_atomically,
    mutate_existing_scene_items_atomically,
    release_scene_rect_snapshot,
    restore_scene_rect_snapshot,
    restore_scene_runtime,
    run_rollback_step,
)

_MISSING_SNAPSHOT_ATTRIBUTE = object()


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


def _active_handle_position_snapshots(canvas) -> list[tuple[object, object]]:
    runtime_state = getattr(canvas, "runtime_state", None)
    handle_state = getattr(runtime_state, "handle_state", None)
    if handle_state is None:
        handle_state = getattr(canvas, "handle_state", None)
    handles = getattr(handle_state, "active_handles", ())
    snapshots: list[tuple[object, object]] = []
    for handle in handles:
        position_method = getattr(handle, "pos", None)
        if not callable(position_method):
            continue
        try:
            snapshots.append((handle, position_method()))
        except RuntimeError:
            continue
    return snapshots


def _restore_active_handle_positions(
    snapshots: list[tuple[object, object]],
    *,
    original_error: BaseException,
) -> None:
    for handle, position in snapshots:
        set_position = getattr(handle, "setPos", None)
        if not callable(set_position):
            continue
        run_rollback_step(
            original_error,
            "restoring an active handle position",
            partial(set_position, position),
        )


_UNAVAILABLE_ITEM_VALUE = object()


@dataclass(slots=True)
class _MoveItemSnapshot:
    item: object
    state: dict
    position: object
    data_1: object
    data_2: object
    atom_positions: dict[int, tuple[float, float]]
    atom_coords_3d: dict[int, tuple[float, float, float]]


def _move_item_atom_ids(canvas, item) -> set[int]:
    data_method = getattr(item, "data", None)
    if not callable(data_method):
        return set()
    try:
        kind = data_method(0)
        item_id = data_method(1)
    except RuntimeError:
        return set()
    if kind == "atom" and isinstance(item_id, int):
        return {item_id}
    if kind != "bond" or not isinstance(item_id, int):
        return set()
    try:
        bond = bond_for_id(canvas, item_id)
    except (AttributeError, RuntimeError):
        return set()
    if bond is None:
        return set()
    return {
        atom_id
        for atom_id in (getattr(bond, "a", None), getattr(bond, "b", None))
        if isinstance(atom_id, int)
    }


def _model_move_snapshots(
    canvas,
    item,
) -> tuple[
    dict[int, tuple[float, float]],
    dict[int, tuple[float, float, float]],
]:
    positions: dict[int, tuple[float, float]] = {}
    coords_3d: dict[int, tuple[float, float, float]] = {}
    for atom_id in _move_item_atom_ids(canvas, item):
        try:
            atom = atom_for_id(canvas, atom_id)
        except (AttributeError, RuntimeError):
            continue
        if atom is None:
            continue
        positions[atom_id] = (float(atom.x), float(atom.y))
        try:
            coord = atom_coords_3d_for_id(canvas, atom_id)
        except (AttributeError, RuntimeError):
            coord = None
        if coord is not None:
            coords_3d[atom_id] = coord
    return positions, coords_3d


def _move_item_snapshot(canvas, item) -> _MoveItemSnapshot:
    position: object = _UNAVAILABLE_ITEM_VALUE
    position_method = getattr(item, "pos", None)
    if callable(position_method):
        try:
            position = position_method()
        except RuntimeError:
            pass

    data_values: list[object] = []
    data_method = getattr(item, "data", None)
    for index in (1, 2):
        value: object = _UNAVAILABLE_ITEM_VALUE
        if callable(data_method):
            try:
                current = data_method(index)
                value = dict(current) if isinstance(current, dict) else current
            except RuntimeError:
                pass
        data_values.append(value)

    atom_positions, atom_coords_3d = _model_move_snapshots(canvas, item)
    return _MoveItemSnapshot(
        item=item,
        state=scene_item_state_for(canvas, item),
        position=position,
        data_1=data_values[0],
        data_2=data_values[1],
        atom_positions=atom_positions,
        atom_coords_3d=atom_coords_3d,
    )


def _restore_raw_move_item_state(
    snapshot: _MoveItemSnapshot,
    *,
    original_error: BaseException,
) -> bool:
    restored = False
    if snapshot.position is not _UNAVAILABLE_ITEM_VALUE:
        set_position = getattr(snapshot.item, "setPos", None)
        if callable(set_position):
            try:
                set_position(snapshot.position)
                restored = True
            except Exception as rollback_error:
                _add_rollback_error_note(
                    original_error,
                    rollback_error,
                    phase="restoring a moved item's raw position",
                )

    set_data = getattr(snapshot.item, "setData", None)
    if not callable(set_data):
        return restored
    for index, value in ((1, snapshot.data_1), (2, snapshot.data_2)):
        if value is _UNAVAILABLE_ITEM_VALUE:
            continue
        try:
            set_data(index, value)
            restored = True
        except Exception as rollback_error:
            _add_rollback_error_note(
                original_error,
                rollback_error,
                phase=f"restoring a moved item's raw data slot {index}",
            )
    return restored


@dataclass
class MoveItemsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    items: list
    dx: float
    dy: float

    def _apply(self, canvas, dx: float, dy: float) -> None:
        attempted: list[_MoveItemSnapshot] = []
        transaction = capture_history_transaction_for_command(canvas)
        handle_snapshots: list[tuple[object, object]] = []
        try:
            snapshots = [
                _move_item_snapshot(canvas, item)
                for item in self.items
                if item is not None and _item_is_in_canvas_scene(canvas, item)
            ]
            handle_snapshots = _active_handle_position_snapshots(canvas)
            for snapshot in snapshots:
                attempted.append(snapshot)
                move_item_for(canvas, snapshot.item, dx, dy, update_selection=False)
            refresh_selection_outline_for_canvas(canvas)
            release_history_transaction_for_command(canvas, transaction)
        except Exception as original_error:
            atom_positions: dict[int, tuple[float, float]] = {}
            atom_coords_3d: dict[int, tuple[float, float, float]] = {}
            for snapshot in attempted:
                atom_positions.update(snapshot.atom_positions)
                atom_coords_3d.update(snapshot.atom_coords_3d)
            if atom_positions:
                # Atom and bond moves mutate model coordinates, bound marks,
                # 3D coordinates, the spatial index, bonds, and ring fills in
                # addition to the grabbed graphics item. Restore those absolute
                # savepoints before normalizing each graphics item below.
                run_rollback_step(
                    original_error,
                    "restoring absolute atom positions after a move",
                    lambda: _set_atom_positions_for_history(
                        canvas,
                        atom_positions,
                        update_selection=False,
                        coords_3d=atom_coords_3d or None,
                    ),
                )
            for snapshot in reversed(attempted):
                raw_restored = _restore_raw_move_item_state(
                    snapshot,
                    original_error=original_error,
                )
                if snapshot.state:
                    try:
                        _apply_scene_item_state(canvas, snapshot.item, snapshot.state)
                        continue
                    except Exception as rollback_error:
                        _add_rollback_error_note(
                            original_error,
                            rollback_error,
                            phase="canonically restoring a moved scene item",
                        )
                        # Canonical apply can mutate before raising. Reapply the
                        # raw savepoint last so its partial state cannot leak.
                        raw_restored = (
                            _restore_raw_move_item_state(
                                snapshot,
                                original_error=original_error,
                            )
                            or raw_restored
                        )
                if raw_restored:
                    continue
                run_rollback_step(
                    original_error,
                    "inversely moving a scene item",
                    partial(
                        move_item_for,
                        canvas,
                        snapshot.item,
                        -dx,
                        -dy,
                        update_selection=False,
                    ),
                )
            _restore_active_handle_positions(
                handle_snapshots,
                original_error=original_error,
            )
            run_rollback_step(
                original_error,
                "refreshing the selection outline after a move",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            # A bulk position setter can restore one mutable Atom and then
            # terminate before later atoms, labels, rings, or 3D coordinates.
            # Make the full pre-command transaction savepoint authoritative
            # after every local best-effort repair.
            restore_result = run_rollback_step(
                original_error,
                "restoring the exact move transaction",
                partial(
                    restore_history_transaction_for_command,
                    canvas,
                    transaction,
                    original_error,
                ),
            )
            if restore_result is not None:
                for exact_restore_error in restore_result.errors:
                    _add_rollback_error_note(
                        original_error,
                        exact_restore_error,
                        phase="restoring the exact move transaction",
                    )
            raise

    def undo(self, canvas) -> None:
        self._apply(canvas, -self.dx, -self.dy)

    def redo(self, canvas) -> None:
        self._apply(canvas, self.dx, self.dy)


@dataclass
class UpdateSceneItemCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item: object
    before_state: dict
    after_state: dict

    def _apply(self, canvas, state: dict, rollback_state: dict) -> None:
        runtime_snapshot = capture_scene_runtime(canvas, strict=True)
        scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            _apply_scene_item_state(canvas, self.item, state)
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
            run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    restore_scene_runtime,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise

    def undo(self, canvas) -> None:
        self._apply(canvas, self.before_state, self.after_state)

    def redo(self, canvas) -> None:
        self._apply(canvas, self.after_state, self.before_state)


@dataclass
class AddSceneItemsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item_states: list[dict]
    items: list = field(default_factory=list)

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

    def undo(self, canvas) -> None:
        mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _remove_scene_item,
            unknown_was_attached=True,
        )


@dataclass
class DeleteSceneItemsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item_states: list[dict]
    items: list = field(default_factory=list)

    def redo(self, canvas) -> None:
        mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _remove_scene_item,
            unknown_was_attached=True,
        )

    def undo(self, canvas) -> None:
        if not self.items:
            create_scene_items_atomically(canvas, self.item_states, self.items)
            return
        mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _restore_scene_item,
            unknown_was_attached=False,
        )


@dataclass
class GroupSceneItemsCommand(HistoryCommand):
    atom_ids: set[int]
    items: list
    absorbed: list[tuple[int, CanvasSceneGroup]] = field(default_factory=list)
    group_id: int | None = None

    def redo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = capture_scene_runtime(canvas, strict=True)
        previous_group_id = self.group_id
        scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
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
            self.group_id = previous_group_id
            run_rollback_step(
                original_error,
                "refreshing the selection outline after grouping",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    restore_scene_runtime,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise

    def undo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = capture_scene_runtime(canvas, strict=True)
        scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            if self.group_id is not None:
                remove_group_for(canvas, self.group_id)
            for absorbed_id, group in self.absorbed:
                restore_group_for(canvas, absorbed_id, group)
            refresh_selection_outline_for_canvas(canvas)
            release_scene_rect_snapshot(scene_rect_snapshot)
        except Exception as original_error:
            run_rollback_step(
                original_error,
                "restoring group state",
                lambda: _restore_group_state(snapshot),
            )
            run_rollback_step(
                original_error,
                "refreshing the selection outline after ungrouping",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    restore_scene_runtime,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise


@dataclass
class UngroupSceneItemsCommand(HistoryCommand):
    removed: list[tuple[int, CanvasSceneGroup]]

    def redo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = capture_scene_runtime(canvas, strict=True)
        scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            for group_id, _ in self.removed:
                remove_group_for(canvas, group_id)
            refresh_selection_outline_for_canvas(canvas)
            release_scene_rect_snapshot(scene_rect_snapshot)
        except Exception as original_error:
            run_rollback_step(
                original_error,
                "restoring group state",
                lambda: _restore_group_state(snapshot),
            )
            run_rollback_step(
                original_error,
                "refreshing the selection outline after grouping",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    restore_scene_runtime,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise

    def undo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = capture_scene_runtime(canvas, strict=True)
        scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            for group_id, group in self.removed:
                restore_group_for(canvas, group_id, group)
            refresh_selection_outline_for_canvas(canvas)
            release_scene_rect_snapshot(scene_rect_snapshot)
        except Exception as original_error:
            run_rollback_step(
                original_error,
                "restoring group state",
                lambda: _restore_group_state(snapshot),
            )
            run_rollback_step(
                original_error,
                "refreshing the selection outline after ungrouping",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    restore_scene_runtime,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise


@dataclass
class ChangeAtomLabelCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

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
        runtime_snapshot = capture_scene_runtime(canvas, strict=True)
        scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
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
            release_scene_rect_snapshot(scene_rect_snapshot)
        except Exception as original_error:
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
            run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    restore_scene_runtime,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise

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
    "MoveItemsCommand",
    "UngroupSceneItemsCommand",
    "UpdateSceneItemCommand",
]
