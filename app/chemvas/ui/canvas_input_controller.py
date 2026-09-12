from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QCursor, QKeySequence, QNativeGestureEvent
from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsView, QWidget

from chemvas.ui.atom_label_access import atom_has_visible_label_for, atom_label_service
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.canvas_window_access import notify_error_for
from chemvas.ui.input_view_access import (
    fit_canvas_to_view_for,
    focused_scene_item_for,
    reset_view_transform_for,
    reset_zoom_for,
    scene_pos_from_global_pos_for,
    shortcut_modifiers_for,
    should_override_chemdraw_shortcut_for,
    structure_edit_shortcut_matches,
    zoom_in_for,
    zoom_out_for,
)
from chemvas.ui.insert_session_access import (
    cancel_smiles_insert_for,
    cancel_template_insert_for,
)
from chemvas.ui.scene_group_operations import group_selection_for, ungroup_selection_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.selection_collection_access import selected_scene_items_for
from chemvas.ui.selection_service_access import selection_service_from_canvas
from chemvas.ui.sheet_setup_access import (
    OFF_SHEET_EDIT_GUIDANCE,
    scene_pos_in_sheet_for,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class CanvasInputController:
    def __init__(
        self,
        canvas,
        *,
        scene_delete_controller,
        scene_clipboard_controller,
        history_service=None,
        hover_controller,
        chemdraw_shortcut_service=None,
        tool_mode_controller,
        prepare_for_document_edit: Callable[[], None],
        cancel_active_gesture: Callable[[], None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state_for(canvas)
        self._history = history_service
        self.scene_delete = scene_delete_controller
        self.scene_clipboard = scene_clipboard_controller
        self.hover = hover_controller
        self.chemdraw_shortcut_service = chemdraw_shortcut_service
        self.tool_mode_controller = tool_mode_controller
        self._prepare_for_document_edit = prepare_for_document_edit
        self._cancel_active_gesture = cancel_active_gesture

    @property
    def history(self):
        if self._history is not None:
            return self._history
        raise AttributeError(
            "CanvasInputController requires an injected history_service"
        )

    @property
    def atom_labels(self):
        return atom_label_service(self.canvas)

    def key_press_event(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_interaction()
            event.accept()
            return
        focus_item = focused_scene_item_for(self.canvas)
        if isinstance(focus_item, QGraphicsTextItem) and (
            focus_item.textInteractionFlags()
            & Qt.TextInteractionFlag.TextEditorInteraction
        ):
            QGraphicsView.keyPressEvent(self.canvas, event)
            return
        self.hover.refresh()
        if event.matches(QKeySequence.StandardKey.Undo):
            self._prepare_for_document_edit()
            self.history.undo()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self._prepare_for_document_edit()
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
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_0
        ):
            reset_zoom_for(self.canvas)
            event.accept()
            return
        if shortcut_modifiers_for(event) == Qt.KeyboardModifier.NoModifier:
            if event.key() == Qt.Key.Key_F5:
                reset_zoom_for(self.canvas)
                event.accept()
                return
            if event.key() == Qt.Key.Key_F6:
                fit_canvas_to_view_for(self.canvas)
                event.accept()
                return
            if event.key() == Qt.Key.Key_F7:
                zoom_in_for(self.canvas)
                event.accept()
                return
            if event.key() == Qt.Key.Key_F8:
                zoom_out_for(self.canvas)
                event.accept()
                return
        if (
            event.matches(QKeySequence.StandardKey.Copy)
            and self.scene_clipboard.copy_selection_to_clipboard()
        ):
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            self._prepare_for_document_edit()
            if self.scene_clipboard.copy_selection_to_clipboard():
                self.scene_delete.delete_selected_items()
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Paste):
            self._prepare_for_document_edit()
            if self.scene_clipboard.paste_selection_from_clipboard():
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.tool_mode_controller.set_tool("select")
            select_all_scene_items_for(self.canvas)
            event.accept()
            return
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_G
        ):
            self._prepare_for_document_edit()
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                ungroup_selection_for(self.canvas)
            else:
                group_selection_for(self.canvas)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._prepare_for_document_edit()
            # Cancellation restored the pre-drag geometry; resolve any hover
            # deletion against that state, never the discarded preview.
            self.hover.refresh()
            if selected_scene_items_for(
                self.canvas, excluded_kinds={"handle", "note_box", "note_select"}
            ):
                self.scene_delete.delete_selected_items()
                event.accept()
                return
            self._delete_hover_target(event)
            event.accept()
            return
        if self.handle_chemdraw_shortcut(event):
            event.accept()
            return
        QGraphicsView.keyPressEvent(self.canvas, event)

    def _delete_hover_target(self, event) -> None:
        if self._is_offsheet_structure_edit(event):
            notify_error_for(self.canvas, OFF_SHEET_EDIT_GUIDANCE)
            return
        hover_atom_id = hover_state_for(self.canvas).atom_id
        if hover_atom_id is not None:
            if atom_has_visible_label_for(self.canvas, hover_atom_id):
                self.atom_labels.add_or_update_atom_label(
                    hover_atom_id, "C", show_carbon=False
                )
            else:
                self.hover.clear_hover_highlight()
                self.scene_delete.delete_atom(hover_atom_id, record=True)
            return
        hover_bond_id = hover_state_for(self.canvas).bond_id
        if hover_bond_id is not None:
            self.hover.clear_hover_highlight()
            self.scene_delete.delete_bond(hover_bond_id, record=True)

    def _cancel_interaction(self) -> None:
        if self.insert_state.template_active:
            cancel_template_insert_for(self.canvas)
        elif self.insert_state.smiles_active:
            cancel_smiles_insert_for(self.canvas)
        else:
            if self._cancel_active_gesture is not None:
                self._cancel_active_gesture()
            # Tool deactivation owns gesture rollback and note commits.
            # Re-enter Select even when already active to cancel its drag.
            self.tool_mode_controller.set_tool("select")

    def handle_chemdraw_shortcut(self, event) -> bool:
        if self._is_offsheet_structure_edit(event):
            notify_error_for(self.canvas, OFF_SHEET_EDIT_GUIDANCE)
            return True
        modifiers = shortcut_modifiers_for(event)
        object_edit = (
            modifiers
            == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            and event.key() in (Qt.Key.Key_H, Qt.Key.Key_V)
        ) or (
            modifiers
            in (Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.AltModifier)
            and event.key()
            in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down)
        )
        if object_edit or should_override_chemdraw_shortcut_for(self.canvas, event):
            # Do not cancel on modifier presses alone: Shift is also the live
            # gesture's snapping modifier. Only an editing shortcut cancels.
            self._prepare_for_document_edit()
            self.hover.refresh()
        handle_shortcut = getattr(
            self.chemdraw_shortcut_service, "handle_shortcut", None
        )
        if callable(handle_shortcut):
            return bool(handle_shortcut(event))
        return False

    def _is_offsheet_structure_edit(self, event) -> bool:
        if shortcut_modifiers_for(event) not in (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.ShiftModifier,
        ):
            return False
        focus_item = focused_scene_item_for(self.canvas)
        if isinstance(focus_item, QGraphicsTextItem) and (
            focus_item.textInteractionFlags()
            & Qt.TextInteractionFlag.TextEditorInteraction
        ):
            return False
        position = scene_pos_from_global_pos_for(self.canvas, QCursor.pos())
        if position is None or scene_pos_in_sheet_for(self.canvas, position):
            return False
        # Resolve only on an attempted key edit. The normal off-sheet hover
        # remains empty, so no highlight or per-move warning is introduced.
        hit = selection_service_from_canvas(
            self.canvas
        ).preferred_structure_hit_at_scene_pos(position)
        if hit is None or hit.kind not in {"atom", "bond"}:
            return False
        return event.key() in (
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Delete,
        ) or structure_edit_shortcut_matches(
            event, atom=hit.kind == "atom", bond=hit.kind == "bond"
        )

    def should_override_chemdraw_shortcut(self, event) -> bool:
        self.hover.refresh()
        return should_override_chemdraw_shortcut_for(
            self.canvas, event
        ) or self._is_offsheet_structure_edit(event)

    def event(self, event, *, native_gesture_event_type=QNativeGestureEvent) -> bool:
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
            and event.modifiers()
            in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier)
        ):
            focus_item = focused_scene_item_for(self.canvas)
            editing_text = isinstance(focus_item, QGraphicsTextItem) and bool(
                focus_item.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
            )
            # A committed note can remain the scene's remembered focus item.
            # The scene then consumes Tab without moving focus. Outside a live
            # text editor, traversal belongs to the containing widget chain.
            if not editing_text:
                forward = event.key() != Qt.Key.Key_Backtab and not (
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                )
                if QWidget.focusNextPrevChild(self.canvas, forward):
                    event.accept()
                    return True
        if (
            event.type() == QEvent.Type.ShortcutOverride
            and self.should_override_chemdraw_shortcut(event)
        ):
            event.accept()
            return True
        if event.type() == QEvent.Type.NativeGesture and isinstance(
            event, native_gesture_event_type
        ):
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
