import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QApplication, QGraphicsView

from chemvas.ui.canvas.canvas_view import CanvasView
from chemvas.ui.canvas.input_view_access import should_override_chemdraw_shortcut_for
from tests.canvas_factory import build_canvas_view


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


class CanvasViewEventShortcutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _new_view(self):
        view = build_canvas_view()
        view.runtime_state.input_view_state.base_transform = QTransform().translate(
            3.0, 4.0
        )
        view.setTransform(QTransform().scale(2.0, 2.0))
        view.services.tool_controller.active = None
        return view

    def test_event_accepts_supported_native_gestures_and_resets_transform(self) -> None:
        gestures = (
            Qt.NativeGestureType.PanNativeGesture,
            Qt.NativeGestureType.ZoomNativeGesture,
            Qt.NativeGestureType.RotateNativeGesture,
            Qt.NativeGestureType.SmartZoomNativeGesture,
        )
        with mock.patch.object(
            QGraphicsView, "event", new=mock.Mock(return_value=False)
        ) as base_event:

            class _FakeNativeGestureEvent(_FakeEvent):
                pass

            with mock.patch(
                "chemvas.ui.canvas.canvas_view.QNativeGestureEvent",
                _FakeNativeGestureEvent,
            ):
                for gesture_type in gestures:
                    view = self._new_view()
                    base_event.reset_mock()
                    event = _FakeNativeGestureEvent(
                        QEvent.Type.NativeGesture,
                        gesture_type=gesture_type,
                    )
                    self.assertTrue(CanvasView.event(view, event))
                    event.accept.assert_called_once_with()
                    self.assertTrue(
                        view.runtime_state.input_view_state.base_transform.isIdentity()
                    )
                    self.assertTrue(view.transform().isIdentity())
                    self.assertEqual(base_event.call_count, 0)

    def test_event_falls_back_to_super_for_non_matching_native_gesture(self) -> None:
        with mock.patch.object(
            QGraphicsView, "event", new=mock.Mock(return_value=False)
        ) as base_event:

            class _FakeNativeGestureEvent(_FakeEvent):
                pass

            with mock.patch(
                "chemvas.ui.canvas.canvas_view.QNativeGestureEvent",
                _FakeNativeGestureEvent,
            ):
                view = self._new_view()
                base_event.reset_mock()
                event = _FakeNativeGestureEvent(
                    QEvent.Type.NativeGesture,
                    gesture_type=object(),
                )
                self.assertFalse(CanvasView.event(view, event))
                event.accept.assert_not_called()
                self.assertFalse(
                    view.runtime_state.input_view_state.base_transform.isIdentity()
                )
                self.assertFalse(view.transform().isIdentity())
                self.assertEqual(base_event.call_count, 1)

    def test_should_override_chemdraw_shortcut_uses_hover_state_and_modifiers(
        self,
    ) -> None:
        atom_view = self._new_view()
        atom_view.runtime_state.hover_preview_state.atom_id = 7
        atom_event = _FakeEvent(
            modifiers=Qt.KeyboardModifier.NoModifier,
            key=Qt.Key.Key_Return,
            text="",
        )
        self.assertTrue(should_override_chemdraw_shortcut_for(atom_view, atom_event))

        dimethyl_event = _FakeEvent(
            modifiers=Qt.KeyboardModifier.NoModifier,
            key=Qt.Key.Key_unknown,
            text="9",
        )
        self.assertTrue(
            should_override_chemdraw_shortcut_for(atom_view, dimethyl_event)
        )

        bond_view = self._new_view()
        bond_view.runtime_state.hover_preview_state.bond_id = 11
        bond_event = _FakeEvent(
            modifiers=Qt.KeyboardModifier.NoModifier,
            key=Qt.Key.Key_unknown,
            text="b",
        )
        self.assertTrue(should_override_chemdraw_shortcut_for(bond_view, bond_event))

        for text in ("c", "d", "l", "r", "D"):
            bond_style_event = _FakeEvent(
                modifiers=Qt.KeyboardModifier.NoModifier,
                key=Qt.Key.Key_unknown,
                text=text,
            )
            self.assertTrue(
                should_override_chemdraw_shortcut_for(bond_view, bond_style_event)
            )

        reject_view = self._new_view()
        reject_view.runtime_state.hover_preview_state.atom_id = 3
        reject_event = _FakeEvent(
            modifiers=Qt.KeyboardModifier.ControlModifier,
            key=Qt.Key.Key_Return,
            text="c",
        )
        self.assertFalse(
            should_override_chemdraw_shortcut_for(reject_view, reject_event)
        )
