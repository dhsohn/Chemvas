from __future__ import annotations

import time
from typing import override

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QGraphicsView

from chemvas.domain.document import VALID_ARROW_KINDS, VALID_CURVED_ARROW_KINDS
from chemvas.features.selection import (
    ROTATION_HANDLE_TYPE,
    SelectionPressContext,
    plan_selection_press,
)
from chemvas.ui.handle_overlay_access import (
    clear_handles_for,
    show_curved_handles_for,
    show_endpoint_handles_for,
    show_shape_handles_for,
)
from chemvas.ui.handle_state import active_handles_for, handle_target_for
from chemvas.ui.history_commands import UpdateSceneItemCommand
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.selection_collection_access import selection_snapshot_for
from chemvas.ui.selection_drag_tool import SelectionDragMixin
from chemvas.ui.selection_scene_access import clear_scene_selection_for
from chemvas.ui.selection_service_access import (
    clear_note_selection_for,
    select_note_for,
)
from chemvas.ui.tool_base import Tool

# Holding Shift while turning the rotation handle snaps the sweep to this
# many degrees, so a scheme can be squared up without typing an angle.
ROTATION_SNAP_STEP_DEGREES = 15.0


class SelectTool(SelectionDragMixin, Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("select", canvas, context=context)
        self._drag_transaction = None
        self._active_handle = None
        self._handle_target = None
        self._handle_before_state: dict | None = None
        self._rotation_session = None
        self._pending_arrow_handle_item = None
        self._pending_arrow_handle_action: str | None = None
        self._pending_shape_handle_item = None
        self._pending_shape_handle_action: str | None = None
        self._reset_selection_drag_state()
        self._drag_interval = 1.0 / 60.0
        self._last_drag_time = 0.0

    @override
    def activate(self) -> None:
        self.context.set_rubber_band_drag_mode()

    @override
    def deactivate(self) -> None:
        self._cancel_active_interaction()
        # Qt owns marquee dragging separately from our item transactions.
        # Changing mode stops it even if the mouse button is still held.
        self.context.set_drag_mode(QGraphicsView.DragMode.NoDrag)
        clear_handles_for(self.canvas)

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

    def _clear_pending_handle_toggle(self) -> None:
        self._pending_arrow_handle_item = None
        self._pending_arrow_handle_action = None
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
                self._clear_pending_handle_toggle()
                self._reset_selection_drag_state()
                return
            token = self._require_drag_token()
        try:
            self._cancel_drag_transaction(token, original_error)
        finally:
            if self._drag_transaction is None:
                self._clear_handle_drag_state()
                self._clear_pending_handle_toggle()
                self._reset_selection_drag_state()

    def _cancel_rotation_drag(
        self,
        original_error: BaseException | None = None,
        *,
        token=None,
    ) -> None:
        if token is None:
            if self._drag_transaction is None:
                self._rotation_session = None
                return
            token = self._require_drag_token()
        try:
            self._cancel_drag_transaction(token, original_error)
        finally:
            if self._drag_transaction is None:
                self._rotation_session = None

    def _commit_rotation_drag(self) -> None:
        session = self._rotation_session
        self._require_drag_token()

        def commit(owner) -> None:
            command = self.context.rotation_drag_command(session)
            self._ensure_drag_owner(owner, phase="reading its rotation result")
            if command is not None:
                self._push_drag_history(owner, command)

        try:
            self._commit_drag_transaction(commit)
        finally:
            if self._drag_transaction is None:
                self._rotation_session = None

    def _cancel_active_interaction(self) -> None:
        if self._rotation_session is not None:
            self._cancel_rotation_drag()
            return
        if self._active_handle is not None:
            self._cancel_handle_drag()
            return
        if self._drag_transaction is not None or self._drag_selection:
            try:
                self._cancel_selection_drag()
            finally:
                if self._drag_transaction is None:
                    self._clear_pending_handle_toggle()
            return
        self._clear_handle_drag_state()
        self._clear_pending_handle_toggle()
        self._reset_selection_drag_state()

    def _commit_handle_drag(self) -> None:
        target = self._handle_target
        before_state = self._handle_before_state
        self._require_drag_token()

        def commit(owner) -> None:
            after_state = scene_item_state_for(self.canvas, target)
            self._ensure_drag_owner(
                owner,
                phase="reading its handle-drag result",
            )
            if before_state and after_state and before_state != after_state:
                self._push_drag_history(
                    owner, UpdateSceneItemCommand(target, before_state, after_state)
                )

        try:
            self._commit_drag_transaction(commit)
        except Exception:
            if self._drag_transaction is None:
                self._clear_handle_drag_state()
                self._clear_pending_handle_toggle()
                self._reset_selection_drag_state()
            raise
        self._clear_handle_drag_state()
        self._clear_pending_handle_toggle()
        self._reset_selection_drag_state()

    def _commit_pending_handle_toggle(self, operation) -> None:
        self._require_drag_token()

        def commit(owner) -> None:
            operation()
            self._ensure_drag_owner(
                owner,
                phase="applying its pending handle toggle",
            )

        try:
            self._commit_drag_transaction(commit)
        except Exception:
            if self._drag_transaction is None:
                self._clear_pending_handle_toggle()
                self._reset_selection_drag_state()
            raise
        self._clear_pending_handle_toggle()
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
        except Exception as original_error:
            self._cancel_selection_drag(original_error)
            raise
        return True

    def _arrow_handle_toggle_action_for_item(self, item) -> str:
        if handle_target_for(self.canvas) is item and bool(
            active_handles_for(self.canvas)
        ):
            return "hide"
        return "show"

    def _begin_arrow_handle_toggle_or_drag(
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
        action = self._arrow_handle_toggle_action_for_item(item)
        if not self._begin_selection_drag(atom_ids, selection_items, press_pos):
            return False
        try:
            if handle_target is not None and handle_target is not item:
                clear_handles_for(self.canvas)
            self._pending_arrow_handle_item = item
            self._pending_arrow_handle_action = action
        except Exception as original_error:
            self._cancel_selection_drag(original_error)
            raise
        return True

    def _selected_arrow_item_for_handle_toggle(self, snapshot) -> object | None:
        if snapshot is None:
            return None
        if len(snapshot.selection_items) != 1:
            return None
        item = snapshot.selection_items[0]
        if item is None or item.data(0) not in VALID_ARROW_KINDS:
            return None
        return item

    @staticmethod
    def _show_arrow_handles_for_item(canvas, item) -> None:
        # A curved arrow also gets its control handle; every other arrow and
        # line is defined by its two ends alone.
        if item.data(0) in VALID_CURVED_ARROW_KINDS:
            show_curved_handles_for(canvas, item)
        else:
            show_endpoint_handles_for(canvas, item)

    @override
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
        if item is not None and item.data(1) == ROTATION_HANDLE_TYPE:
            session = self.context.begin_rotation_drag(
                self.context.scene_pos_from_event(event)
            )
            if session is None:
                return False
            self._begin_drag_transaction()
            self._rotation_session = session
            return True
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
            and item.data(0) in {"note", "shape", "image", "mark"}
            and (snapshot is None or item not in snapshot.selection_items)
        ):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                return self.context.toggle_item_selection(item)
            clear_handles_for(self.canvas)
            if item.data(0) == "note":
                clear_scene_selection_for(self.canvas)
                # Notes own selection outside Qt; their service expands
                # notes-only groups before the drag snapshot is collected.
                select_note_for(self.canvas, item)
            elif not self._select_structure_item(item):
                return False
            atom_ids, selection_items = self._selection_drag_context()
            return self._begin_selection_drag(atom_ids, selection_items, press_pos)
        if item is not None and item.data(0) in VALID_ARROW_KINDS:
            if snapshot is not None and item in snapshot.selection_items:
                return self._begin_arrow_handle_toggle_or_drag(
                    item, press_pos, snapshot=snapshot
                )
            clear_handles_for(self.canvas)
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                return self.context.toggle_item_selection(item)
            if not self._select_structure_item(item):
                return False
            atom_ids, selection_items = self._selection_drag_context()
            return self._begin_selection_drag(atom_ids, selection_items, press_pos)
        selected_arrow = self._selected_arrow_item_for_handle_toggle(snapshot)
        if (
            item is None
            and selected_arrow is not None
            and self.context.selection_hit_test(press_pos, snapshot=snapshot)
        ):
            return self._begin_arrow_handle_toggle_or_drag(
                selected_arrow,
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
        self._clear_pending_handle_toggle()
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
            if not event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
            ):
                clear_note_selection_for(self.canvas)
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

    @override
    def on_mouse_move(self, event) -> bool:
        if self._rotation_session is not None:
            scene_pos = self.context.scene_pos_from_event(event)
            token = self._require_drag_token()
            snap_step = (
                ROTATION_SNAP_STEP_DEGREES
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                else None
            )
            try:
                self._prepare_drag_mutation(token)
                self.context.update_rotation_drag(
                    self._rotation_session, scene_pos, snap_step=snap_step
                )
                self._ensure_drag_owner(token, phase="turning its selection")
            except Exception as original_error:
                self._cancel_rotation_drag(original_error, token=token)
                raise
            return True
        if self._active_handle is not None:
            scene_pos = self.context.scene_pos_from_event(event)
            token = self._require_drag_token()
            try:
                self._prepare_drag_mutation(token)
                self.context.update_handle_drag(self._active_handle, scene_pos)
                self._ensure_drag_owner(
                    token,
                    phase="updating its active handle",
                )
            except Exception as original_error:
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
        self._move_selection_to(self.context.scene_pos_from_event(event))
        return True

    def _move_selection_to(self, scene_pos) -> None:
        if self._start_pos is None or not self._drag_selection:
            return
        delta = scene_pos - self._start_pos
        if not self._drag_delta_is_effective(delta):
            return
        if not self._moved and any(
            item.data(0) in VALID_ARROW_KINDS for item in self._selection_items
        ):
            transform = self.canvas.transform()
            screen_delta = transform.map(scene_pos) - transform.map(self._start_pos)
            if screen_delta.manhattanLength() < QApplication.startDragDistance():
                # Keep the press position until the gesture starts: several
                # small frames must accumulate, while click jitter stays inert.
                return
        self._clear_pending_handle_toggle()
        try:
            self._apply_drag_delta_with_connect(delta)
        except Exception:
            if self._drag_transaction is None:
                self._clear_pending_handle_toggle()
            raise
        self._start_pos = scene_pos

    @override
    def on_mouse_release(self, event) -> bool:
        if self._rotation_session is not None:
            self._commit_rotation_drag()
            return True
        if self._active_handle is not None:
            self._commit_handle_drag()
            return True
        # The final pointer position matters even when Qt coalesces every move
        # frame. Resolve it before deciding whether this was a handle click.
        self._move_selection_to(self.context.scene_pos_from_event(event))
        if self._pending_arrow_handle_item is not None and not self._moved:
            item = self._pending_arrow_handle_item
            action = self._pending_arrow_handle_action

            def apply_toggle() -> None:
                if action == "show":
                    self._show_arrow_handles_for_item(self.canvas, item)
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
            self._clear_pending_handle_toggle()
            return False
        try:
            self._commit_selection_drag()
        except Exception:
            if self._drag_transaction is None:
                self._clear_pending_handle_toggle()
            raise
        self._clear_pending_handle_toggle()
        return True


__all__ = ["SelectTool"]
