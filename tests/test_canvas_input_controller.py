import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeySequence, QTransform
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsTextItem,
        QGraphicsView,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.domain.document import Atom
    from chemvas.ui.canvas_hover_state import (
        set_hover_atom_id_for,
        set_hover_bond_id_for,
    )
    from chemvas.ui.canvas_input_controller import CanvasInputController
    from chemvas.ui.canvas_insert_state import CanvasInsertState
    from chemvas.ui.canvas_scene_items_state import set_selected_notes_for
    from chemvas.ui.input_view_state import input_view_state_for


class _Scene(QGraphicsScene):
    def __init__(self) -> None:
        super().__init__()
        self.focus_item_override = None

    def focusItem(self):
        if self.focus_item_override is not None:
            return self.focus_item_override
        return super().focusItem()


class _FakeEvent:
    def __init__(
        self,
        *,
        key=Qt.Key.Key_unknown,
        text="",
        modifiers=Qt.KeyboardModifier.NoModifier,
        matches=None,
        event_type=None,
        gesture_type=None,
    ) -> None:
        self._key = key
        self._text = text
        self._modifiers = modifiers
        self._matches = set(matches or ())
        self._event_type = event_type
        self._gesture_type = gesture_type
        self.accept = mock.Mock()

    def key(self):
        return self._key

    def text(self):
        return self._text

    def modifiers(self):
        return self._modifiers

    def matches(self, standard_key) -> bool:
        return standard_key in self._matches

    def type(self):
        return self._event_type

    def gestureType(self):
        return self._gesture_type


class _Canvas(QGraphicsView):
    def __init__(self) -> None:
        self.scene_obj = _Scene()
        super().__init__(self.scene_obj)
        self.insert_state = CanvasInsertState()
        self.insert_state.template_active = False
        self.insert_state.smiles_active = False
        insert_controller = SimpleNamespace(
            cancel_template_insert=mock.Mock(),
            cancel_smiles_insert=mock.Mock(),
        )
        self.history_service = SimpleNamespace(
            undo=mock.Mock(),
            redo=mock.Mock(),
        )
        scene_clipboard_controller = SimpleNamespace(
            copy_selection_to_clipboard=mock.Mock(return_value=False),
            paste_selection_from_clipboard=mock.Mock(return_value=False),
        )
        scene_delete_controller = SimpleNamespace(
            delete_selected_items=mock.Mock(),
            delete_atom=mock.Mock(),
            delete_bond=mock.Mock(),
            delete_ring=mock.Mock(),
        )
        atom_label_service = SimpleNamespace(add_or_update_atom_label=mock.Mock())
        hover_scene_service = SimpleNamespace(clear_hover_highlight=mock.Mock())
        self.chemdraw_shortcut_service = SimpleNamespace(
            handle_shortcut=mock.Mock(return_value=False)
        )
        self.tool_mode_controller = SimpleNamespace(set_tool=mock.Mock())
        self.services = SimpleNamespace(
            history_service=self.history_service,
            insert_controller=insert_controller,
            scene_clipboard_controller=scene_clipboard_controller,
            scene_delete_controller=scene_delete_controller,
            atom_label_service=atom_label_service,
            hover_scene_service=hover_scene_service,
            chemdraw_shortcut_service=self.chemdraw_shortcut_service,
        )
        self.hover_refresh = mock.Mock()
        self.undo = mock.Mock(
            side_effect=AssertionError("canvas undo wrapper should not run")
        )
        self.redo = mock.Mock(
            side_effect=AssertionError("canvas redo wrapper should not run")
        )
        self.copy_selection_to_clipboard = mock.Mock(
            side_effect=AssertionError("canvas copy wrapper should not run")
        )
        self.paste_selection_from_clipboard = mock.Mock(
            side_effect=AssertionError("canvas paste wrapper should not run")
        )
        self.delete_selected_items = mock.Mock(
            side_effect=AssertionError("canvas delete wrapper should not run")
        )
        self.clear_atom_label = mock.Mock(
            side_effect=AssertionError("canvas label wrapper should not run")
        )
        self.delete_atom = mock.Mock(
            side_effect=AssertionError("canvas atom delete wrapper should not run")
        )
        self.delete_bond = mock.Mock(
            side_effect=AssertionError("canvas bond delete wrapper should not run")
        )
        self._ring_for_bond = mock.Mock(return_value=None)
        self.delete_ring = mock.Mock()
        self._shortcut_modifiers = CanvasInputController.shortcut_modifiers
        self.model = SimpleNamespace(
            atoms={
                7: Atom("C", 0.0, 0.0),
                8: Atom("O", 1.0, 0.0),
            },
            bonds=[object(), object()],
        )

    def add_selected_item(self):
        item = QGraphicsRectItem(0.0, 0.0, 4.0, 4.0)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.scene_obj.addItem(item)
        item.setSelected(True)
        return item


