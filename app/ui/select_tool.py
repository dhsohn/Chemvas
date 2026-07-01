from __future__ import annotations

import time

from PyQt6.QtCore import QPointF, Qt

from ui.handle_overlay_access import (
    clear_handles_for,
    show_curved_handles_for,
    show_shape_handles_for,
)
from ui.handle_state import active_handles_for, handle_target_for
from ui.history_commands import UpdateSceneItemCommand
from ui.scene_item_state import scene_item_state_for
from ui.selection_collection_access import selection_snapshot_for
from ui.selection_drag_tool import SelectionDragMixin
from ui.selection_press_logic import SelectionPressContext, plan_selection_press
from ui.tool_base import Tool


class SelectTool(SelectionDragMixin, Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("select", canvas, context=context)
        self._active_handle = None
        self._handle_target = None
        self._handle_before_state: dict | None = None
        self._pending_curved_handle_item = None
        self._pending_curved_handle_action: str | None = None
        self._pending_shape_handle_item = None
        self._pending_shape_handle_action: str | None = None
        self._reset_selection_drag_state()
        self._start_pos = None
        self._moved = False
        self._total_delta = QPointF(0.0, 0.0)
        self._drag_interval = 1.0 / 60.0
        self._last_drag_time = 0.0

    def activate(self) -> None:
        self.context.set_rubber_band_drag_mode()

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

    def _shape_handle_toggle_action_for_item(self, item) -> str:
        if handle_target_for(self.canvas) is item and bool(active_handles_for(self.canvas)):
            return "hide"
        return "show"

    def _begin_shape_handle_toggle_or_drag(self, item, press_pos) -> bool:
        snapshot = selection_snapshot_for(self.canvas)
        atom_ids, selection_items = self._selection_drag_context(snapshot)
        if not atom_ids and not selection_items:
            return False
        handle_target = handle_target_for(self.canvas)
        if handle_target is not None and handle_target is not item:
            clear_handles_for(self.canvas)
        self._pending_shape_handle_item = item
        self._pending_shape_handle_action = self._shape_handle_toggle_action_for_item(item)
        return self._begin_selection_drag(atom_ids, selection_items, press_pos)

    def _curved_handle_toggle_action_for_item(self, item) -> str:
        if handle_target_for(self.canvas) is item and bool(active_handles_for(self.canvas)):
            return "hide"
        return "show"

    def _begin_curved_handle_toggle_or_drag(self, item, press_pos) -> bool:
        snapshot = selection_snapshot_for(self.canvas)
        atom_ids, selection_items = self._selection_drag_context(snapshot)
        if not atom_ids and not selection_items:
            return False
        handle_target = handle_target_for(self.canvas)
        if handle_target is not None and handle_target is not item:
            clear_handles_for(self.canvas)
        self._pending_curved_handle_item = item
        self._pending_curved_handle_action = self._curved_handle_toggle_action_for_item(item)
        return self._begin_selection_drag(atom_ids, selection_items, press_pos)

    def _selected_curved_item_for_handle_toggle(self, snapshot) -> object | None:
        if snapshot is None:
            return None
        if len(snapshot.selection_items) != 1:
            return None
        item = snapshot.selection_items[0]
        if item is None or item.data(0) not in {"curved_single", "curved_double"}:
            return None
        if item not in self.context.selected_scene_items(excluded_kinds=set()):
            return None
        return item

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            item = self.context.item_at_event(event)
            if self.context.toggle_item_selection(item):
                return True
        item = self.context.item_at_event(event)
        if item is not None and item.data(0) == "handle":
            self._clear_pending_curved_handle_toggle()
            self._active_handle = item
            self._handle_target = item.data(2)
            self._handle_before_state = scene_item_state_for(self.canvas, self._handle_target)
            return True
        press_pos = self.context.scene_pos_from_event(event)
        snapshot = selection_snapshot_for(self.canvas)
        if (
            item is not None
            and item.data(0) in {"curved_single", "curved_double"}
            and item in self.context.selected_scene_items(excluded_kinds=set())
        ):
            return self._begin_curved_handle_toggle_or_drag(item, press_pos)
        selected_curved = self._selected_curved_item_for_handle_toggle(snapshot)
        if item is None and selected_curved is not None and self.context.selection_hit_test(press_pos, snapshot=snapshot):
            return self._begin_curved_handle_toggle_or_drag(selected_curved, press_pos)
        if (
            item is not None
            and item.data(0) == "shape"
            and item in self.context.selected_scene_items(excluded_kinds=set())
        ):
            return self._begin_shape_handle_toggle_or_drag(item, press_pos)
        self._clear_pending_curved_handle_toggle()
        clear_handles_for(self.canvas)
        selected = self.context.selected_scene_items(excluded_kinds=set())
        if not selected:
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
                hits_current_selection=self.context.selection_hit_test(press_pos, snapshot=snapshot),
                has_preferred_structure=bool(
                    preferred is not None and preferred.data(0) in {"atom", "bond", "ring"}
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
            self.context.update_handle_drag(self._active_handle, scene_pos)
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
        self._apply_drag_delta(delta)
        self._start_pos = scene_pos
        return True

    def on_mouse_release(self, event) -> bool:
        if self._active_handle is not None:
            target = self._handle_target
            before_state = self._handle_before_state
            after_state = scene_item_state_for(self.canvas, target)
            self._active_handle = None
            self._handle_target = None
            self._handle_before_state = None
            self._clear_pending_curved_handle_toggle()
            if before_state and after_state and before_state != after_state:
                command = UpdateSceneItemCommand(target, before_state, after_state)
                self.context.push_history(command)
            return True
        if self._pending_curved_handle_item is not None and not self._moved:
            item = self._pending_curved_handle_item
            action = self._pending_curved_handle_action
            self._clear_pending_curved_handle_toggle()
            if action == "show":
                show_curved_handles_for(self.canvas, item)
            elif action == "hide":
                clear_handles_for(self.canvas)
            self._reset_selection_drag_state()
            self._start_pos = None
            self._moved = False
            self._total_delta = QPointF(0.0, 0.0)
            return True
        if self._pending_shape_handle_item is not None and not self._moved:
            item = self._pending_shape_handle_item
            action = self._pending_shape_handle_action
            self._clear_pending_curved_handle_toggle()
            if action == "show":
                show_shape_handles_for(self.canvas, item)
            elif action == "hide":
                clear_handles_for(self.canvas)
            self._reset_selection_drag_state()
            self._start_pos = None
            self._moved = False
            self._total_delta = QPointF(0.0, 0.0)
            return True
        if self._start_pos is None and not self._drag_selection:
            self._clear_pending_curved_handle_toggle()
            return False
        if self._start_pos is not None and self._drag_selection:
            scene_pos = self.context.scene_pos_from_event(event)
            delta = scene_pos - self._start_pos
            if abs(delta.x()) > 1e-6 or abs(delta.y()) > 1e-6:
                self._apply_drag_delta(delta)
                self._start_pos = scene_pos
        self._commit_selection_drag()
        self._clear_pending_curved_handle_toggle()
        self._reset_selection_drag_state()
        self._start_pos = None
        self._moved = False
        self._total_delta = QPointF(0.0, 0.0)
        return True


__all__ = ["SelectTool"]
