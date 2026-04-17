from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeySequence, QNativeGestureEvent
from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsView


class CanvasInputController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    @staticmethod
    def shortcut_modifiers(event) -> Qt.KeyboardModifier:
        mask = (
            Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
        )
        return event.modifiers() & mask

    def key_press_event(self, event) -> None:
        focus_item = self.canvas.scene().focusItem()
        if isinstance(focus_item, QGraphicsTextItem):
            if focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction:
                QGraphicsView.keyPressEvent(self.canvas, event)
                return
        self.canvas._refresh_hover_from_cursor()
        if event.key() == Qt.Key.Key_Escape:
            if self.canvas._template_insert_active:
                self.canvas._cancel_template_insert()
                event.accept()
                return
            if self.canvas._smiles_insert_active:
                self.canvas._cancel_smiles_insert()
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.canvas.undo()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.canvas.redo()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            if self.canvas.copy_selection_to_clipboard():
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Paste):
            if self.canvas.paste_selection_from_clipboard():
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            if self.canvas.scene().selectedItems():
                self.canvas.delete_selected_items()
                event.accept()
                return
            if self.canvas.hover_atom_id is not None:
                if self.canvas._atom_has_visible_label(self.canvas.hover_atom_id):
                    self.canvas.clear_atom_label(self.canvas.hover_atom_id)
                else:
                    self.canvas.delete_atom(self.canvas.hover_atom_id, record=True)
                event.accept()
                return
            elif self.canvas.hover_bond_id is not None:
                bond_id = self.canvas.hover_bond_id
                self.canvas._clear_hover_highlight()
                if bond_id is not None:
                    self.canvas.delete_bond(bond_id, record=True)
                    event.accept()
                    return
            else:
                if self.canvas.hover_bond_id is not None and self.canvas.hover_atom_id is None:
                    bond = self.canvas.model.bonds[self.canvas.hover_bond_id]
                    if bond is not None:
                        ring_item = self.canvas._ring_for_bond(self.canvas.hover_bond_id)
                        if ring_item is not None:
                            self.canvas.delete_ring(ring_item, record=True)
            event.accept()
            return
        if self.canvas._handle_chemdraw_shortcut(event):
            event.accept()
            return
        QGraphicsView.keyPressEvent(self.canvas, event)

    def handle_chemdraw_shortcut(self, event) -> bool:
        if self.canvas._handle_chemdraw_object_shortcut(event):
            return True
        if self.canvas.hover_atom_id is not None:
            return self.canvas._handle_chemdraw_atom_hotkey(event, self.canvas.hover_atom_id)
        if self.canvas.hover_bond_id is not None:
            return self.canvas._handle_chemdraw_bond_hotkey(event, self.canvas.hover_bond_id)
        return self.canvas._handle_chemdraw_generic_hotkey(event)

    def should_override_chemdraw_shortcut(self, event) -> bool:
        self.canvas._refresh_hover_from_cursor()
        modifiers = self.canvas._shortcut_modifiers(event)
        if modifiers not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            return False
        text = event.text()
        if self.canvas.hover_atom_id is not None:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                return True
            return text in {
                "+",
                "-",
                "0",
                "1",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "a",
                "b",
                "c",
                "d",
                "e",
                "f",
                "h",
                "i",
                "k",
                "l",
                "m",
                "n",
                "o",
                "p",
                "q",
                "r",
                "s",
                "u",
                "v",
                "w",
                "x",
                "z",
                "A",
                "B",
                "C",
                "E",
                "F",
                "H",
                "K",
                "L",
                "M",
                "N",
                "O",
                "P",
                "Q",
                "S",
                "Y",
                "Z",
            }
        if self.canvas.hover_bond_id is not None:
            return text in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "a", "b", "h", "w", "B", "H"}
        return False

    def event(self, event, *, native_gesture_event_type=QNativeGestureEvent) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride:
            if self.canvas._should_override_chemdraw_shortcut(event):
                event.accept()
                return True
        if event.type() == QEvent.Type.NativeGesture and isinstance(event, native_gesture_event_type):
            if event.gestureType() in {
                Qt.NativeGestureType.PanNativeGesture,
                Qt.NativeGestureType.ZoomNativeGesture,
                Qt.NativeGestureType.RotateNativeGesture,
                Qt.NativeGestureType.SmartZoomNativeGesture,
            }:
                self.canvas._reset_view_transform()
                event.accept()
                return True
        return QGraphicsView.event(self.canvas, event)
