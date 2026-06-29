from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeySequence, QNativeGestureEvent
from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsView

from ui.atom_label_access import atom_has_visible_label_for, atom_label_service
from ui.canvas_hover_state import hover_state_for
from ui.canvas_insert_state import insert_state_for
from ui.hover_highlight_access import clear_hover_highlight_for
from ui.input_view_access import (
    focused_scene_item_for,
    reset_view_transform_for,
    reset_zoom_for,
    should_override_chemdraw_shortcut_for,
    zoom_in_for,
    zoom_out_for,
)
from ui.insert_session_access import (
    cancel_smiles_insert_for,
    cancel_template_insert_for,
)
from ui.selection_scene_access import scene_selected_items_for


class CanvasInputController:
    def __init__(
        self,
        canvas,
        *,
        scene_delete_controller,
        scene_clipboard_controller,
        history_service=None,
        hover_refresh: Callable[[], None] | None = None,
        chemdraw_shortcut_service=None,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state_for(canvas)
        self._history = history_service
        self.scene_delete = scene_delete_controller
        self.scene_clipboard = scene_clipboard_controller
        self._hover_refresh = hover_refresh or (lambda: None)
        self.chemdraw_shortcut_service = chemdraw_shortcut_service

    @property
    def history(self):
        if self._history is not None:
            return self._history
        raise AttributeError("CanvasInputController requires an injected history_service")

    @property
    def atom_labels(self):
        return atom_label_service(self.canvas)

    @staticmethod
    def shortcut_modifiers(event) -> Qt.KeyboardModifier:
        mask = (
            Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
        )
        return event.modifiers() & mask

    def key_press_event(self, event) -> None:
        focus_item = focused_scene_item_for(self.canvas)
        if isinstance(focus_item, QGraphicsTextItem):
            if focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction:
                QGraphicsView.keyPressEvent(self.canvas, event)
                return
        self._hover_refresh()
        if event.key() == Qt.Key.Key_Escape:
            if self.insert_state.template_active:
                cancel_template_insert_for(self.canvas)
                event.accept()
                return
            if self.insert_state.smiles_active:
                cancel_smiles_insert_for(self.canvas)
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.history.undo()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.history.redo()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.ZoomIn) or (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal)
        ):
            zoom_in_for(self.canvas)
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.ZoomOut) or (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore)
        ):
            zoom_out_for(self.canvas)
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_0:
            reset_zoom_for(self.canvas)
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            if self.scene_clipboard.copy_selection_to_clipboard():
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Paste):
            if self.scene_clipboard.paste_selection_from_clipboard():
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            if scene_selected_items_for(self.canvas):
                self.scene_delete.delete_selected_items()
                event.accept()
                return
            hover_atom_id = hover_state_for(self.canvas).atom_id
            if hover_atom_id is not None:
                atom_id = hover_atom_id
                if atom_has_visible_label_for(self.canvas, atom_id):
                    self.atom_labels.add_or_update_atom_label(atom_id, "C", show_carbon=False)
                else:
                    clear_hover_highlight_for(self.canvas)
                    self.scene_delete.delete_atom(atom_id, record=True)
                event.accept()
                return
            hover_bond_id = hover_state_for(self.canvas).bond_id
            if hover_bond_id is not None:
                bond_id = hover_bond_id
                clear_hover_highlight_for(self.canvas)
                self.scene_delete.delete_bond(bond_id, record=True)
            event.accept()
            return
        if self.handle_chemdraw_shortcut(event):
            event.accept()
            return
        QGraphicsView.keyPressEvent(self.canvas, event)

    def handle_chemdraw_shortcut(self, event) -> bool:
        handle_shortcut = getattr(self.chemdraw_shortcut_service, "handle_shortcut", None)
        if callable(handle_shortcut):
            return bool(handle_shortcut(event))
        return False

    def should_override_chemdraw_shortcut(self, event) -> bool:
        self._hover_refresh()
        return should_override_chemdraw_shortcut_for(self.canvas, event)

    def event(self, event, *, native_gesture_event_type=QNativeGestureEvent) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride:
            if self.should_override_chemdraw_shortcut(event):
                event.accept()
                return True
        if event.type() == QEvent.Type.NativeGesture and isinstance(event, native_gesture_event_type):
            if event.gestureType() in {
                Qt.NativeGestureType.PanNativeGesture,
                Qt.NativeGestureType.ZoomNativeGesture,
                Qt.NativeGestureType.RotateNativeGesture,
                Qt.NativeGestureType.SmartZoomNativeGesture,
            }:
                reset_view_transform_for(self.canvas)
                event.accept()
                return True
        return QGraphicsView.event(self.canvas, event)
