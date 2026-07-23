from __future__ import annotations

import time

from PyQt6.QtCore import Qt

from chemvas.features.selection import SelectionPressContext, plan_selection_press
from chemvas.ui.handle_overlay_access import (
    clear_handles_for,
    show_curved_handles_for,
    show_shape_handles_for,
)
from chemvas.ui.handle_state import active_handles_for, handle_target_for
from chemvas.ui.history_commands import UpdateSceneItemCommand
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.selection_collection_access import selection_snapshot_for
from chemvas.ui.selection_drag_tool import SelectionDragMixin
from chemvas.ui.tool_base import Tool


class SelectTool(SelectionDragMixin, Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("select", canvas, context=context)
        self._drag_transaction = None
        self._active_handle = None
        self._handle_target = None
        self._handle_before_state: dict | None = None
        self._pending_curved_handle_item = None
        self._pending_curved_handle_action: str | None = None
        self._pending_shape_handle_item = None
        self._pending_shape_handle_action: str | None = None
        self._reset_selection_drag_state()
        self._drag_interval = 1.0 / 60.0
        self._last_drag_time = 0.0

    def activate(self) -> None:
        self.context.set_rubber_band_drag_mode()

    def deactivate(self) -> None:
        self._cancel_active_interaction()

    def _selection_drag_context(self, snapshot=None) -> tuple[set[int], list]:
        if snapshot is None:
            snapshot = selection_snapshot_for(self.canvas)
        if snapshot is None:
            return set(), []
        return set(snapshot.selected_atom_ids), list(snapshot.selection_items)

    def _select_structure_item(self, item) -> bool:
        if item is None:
            return False
        return self.context.select_single_structure_item(item)

    def _clear_pending_curved_handle_toggle(self) -> None:
        self._pending_curved_handle_item = None
        self._pending_curved_handle_action = None
        self._pending_shape_handle_item = None
        self._pending_shape_handle_action = None

    def _clear_handle_drag_state(self) -> None:
        self._active_handle = None
        self._handle_target = None
        self._handle_before_state = None

    def _cancel_handle_drag(
        self,
        original_error: BaseException | None = None,
        *,
        token=None,
    ) -> None:
        if token is None:
            if self._drag_transaction is None:
                self._clear_handle_drag_state()
                self._clear_pending_curved_handle_toggle()
                self._reset_selection_drag_state()
                return
            token = self._require_drag_token()
        try:
            self._cancel_drag_transaction(token, original_error)
        finally:
            if self._drag_transaction is None:
                self._clear_handle_drag_state()
                self._clear_pending_curved_handle_toggle()
                self._reset_selection_drag_state()

    def _cancel_active_interaction(self) -> None:
        if self._active_handle is not None:
            self._cancel_handle_drag()
            return
        if self._drag_transaction is not None or self._drag_selection:
            try:
                self._cancel_selection_drag()
            finally:
                if self._drag_transaction is None:
                    self._clear_pending_curved_handle_toggle()
            return
        self._clear_handle_drag_state()
        self._clear_pending_curved_handle_toggle()
        self._reset_selection_drag_state()

    def _commit_handle_drag(self) -> None:
        target = self._handle_target
        before_state = self._handle_before_state
        self._require_drag_token()

        def commit(owner) -> None:
            after_state = scene_item_state_for(self.canvas, target)
            self._ensure_drag_owner(
                owner,
                checkpoint=owner.begin_history_checkpoint,
                phase="reading its handle-drag result",
            )
            if before_state and after_state and before_state != after_state:
                self._push_drag_history(
                    owner, UpdateSceneItemCommand(target, before_state, after_state)
                )

        try:
            self._commit_drag_transaction(commit)
        except BaseException:
            if self._drag_transaction is None:
                self._clear_handle_drag_state()
                self._clear_pending_curved_handle_toggle()
                self._reset_selection_drag_state()
            raise
        self._clear_handle_drag_state()
        self._clear_pending_curved_handle_toggle()
        self._reset_selection_drag_state()

    def _commit_pending_handle_toggle(self, operation) -> None:
        self._require_drag_token()

        def commit(owner) -> None:
            operation()
            self._ensure_drag_owner(
                owner,
                checkpoint=owner.begin_history_checkpoint,
                phase="applying its pending handle toggle",
            )

        try:
            self._commit_drag_transaction(commit)
        except BaseException:
            if self._drag_transaction is None:
                self._clear_pending_curved_handle_toggle()
                self._reset_selection_drag_state()
            raise
        self._clear_pending_curved_handle_toggle()
        self._reset_selection_drag_state()

    def _shape_handle_toggle_action_for_item(self, item) -> str:
        if handle_target_for(self.canvas) is item and bool(
            active_handles_for(self.canvas)
        ):
            return "hide"
        return "show"

    def _begin_shape_handle_toggle_or_drag(
        self,
        item,
        press_pos,
        *,
        snapshot=None,
    ) -> bool:
        if snapshot is None:
            snapshot = selection_snapshot_for(self.canvas)
        atom_ids, selection_items = self._selection_drag_context(snapshot)
        if not atom_ids and not selection_items:
            return False
        handle_target = handle_target_for(self.canvas)
        action = self._shape_handle_toggle_action_for_item(item)
        if not self._begin_selection_drag(atom_ids, selection_items, press_pos):
            return False
        try:
            if handle_target is not None and handle_target is not item:
                clear_handles_for(self.canvas)
            self._pending_shape_handle_item = item
            self._pending_shape_handle_action = action
        except BaseException as original_error:
            self._cancel_selection_drag(original_error)
            raise
        return True

    def _curved_handle_toggle_action_for_item(self, item) -> str:
        if handle_target_for(self.canvas) is item and bool(
            active_handles_for(self.canvas)
        ):
            return "hide"
        return "show"

    def _begin_curved_handle_toggle_or_drag(
        self,
        item,
        press_pos,
        *,
        snapshot=None,
    ) -> bool:
        if snapshot is None:
            snapshot = selection_snapshot_for(self.canvas)
        atom_ids, selection_items = self._selection_drag_context(snapshot)
        if not atom_ids and not selection_items:
            return False
        handle_target = handle_target_for(self.canvas)
        action = self._curved_handle_toggle_action_for_item(item)
        if not self._begin_selection_drag(atom_ids, selection_items, press_pos):
            return False
        try:
            if handle_target is not None and handle_target is not item:
                clear_handles_for(self.canvas)
            self._pending_curved_handle_item = item
            self._pending_curved_handle_action = action
        except BaseException as original_error:
            self._cancel_selection_drag(original_error)
            raise
        return True

    def _selected_curved_item_for_handle_toggle(self, snapshot) -> object | None:
        if snapshot is None:
            return None
        if len(snapshot.selection_items) != 1:
            return None
        item = snapshot.selection_items[0]
        if item is None or item.data(0) not in {"curved_single", "curved_double"}:
            return None
        return item

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        # A failed release or an interrupted tool switch must not let this press
        # overwrite the only savepoint for the prior interaction.
        self._cancel_active_interaction()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            item = self.context.item_at_event(event)
            if self.context.toggle_item_selection(item):
                return True
        item = self.context.item_at_event(event)
        if item is not None and item.data(0) == "handle":
            handle_target = item.data(2)
            handle_before_state = scene_item_state_for(
                self.canvas,
                handle_target,
            )
            self._begin_drag_transaction()
            self._active_handle = item
            self._handle_target = handle_target
            self._handle_before_state = handle_before_state
            return True
        press_pos = self.context.scene_pos_from_event(event)
        snapshot = selection_snapshot_for(self.canvas)
        if (
            item is not None
            and item.data(0) in {"curved_single", "curved_double"}
            and snapshot is not None
            and item in snapshot.selection_items
        ):
            return self._begin_curved_handle_toggle_or_drag(
                item,
                press_pos,
                snapshot=snapshot,
            )
        selected_curved = self._selected_curved_item_for_handle_toggle(snapshot)
        if (
            item is None
            and selected_curved is not None
            and self.context.selection_hit_test(press_pos, snapshot=snapshot)
        ):
            return self._begin_curved_handle_toggle_or_drag(
                selected_curved,
                press_pos,
                snapshot=snapshot,
            )
        if (
            item is not None
            and item.data(0) == "shape"
            and snapshot is not None
            and item in snapshot.selection_items
        ):
            return self._begin_shape_handle_toggle_or_drag(
                item,
                press_pos,
                snapshot=snapshot,
            )
        self._clear_pending_curved_handle_toggle()
        clear_handles_for(self.canvas)
        if snapshot is None:
            preferred = self.context.preferred_structure_item_at_scene_pos(press_pos)
            if preferred is None or preferred.data(0) not in {"atom", "bond", "ring"}:
                return False
            if not self._select_structure_item(preferred):
                return False
            item = preferred
            snapshot = selection_snapshot_for(self.canvas)
        atom_ids, selection_items = self._selection_drag_context(snapshot)
        preferred = self.context.preferred_structure_item_at_scene_pos(press_pos)
        decision = plan_selection_press(
            SelectionPressContext(
                has_selection_target=bool(atom_ids or selection_items),
                hits_current_selection=self.context.selection_hit_test(
                    press_pos, snapshot=snapshot
                ),
                has_preferred_structure=bool(
                    preferred is not None
                    and preferred.data(0) in {"atom", "bond", "ring"}
                ),
            )
        )
        if decision.action == "ignore":
            return False
        if decision.action == "reselect_preferred_and_drag":
            if preferred is None or preferred.data(0) not in {"atom", "bond", "ring"}:
                return False
            if not self._select_structure_item(preferred):
                return False
            item = preferred
            snapshot = selection_snapshot_for(self.canvas)
            atom_ids, selection_items = self._selection_drag_context(snapshot)
            if not atom_ids and not selection_items:
                return False
        return self._begin_selection_drag(atom_ids, selection_items, press_pos)

    def on_mouse_move(self, event) -> bool:
        if self._active_handle is not None:
            scene_pos = self.context.scene_pos_from_event(event)
            token = self._require_drag_token()
            try:
                self._prepare_drag_mutation(token)
                self.context.update_handle_drag(self._active_handle, scene_pos)
                self._ensure_drag_owner(
                    token,
                    checkpoint=token.begin_history_checkpoint,
                    phase="updating its active handle",
                )
            except BaseException as original_error:
                self._cancel_handle_drag(
                    original_error,
                    token=token,
                )
                raise
            return True
        if self._start_pos is None:
            return False
        if self._drag_selection:
            now = time.monotonic()
            if now - self._last_drag_time < self._drag_interval:
                return True
            self._last_drag_time = now
        scene_pos = self.context.scene_pos_from_event(event)
        delta = scene_pos - self._start_pos
        if abs(delta.x()) > 1e-6 or abs(delta.y()) > 1e-6:
            self._clear_pending_curved_handle_toggle()
        try:
            self._apply_drag_delta(delta)
        except BaseException:
            if self._drag_transaction is None:
                self._clear_pending_curved_handle_toggle()
            raise
        self._start_pos = scene_pos
        return True

    def on_mouse_release(self, event) -> bool:
        if self._active_handle is not None:
            self._commit_handle_drag()
            return True
        if self._pending_curved_handle_item is not None and not self._moved:
            item = self._pending_curved_handle_item
            action = self._pending_curved_handle_action

            def apply_toggle() -> None:
                if action == "show":
                    show_curved_handles_for(self.canvas, item)
                elif action == "hide":
                    clear_handles_for(self.canvas)

            self._commit_pending_handle_toggle(apply_toggle)
            return True
        if self._pending_shape_handle_item is not None and not self._moved:
            item = self._pending_shape_handle_item
            action = self._pending_shape_handle_action

            def apply_toggle() -> None:
                if action == "show":
                    show_shape_handles_for(self.canvas, item)
                elif action == "hide":
                    clear_handles_for(self.canvas)

            self._commit_pending_handle_toggle(apply_toggle)
            return True
        if self._start_pos is None and not self._drag_selection:
            self._clear_pending_curved_handle_toggle()
            return False
        if self._start_pos is not None and self._drag_selection:
            scene_pos = self.context.scene_pos_from_event(event)
            delta = scene_pos - self._start_pos
            if abs(delta.x()) > 1e-6 or abs(delta.y()) > 1e-6:
                try:
                    self._apply_drag_delta(delta)
                except BaseException:
                    if self._drag_transaction is None:
                        self._clear_pending_curved_handle_toggle()
                    raise
                self._start_pos = scene_pos
        try:
            self._commit_selection_drag()
        except BaseException:
            if self._drag_transaction is None:
                self._clear_pending_curved_handle_toggle()
            raise
        self._clear_pending_curved_handle_toggle()
        return True


__all__ = ["SelectTool"]
