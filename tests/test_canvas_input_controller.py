import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeySequence
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


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.canvas_input_controller import CanvasInputController


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
        self._refresh_hover_from_cursor = mock.Mock()
        self._template_insert_active = False
        self._smiles_insert_active = False
        self._cancel_template_insert = mock.Mock()
        self._cancel_smiles_insert = mock.Mock()
        self.undo = mock.Mock()
        self.redo = mock.Mock()
        self.copy_selection_to_clipboard = mock.Mock(return_value=False)
        self.paste_selection_from_clipboard = mock.Mock(return_value=False)
        self.delete_selected_items = mock.Mock()
        self.hover_atom_id = None
        self.hover_bond_id = None
        self._atom_has_visible_label = mock.Mock(return_value=False)
        self.clear_atom_label = mock.Mock()
        self.delete_atom = mock.Mock()
        self._clear_hover_highlight = mock.Mock()
        self.delete_bond = mock.Mock()
        self._ring_for_bond = mock.Mock(return_value=None)
        self.delete_ring = mock.Mock()
        self._handle_chemdraw_shortcut = mock.Mock(return_value=False)
        self._shortcut_modifiers = CanvasInputController.shortcut_modifiers
        self._should_override_chemdraw_shortcut = mock.Mock(return_value=False)
        self._reset_view_transform = mock.Mock()
        self.model = SimpleNamespace(bonds=[object(), object()])

    def add_selected_item(self):
        item = QGraphicsRectItem(0.0, 0.0, 4.0, 4.0)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.scene_obj.addItem(item)
        item.setSelected(True)
        return item


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas input controller tests")
class CanvasInputControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_key_press_event_covers_text_editor_escape_and_standard_shortcuts(self) -> None:
        canvas = _Canvas()
        controller = CanvasInputController(canvas)

        focus_item = QGraphicsTextItem()
        focus_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        canvas.scene_obj.focus_item_override = focus_item
        with mock.patch.object(QGraphicsView, "keyPressEvent", new=mock.Mock(return_value=None)) as base_key_press:
            controller.key_press_event(_FakeEvent(key=Qt.Key.Key_A))
        base_key_press.assert_called_once()

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        canvas.scene_obj.focus_item_override = QGraphicsTextItem()
        canvas._template_insert_active = True
        template_event = _FakeEvent(key=Qt.Key.Key_Escape)
        controller.key_press_event(template_event)
        canvas._cancel_template_insert.assert_called_once_with()
        template_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        canvas._smiles_insert_active = True
        smiles_event = _FakeEvent(key=Qt.Key.Key_Escape)
        controller.key_press_event(smiles_event)
        canvas._cancel_smiles_insert.assert_called_once_with()
        smiles_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        undo_event = _FakeEvent(key=Qt.Key.Key_Z, matches={QKeySequence.StandardKey.Undo})
        redo_event = _FakeEvent(key=Qt.Key.Key_Y, matches={QKeySequence.StandardKey.Redo})
        copy_event = _FakeEvent(key=Qt.Key.Key_C, matches={QKeySequence.StandardKey.Copy})
        paste_event = _FakeEvent(key=Qt.Key.Key_V, matches={QKeySequence.StandardKey.Paste})
        canvas.copy_selection_to_clipboard.return_value = True
        canvas.paste_selection_from_clipboard.return_value = True

        controller.key_press_event(undo_event)
        controller.key_press_event(redo_event)
        controller.key_press_event(copy_event)
        controller.key_press_event(paste_event)

        canvas.undo.assert_called_once_with()
        canvas.redo.assert_called_once_with()
        canvas.copy_selection_to_clipboard.assert_called_once_with()
        canvas.paste_selection_from_clipboard.assert_called_once_with()
        undo_event.accept.assert_called_once_with()
        redo_event.accept.assert_called_once_with()
        copy_event.accept.assert_called_once_with()
        paste_event.accept.assert_called_once_with()

    def test_key_press_event_escape_copy_and_paste_false_paths_fall_through(self) -> None:
        canvas = _Canvas()
        controller = CanvasInputController(canvas)

        escape_event = _FakeEvent(key=Qt.Key.Key_Escape)
        copy_event = _FakeEvent(key=Qt.Key.Key_C, matches={QKeySequence.StandardKey.Copy})
        paste_event = _FakeEvent(key=Qt.Key.Key_V, matches={QKeySequence.StandardKey.Paste})

        with mock.patch.object(QGraphicsView, "keyPressEvent", new=mock.Mock(return_value=None)) as base_key_press:
            controller.key_press_event(escape_event)
            controller.key_press_event(copy_event)
            controller.key_press_event(paste_event)

        self.assertEqual(base_key_press.call_count, 3)
        escape_event.accept.assert_not_called()
        copy_event.accept.assert_not_called()
        paste_event.accept.assert_not_called()

    def test_key_press_event_covers_delete_chemdraw_and_fallback_paths(self) -> None:
        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        canvas.add_selected_item()
        selected_delete_event = _FakeEvent(key=Qt.Key.Key_Delete)
        controller.key_press_event(selected_delete_event)
        canvas.delete_selected_items.assert_called_once_with()
        selected_delete_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        canvas.hover_atom_id = 7
        canvas._atom_has_visible_label.return_value = False
        atom_delete_event = _FakeEvent(key=Qt.Key.Key_Delete)
        controller.key_press_event(atom_delete_event)
        canvas.delete_atom.assert_called_once_with(7, record=True)
        atom_delete_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        canvas.hover_bond_id = 1
        bond_delete_event = _FakeEvent(key=Qt.Key.Key_Delete)
        controller.key_press_event(bond_delete_event)
        canvas._clear_hover_highlight.assert_called_once_with()
        canvas.delete_bond.assert_called_once_with(1, record=True)
        bond_delete_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        noop_delete_event = _FakeEvent(key=Qt.Key.Key_Delete)
        controller.key_press_event(noop_delete_event)
        noop_delete_event.accept.assert_called_once_with()
        canvas.delete_ring.assert_not_called()

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        canvas._handle_chemdraw_shortcut.return_value = True
        shortcut_event = _FakeEvent(key=Qt.Key.Key_A)
        controller.key_press_event(shortcut_event)
        canvas._handle_chemdraw_shortcut.assert_called_once_with(shortcut_event)
        shortcut_event.accept.assert_called_once_with()

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        fallback_event = _FakeEvent(key=Qt.Key.Key_A)
        with mock.patch.object(QGraphicsView, "keyPressEvent", new=mock.Mock(return_value=None)) as base_key_press:
            controller.key_press_event(fallback_event)
        base_key_press.assert_called_once()

    def test_shortcut_override_and_event_paths_cover_service_and_native_gesture(self) -> None:
        canvas = _Canvas()
        controller = CanvasInputController(canvas)

        with mock.patch(
            "ui.canvas_input_controller.canvas_chemdraw_shortcut_service_for",
            return_value=SimpleNamespace(handle_shortcut=mock.Mock(return_value=True)),
        ) as service_for:
            event = _FakeEvent(key=Qt.Key.Key_A)
            self.assertTrue(controller.handle_chemdraw_shortcut(event))
        service_for.assert_called_once_with(canvas)

        atom_event = _FakeEvent(
            key=Qt.Key.Key_Return,
            modifiers=Qt.KeyboardModifier.NoModifier,
        )
        canvas.hover_atom_id = 3
        self.assertTrue(controller.should_override_chemdraw_shortcut(atom_event))

        bond_event = _FakeEvent(
            key=Qt.Key.Key_unknown,
            text="b",
            modifiers=Qt.KeyboardModifier.ShiftModifier,
        )
        canvas.hover_atom_id = None
        canvas.hover_bond_id = 5
        self.assertTrue(controller.should_override_chemdraw_shortcut(bond_event))

        reject_event = _FakeEvent(
            key=Qt.Key.Key_unknown,
            text="c",
            modifiers=Qt.KeyboardModifier.ControlModifier,
        )
        canvas.hover_bond_id = None
        self.assertFalse(controller.should_override_chemdraw_shortcut(reject_event))

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        canvas._should_override_chemdraw_shortcut = mock.Mock(return_value=True)
        shortcut_override_event = _FakeEvent(event_type=QEvent.Type.ShortcutOverride)
        with mock.patch.object(QGraphicsView, "event", new=mock.Mock(return_value=False)) as base_event:
            self.assertTrue(controller.event(shortcut_override_event))
        canvas._should_override_chemdraw_shortcut.assert_called_once_with(shortcut_override_event)
        shortcut_override_event.accept.assert_called_once_with()
        base_event.assert_not_called()

        class _FakeNativeGestureEvent(_FakeEvent):
            pass

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        native_event = _FakeNativeGestureEvent(
            event_type=QEvent.Type.NativeGesture,
            gesture_type=Qt.NativeGestureType.ZoomNativeGesture,
        )
        with mock.patch.object(QGraphicsView, "event", new=mock.Mock(return_value=False)) as base_event:
            self.assertTrue(controller.event(native_event, native_gesture_event_type=_FakeNativeGestureEvent))
        canvas._reset_view_transform.assert_called_once_with()
        native_event.accept.assert_called_once_with()
        base_event.assert_not_called()

        canvas = _Canvas()
        controller = CanvasInputController(canvas)
        fallback_event = _FakeNativeGestureEvent(
            event_type=QEvent.Type.NativeGesture,
            gesture_type=object(),
        )
        with mock.patch.object(QGraphicsView, "event", new=mock.Mock(return_value=False)) as base_event:
            self.assertFalse(controller.event(fallback_event, native_gesture_event_type=_FakeNativeGestureEvent))
        base_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