def _input_controller(canvas: _Canvas) -> CanvasInputController:
    return CanvasInputController(
        canvas,
        scene_delete_controller=canvas.services.scene_delete_controller,
        scene_clipboard_controller=canvas.services.scene_clipboard_controller,
        history_service=canvas.services.history_service,
        hover_refresh=canvas.hover_refresh,
        chemdraw_shortcut_service=canvas.chemdraw_shortcut_service,
        tool_mode_controller=canvas.tool_mode_controller,
    )


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas input controller tests"
)
class CanvasInputControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_key_press_event_covers_text_editor_escape_and_standard_shortcuts(
        self,
    ) -> None:
        canvas = _Canvas()
        controller = _input_controller(canvas)

        focus_item = QGraphicsTextItem()
        focus_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        canvas.scene_obj.focus_item_override = focus_item
        with mock.patch.object(
            QGraphicsView, "keyPressEvent", new=mock.Mock(return_value=None)
        ) as base_key_press:
            controller.key_press_event(_FakeEvent(key=Qt.Key.Key_A))
        base_key_press.assert_called_once()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        canvas.scene_obj.focus_item_override = QGraphicsTextItem()
        canvas.insert_state.template_active = True
        template_event = _FakeEvent(key=Qt.Key.Key_Escape)
        controller.key_press_event(template_event)
        canvas.services.insert_controller.cancel_template_insert.assert_called_once_with()
        template_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        canvas.insert_state.smiles_active = True
        smiles_event = _FakeEvent(key=Qt.Key.Key_Escape)
        controller.key_press_event(smiles_event)
        canvas.services.insert_controller.cancel_smiles_insert.assert_called_once_with()
        smiles_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        undo_event = _FakeEvent(
            key=Qt.Key.Key_Z, matches={QKeySequence.StandardKey.Undo}
        )
        redo_event = _FakeEvent(
            key=Qt.Key.Key_Y, matches={QKeySequence.StandardKey.Redo}
        )
        copy_event = _FakeEvent(
            key=Qt.Key.Key_C, matches={QKeySequence.StandardKey.Copy}
        )
        paste_event = _FakeEvent(
            key=Qt.Key.Key_V, matches={QKeySequence.StandardKey.Paste}
        )
        canvas.services.scene_clipboard_controller.copy_selection_to_clipboard.return_value = True
        canvas.services.scene_clipboard_controller.paste_selection_from_clipboard.return_value = True

        controller.key_press_event(undo_event)
        controller.key_press_event(redo_event)
        controller.key_press_event(copy_event)
        controller.key_press_event(paste_event)

        canvas.history_service.undo.assert_called_once_with()
        canvas.history_service.redo.assert_called_once_with()
        canvas.services.scene_clipboard_controller.copy_selection_to_clipboard.assert_called_once_with()
        canvas.services.scene_clipboard_controller.paste_selection_from_clipboard.assert_called_once_with()
        canvas.undo.assert_not_called()
        canvas.redo.assert_not_called()
        canvas.copy_selection_to_clipboard.assert_not_called()
        canvas.paste_selection_from_clipboard.assert_not_called()
        undo_event.accept.assert_called_once_with()
        redo_event.accept.assert_called_once_with()
        copy_event.accept.assert_called_once_with()
        paste_event.accept.assert_called_once_with()

    def test_key_press_select_all_switches_to_select_tool_and_selects(self) -> None:
        canvas = _Canvas()
        controller = _input_controller(canvas)
        event = _FakeEvent(
            key=Qt.Key.Key_A, matches={QKeySequence.StandardKey.SelectAll}
        )

        with mock.patch(
            "chemvas.ui.canvas_input_controller.select_all_scene_items_for",
            return_value=True,
        ) as select_all:
            controller.key_press_event(event)

        canvas.tool_mode_controller.set_tool.assert_called_once_with("select")
        select_all.assert_called_once_with(canvas)
        event.accept.assert_called_once_with()

    def test_key_press_ctrl_g_groups_and_ctrl_shift_g_ungroups(self) -> None:
        canvas = _Canvas()
        controller = _input_controller(canvas)
        group_event = _FakeEvent(
            key=Qt.Key.Key_G,
            modifiers=Qt.KeyboardModifier.ControlModifier,
        )
        ungroup_event = _FakeEvent(
            key=Qt.Key.Key_G,
            modifiers=Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.ShiftModifier,
        )

        with (
            mock.patch(
                "chemvas.ui.canvas_input_controller.group_selection_for",
                return_value=True,
            ) as group,
            mock.patch(
                "chemvas.ui.canvas_input_controller.ungroup_selection_for",
                return_value=True,
            ) as ungroup,
        ):
            controller.key_press_event(group_event)
            controller.key_press_event(ungroup_event)

        group.assert_called_once_with(canvas)
        ungroup.assert_called_once_with(canvas)
        group_event.accept.assert_called_once_with()
        ungroup_event.accept.assert_called_once_with()

    def test_key_press_event_view_function_keys_and_cut(self) -> None:
        canvas = _Canvas()
        controller = _input_controller(canvas)

        with (
            mock.patch(
                "chemvas.ui.canvas_input_controller.reset_zoom_for"
            ) as reset_zoom,
            mock.patch(
                "chemvas.ui.canvas_input_controller.fit_canvas_to_view_for"
            ) as fit_view,
            mock.patch("chemvas.ui.canvas_input_controller.zoom_in_for") as zoom_in,
            mock.patch("chemvas.ui.canvas_input_controller.zoom_out_for") as zoom_out,
        ):
            for key in (Qt.Key.Key_F5, Qt.Key.Key_F6, Qt.Key.Key_F7, Qt.Key.Key_F8):
                event = _FakeEvent(key=key)
                controller.key_press_event(event)
                event.accept.assert_called_once_with()
        reset_zoom.assert_called_once_with(canvas)
        fit_view.assert_called_once_with(canvas)
        zoom_in.assert_called_once_with(canvas)
        zoom_out.assert_called_once_with(canvas)

        cut_event = _FakeEvent(key=Qt.Key.Key_X, matches={QKeySequence.StandardKey.Cut})
        canvas.services.scene_clipboard_controller.copy_selection_to_clipboard.return_value = True
        controller.key_press_event(cut_event)
        canvas.services.scene_clipboard_controller.copy_selection_to_clipboard.assert_called_once_with()
        canvas.services.scene_delete_controller.delete_selected_items.assert_called_once_with()
        cut_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        empty_cut_event = _FakeEvent(
            key=Qt.Key.Key_X, matches={QKeySequence.StandardKey.Cut}
        )
        with mock.patch.object(
            QGraphicsView, "keyPressEvent", new=mock.Mock(return_value=None)
        ):
            controller.key_press_event(empty_cut_event)
        canvas.services.scene_delete_controller.delete_selected_items.assert_not_called()
        empty_cut_event.accept.assert_not_called()

    def test_key_press_event_escape_copy_and_paste_false_paths_fall_through(
        self,
    ) -> None:
        canvas = _Canvas()
        controller = _input_controller(canvas)

        escape_event = _FakeEvent(key=Qt.Key.Key_Escape)
        copy_event = _FakeEvent(
            key=Qt.Key.Key_C, matches={QKeySequence.StandardKey.Copy}
        )
        paste_event = _FakeEvent(
            key=Qt.Key.Key_V, matches={QKeySequence.StandardKey.Paste}
        )

        with mock.patch.object(
            QGraphicsView, "keyPressEvent", new=mock.Mock(return_value=None)
        ) as base_key_press:
            controller.key_press_event(escape_event)
            controller.key_press_event(copy_event)
            controller.key_press_event(paste_event)

        self.assertEqual(base_key_press.call_count, 3)
        escape_event.accept.assert_not_called()
        copy_event.accept.assert_not_called()
        paste_event.accept.assert_not_called()

    def test_key_press_event_covers_delete_chemdraw_and_fallback_paths(self) -> None:
        canvas = _Canvas()
        controller = _input_controller(canvas)
        canvas.add_selected_item()
        selected_delete_event = _FakeEvent(key=Qt.Key.Key_Delete)
        controller.key_press_event(selected_delete_event)
        canvas.services.scene_delete_controller.delete_selected_items.assert_called_once_with()
        canvas.delete_selected_items.assert_not_called()
        selected_delete_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        note = QGraphicsTextItem("note")
        note.setData(0, "note")
        canvas.scene_obj.addItem(note)
        set_selected_notes_for(canvas, [note])
        note_delete_event = _FakeEvent(key=Qt.Key.Key_Delete)
        controller.key_press_event(note_delete_event)
        canvas.services.scene_delete_controller.delete_selected_items.assert_called_once_with()
        note_delete_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        set_hover_atom_id_for(canvas, 7)
        atom_delete_event = _FakeEvent(key=Qt.Key.Key_Delete)
        controller.key_press_event(atom_delete_event)
        canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        canvas.services.scene_delete_controller.delete_atom.assert_called_once_with(
            7, record=True
        )
        canvas.delete_atom.assert_not_called()
        atom_delete_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        set_hover_atom_id_for(canvas, 8)
        label_clear_event = _FakeEvent(key=Qt.Key.Key_Backspace)
        controller.key_press_event(label_clear_event)
        canvas.services.atom_label_service.add_or_update_atom_label.assert_called_once_with(
            8, "C", show_carbon=False
        )
        canvas.clear_atom_label.assert_not_called()
        canvas.services.scene_delete_controller.delete_atom.assert_not_called()
        label_clear_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        set_hover_bond_id_for(canvas, 1)

        def clear_hover() -> None:
            set_hover_bond_id_for(canvas, None)

        canvas.services.hover_scene_service.clear_hover_highlight.side_effect = (
            clear_hover
        )
        bond_delete_event = _FakeEvent(key=Qt.Key.Key_Delete)
        controller.key_press_event(bond_delete_event)
        canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        canvas.services.scene_delete_controller.delete_bond.assert_called_once_with(
            1, record=True
        )
        canvas.delete_bond.assert_not_called()
        bond_delete_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        noop_delete_event = _FakeEvent(key=Qt.Key.Key_Delete)
        controller.key_press_event(noop_delete_event)
        noop_delete_event.accept.assert_called_once_with()
        canvas.services.scene_delete_controller.delete_ring.assert_not_called()

        canvas = _Canvas()
        canvas.chemdraw_shortcut_service.handle_shortcut.return_value = True
        controller = _input_controller(canvas)
        shortcut_event = _FakeEvent(key=Qt.Key.Key_A)
        controller.key_press_event(shortcut_event)
        canvas.chemdraw_shortcut_service.handle_shortcut.assert_called_once_with(
            shortcut_event
        )
        shortcut_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        fallback_event = _FakeEvent(key=Qt.Key.Key_A)
        with mock.patch.object(
            QGraphicsView, "keyPressEvent", new=mock.Mock(return_value=None)
        ) as base_key_press:
            controller.key_press_event(fallback_event)
        base_key_press.assert_called_once()

    def test_shortcut_override_and_event_paths_cover_service_and_native_gesture(
        self,
    ) -> None:
        canvas = _Canvas()
        canvas.chemdraw_shortcut_service.handle_shortcut.return_value = True
        controller = _input_controller(canvas)

        event = _FakeEvent(key=Qt.Key.Key_A)
        self.assertTrue(controller.handle_chemdraw_shortcut(event))
        canvas.chemdraw_shortcut_service.handle_shortcut.assert_called_once_with(event)

        atom_event = _FakeEvent(
            key=Qt.Key.Key_Return,
            modifiers=Qt.KeyboardModifier.NoModifier,
        )
        set_hover_atom_id_for(canvas, 3)
        self.assertTrue(controller.should_override_chemdraw_shortcut(atom_event))

        bond_event = _FakeEvent(
            key=Qt.Key.Key_unknown,
            text="b",
            modifiers=Qt.KeyboardModifier.ShiftModifier,
        )
        set_hover_atom_id_for(canvas, None)
        set_hover_bond_id_for(canvas, 5)
        self.assertTrue(controller.should_override_chemdraw_shortcut(bond_event))

        reject_event = _FakeEvent(
            key=Qt.Key.Key_unknown,
            text="c",
            modifiers=Qt.KeyboardModifier.ControlModifier,
        )
        set_hover_bond_id_for(canvas, None)
        self.assertFalse(controller.should_override_chemdraw_shortcut(reject_event))
        self.assertEqual(canvas.hover_refresh.call_count, 3)

        canvas = _Canvas()
        controller = _input_controller(canvas)
        set_hover_atom_id_for(canvas, 3)
        shortcut_override_event = _FakeEvent(
            event_type=QEvent.Type.ShortcutOverride,
            key=Qt.Key.Key_Return,
        )
        with mock.patch.object(
            QGraphicsView, "event", new=mock.Mock(return_value=False)
        ) as base_event:
            self.assertTrue(controller.event(shortcut_override_event))
        canvas.hover_refresh.assert_called_once_with()
        shortcut_override_event.accept.assert_called_once_with()
        base_event.assert_not_called()

        class _FakeNativeGestureEvent(_FakeEvent):
            pass

        canvas = _Canvas()
        controller = _input_controller(canvas)
        input_view_state_for(canvas).base_transform = QTransform().translate(3.0, 4.0)
        canvas.setTransform(QTransform().scale(2.0, 2.0))
        native_event = _FakeNativeGestureEvent(
            event_type=QEvent.Type.NativeGesture,
            gesture_type=Qt.NativeGestureType.ZoomNativeGesture,
        )
        with mock.patch.object(
            QGraphicsView, "event", new=mock.Mock(return_value=False)
        ) as base_event:
            self.assertTrue(
                controller.event(
                    native_event, native_gesture_event_type=_FakeNativeGestureEvent
                )
            )
        self.assertTrue(input_view_state_for(canvas).base_transform.isIdentity())
        self.assertTrue(canvas.transform().isIdentity())
        native_event.accept.assert_called_once_with()
        base_event.assert_not_called()

        canvas = _Canvas()
        controller = _input_controller(canvas)
        fallback_event = _FakeNativeGestureEvent(
            event_type=QEvent.Type.NativeGesture,
            gesture_type=object(),
        )
        with mock.patch.object(
            QGraphicsView, "event", new=mock.Mock(return_value=False)
        ) as base_event:
            self.assertFalse(
                controller.event(
                    fallback_event, native_gesture_event_type=_FakeNativeGestureEvent
                )
            )
        base_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
