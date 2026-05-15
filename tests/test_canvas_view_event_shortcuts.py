import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtWidgets import QApplication, QGraphicsView
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_view import CanvasView


class _FakeEvent:
    def __init__(
        self,
        event_type=None,
        *,
        modifiers=Qt.KeyboardModifier.NoModifier,
        key=Qt.Key.Key_unknown,
        text="",
        gesture_type=None,
    ) -> None:
        self._event_type = event_type
        self._modifiers = modifiers
        self._key = key
        self._text = text
        self._gesture_type = gesture_type
        self.accept = mock.Mock()

    def type(self):
        return self._event_type

    def modifiers(self):
        return self._modifiers

    def key(self):
        return self._key

    def text(self):
        return self._text

    def gestureType(self):
        return self._gesture_type


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewEventShortcutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _new_view(self):
        view = CanvasView()
        view._refresh_hover_from_cursor = mock.Mock()
        view._reset_view_transform = mock.Mock()
        view.tools = SimpleNamespace(active=None)
        return view

    def test_event_accepts_supported_native_gestures_and_resets_transform(self) -> None:
        gestures = (
            Qt.NativeGestureType.PanNativeGesture,
            Qt.NativeGestureType.ZoomNativeGesture,
            Qt.NativeGestureType.RotateNativeGesture,
            Qt.NativeGestureType.SmartZoomNativeGesture,
        )
        with mock.patch.object(QGraphicsView, "event", new=mock.Mock(return_value=False)) as base_event:
            class _FakeNativeGestureEvent(_FakeEvent):
                pass

            with mock.patch("ui.canvas_view.QNativeGestureEvent", _FakeNativeGestureEvent):
                for gesture_type in gestures:
                    view = self._new_view()
                    base_event.reset_mock()
                    event = _FakeNativeGestureEvent(
                        QEvent.Type.NativeGesture,
                        gesture_type=gesture_type,
                    )
                    self.assertTrue(CanvasView.event(view, event))
                    event.accept.assert_called_once_with()
                    view._reset_view_transform.assert_called_once_with()
                    self.assertEqual(base_event.call_count, 0)

    def test_event_falls_back_to_super_for_non_matching_native_gesture(self) -> None:
        with mock.patch.object(QGraphicsView, "event", new=mock.Mock(return_value=False)) as base_event:
            class _FakeNativeGestureEvent(_FakeEvent):
                pass

            with mock.patch("ui.canvas_view.QNativeGestureEvent", _FakeNativeGestureEvent):
                view = self._new_view()
                base_event.reset_mock()
                event = _FakeNativeGestureEvent(
                    QEvent.Type.NativeGesture,
                    gesture_type=object(),
                )
                self.assertFalse(CanvasView.event(view, event))
                event.accept.assert_not_called()
                view._reset_view_transform.assert_not_called()
                self.assertEqual(base_event.call_count, 1)

    def test_should_override_chemdraw_shortcut_uses_hover_state_and_modifiers(self) -> None:
        atom_view = self._new_view()
        atom_view.hover_atom_id = 7
        atom_event = _FakeEvent(
            modifiers=Qt.KeyboardModifier.NoModifier,
            key=Qt.Key.Key_Return,
            text="",
        )
        self.assertTrue(CanvasView._should_override_chemdraw_shortcut(atom_view, atom_event))
        atom_view._refresh_hover_from_cursor.assert_called_once_with()

        bond_view = self._new_view()
        bond_view.hover_bond_id = 11
        bond_event = _FakeEvent(
            modifiers=Qt.KeyboardModifier.NoModifier,
            key=Qt.Key.Key_unknown,
            text="b",
        )
        self.assertTrue(CanvasView._should_override_chemdraw_shortcut(bond_view, bond_event))
        bond_view._refresh_hover_from_cursor.assert_called_once_with()

        reject_view = self._new_view()
        reject_view.hover_atom_id = 3
        reject_event = _FakeEvent(
            modifiers=Qt.KeyboardModifier.ControlModifier,
            key=Qt.Key.Key_Return,
            text="c",
        )
        self.assertFalse(CanvasView._should_override_chemdraw_shortcut(reject_view, reject_event))
        reject_view._refresh_hover_from_cursor.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
