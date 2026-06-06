import time

from core.tool_overlay_logic import activate_tool_no_drag
from PyQt6.QtCore import QPointF, Qt

from ui.history_commands import MoveItemsCommand
from ui.move_access import move_item_for
from ui.selection_collection_access import (
    selected_ids_for,
    selected_items_for_transform_for,
)
from ui.selection_drag_tool import (
    SelectionDragMixin,
    atom_ids_with_bonds,
    independent_selection_items,
)
from ui.selection_service_access import refresh_selection_outline_for
from ui.tool_base import Tool


class MoveTool(SelectionDragMixin, Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("move", canvas, context=context)
        self._drag_item = None
        self._start_pos = None
        self._moved = False
        self._reset_selection_drag_state()
        self._drag_interval = 1.0 / 60.0
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.context.item_at_event(event)
        selected = selected_items_for_transform_for(self.canvas)
        if selected:
            atom_ids, bond_ids = selected_ids_for(self.canvas)
            atom_ids = atom_ids_with_bonds(self.canvas, atom_ids, bond_ids)
            selection_items = independent_selection_items(selected, atom_ids)
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
        }:
            return True
        self._drag_item = item
        self._start_pos = self.context.scene_pos_from_event(event)
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)
        return True

    def _apply_drag_delta(self, delta: QPointF) -> None:
        if self._drag_selection:
            super()._apply_drag_delta(delta)
        elif self._drag_item is not None:
            move_item_for(self.canvas, self._drag_item, delta.x(), delta.y())
            self._moved = True
            self._total_delta += delta

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
        if self._start_pos is not None and (self._drag_selection or self._drag_item is not None):
            scene_pos = self.context.scene_pos_from_event(event)
            delta = scene_pos - self._start_pos
            if abs(delta.x()) > 1e-6 or abs(delta.y()) > 1e-6:
                self._apply_drag_delta(delta)
                self._start_pos = scene_pos
        if self._moved:
            if self._drag_selection:
                self._commit_selection_drag()
            elif self._drag_item is not None:
                refresh_selection_outline_for(self.canvas)
                command = MoveItemsCommand(
                    items=[self._drag_item],
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                )
                self.context.push_history(command)
        self._drag_item = None
        self._start_pos = None
        self._moved = False
        self._reset_selection_drag_state()
        self._total_delta = QPointF(0.0, 0.0)
        return True


__all__ = ["MoveTool"]
