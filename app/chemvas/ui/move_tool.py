from __future__ import annotations

import time

from PyQt6.QtCore import QPointF, Qt

from chemvas.core.tool_overlay_logic import activate_tool_no_drag
from chemvas.ui.history_commands import MoveItemsCommand
from chemvas.ui.move_access import move_item_for
from chemvas.ui.selection_collection_access import selection_snapshot_for
from chemvas.ui.selection_drag_tool import (
    SelectionDragMixin,
    atom_ids_with_bonds,
    independent_selection_items,
)
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.tool_base import Tool


class MoveTool(SelectionDragMixin, Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("move", canvas, context=context)
        self._drag_transaction = None
        self._drag_item = None
        self._reset_selection_drag_state()
        self._drag_interval = 1.0 / 60.0
        self._last_drag_time = 0.0

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def deactivate(self) -> None:
        self._cancel_active_interaction()

    def _cancel_direct_item_drag(
        self,
        original_error: BaseException | None = None,
        *,
        token=None,
    ) -> None:
        if token is None:
            if self._drag_transaction is None:
                self._drag_item = None
                self._reset_selection_drag_state()
                return
            token = self._require_drag_token()
        try:
            self._cancel_drag_transaction(token, original_error)
        finally:
            if self._drag_transaction is None:
                self._drag_item = None
                self._reset_selection_drag_state()

    def _cancel_active_interaction(self) -> None:
        if self._drag_transaction is not None or self._drag_selection:
            if self._drag_selection:
                self._cancel_selection_drag()
                if self._drag_transaction is None:
                    self._drag_item = None
                return
            self._cancel_direct_item_drag()
            return
        self._drag_item = None
        self._reset_selection_drag_state()

    def _commit_direct_item_drag(self) -> None:
        item = self._drag_item
        self._require_drag_token()

        def commit(owner) -> None:
            if not self._moved or not self._drag_has_net_movement() or item is None:
                return
            refresh_selection_outline_for(self.canvas)
            self._ensure_drag_owner(
                owner,
                phase="refreshing its directly moved item",
            )
            self._push_drag_history(
                owner,
                MoveItemsCommand(
                    items=[item],
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                ),
            )

        try:
            self._commit_drag_transaction(commit)
        except BaseException:
            if self._drag_transaction is None:
                self._drag_item = None
                self._reset_selection_drag_state()
            raise
        self._drag_item = None
        self._reset_selection_drag_state()

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._cancel_active_interaction()
        item = self.context.item_at_event(event)
        snapshot = selection_snapshot_for(self.canvas)
        if snapshot is not None:
            atom_ids = set(snapshot.selected_atom_ids)
            bond_ids = set(snapshot.selected_bond_ids)
            atom_ids = atom_ids_with_bonds(self.canvas, atom_ids, bond_ids)
            selection_items = independent_selection_items(
                list(snapshot.selection_items),
                atom_ids,
            )
            press_pos = self.context.scene_pos_from_event(event)
            if self._begin_selection_drag(atom_ids, selection_items, press_pos):
                return True
        if item is None:
            return True
        kind = item.data(0)
        if kind not in {
            "atom",
            "bond",
            "arrow",
            "equilibrium",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
            "orbital",
            "ts_bracket",
            "shape",
        }:
            return True
        start_pos = self.context.scene_pos_from_event(event)
        self._begin_drag_transaction()
        self._drag_item = item
        self._start_pos = start_pos
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)
        return True

    def _apply_drag_delta(self, delta: QPointF) -> None:
        if not self._drag_delta_is_effective(delta):
            return
        if self._drag_selection:
            super()._apply_drag_delta(delta)
        elif self._drag_item is not None:
            token = self._require_drag_token()
            try:
                self._prepare_drag_mutation(token)
                move_item_for(self.canvas, self._drag_item, delta.x(), delta.y())
                self._ensure_drag_owner(
                    token,
                    phase="moving its directly grabbed item",
                )
                self._moved = True
                self._total_delta += delta
            except BaseException as original_error:
                self._cancel_direct_item_drag(
                    original_error,
                    token=token,
                )
                raise

    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None:
            return False
        if self._drag_selection or self._drag_item is not None:
            now = time.monotonic()
            if now - self._last_drag_time < self._drag_interval:
                return True
            self._last_drag_time = now
        scene_pos = self.context.scene_pos_from_event(event)
        delta = scene_pos - self._start_pos
        self._apply_drag_delta(delta)
        self._start_pos = scene_pos
        return True

    def on_mouse_release(self, event) -> bool:
        if self._start_pos is not None and (
            self._drag_selection or self._drag_item is not None
        ):
            scene_pos = self.context.scene_pos_from_event(event)
            delta = scene_pos - self._start_pos
            if abs(delta.x()) > 1e-6 or abs(delta.y()) > 1e-6:
                self._apply_drag_delta(delta)
                self._start_pos = scene_pos
        if self._drag_selection:
            try:
                self._commit_selection_drag()
            except BaseException:
                if self._drag_transaction is None:
                    self._drag_item = None
                raise
            self._drag_item = None
            return True
        if self._drag_item is not None:
            self._commit_direct_item_drag()
            return True
        self._reset_selection_drag_state()
        return True


__all__ = ["MoveTool"]
