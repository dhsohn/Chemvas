import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
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
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.NoButton,
        modifiers=Qt.KeyboardModifier.NoModifier,
        key=Qt.Key.Key_unknown,
        text="",
        gesture_type=None,
    ) -> None:
        self._event_type = event_type
        self._button = button
        self._buttons = buttons
        self._modifiers = modifiers
        self._key = key
        self._text = text
        self._gesture_type = gesture_type
        self.accept = mock.Mock()

    def type(self):
        return self._event_type

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def modifiers(self):
        return self._modifiers

    def key(self):
        return self._key

    def text(self):
        return self._text

    def gestureType(self):
        return self._gesture_type


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewEventWrapperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _new_view(self, *, tool_active=None):
        view = CanvasView()
        view._touch_interaction = mock.Mock()
        view._clear_hover_highlight = mock.Mock()
        view._refresh_hover_from_cursor = mock.Mock()
        view._render_template_preview = mock.Mock()
        view._render_smiles_preview = mock.Mock()
        view._update_hover_highlight = mock.Mock()
        view._commit_template_insert = mock.Mock()
        view._commit_smiles_insert = mock.Mock()
        view._reset_view_transform = mock.Mock()
        view.scene_pos_from_event = mock.Mock(return_value=QPointF(4.0, 5.0))
        view.tools = SimpleNamespace(active=tool_active)
        return view

    def test_mouse_press_event_handles_template_smiles_and_tool_branches(self) -> None:
        press_event = _FakeEvent(button=Qt.MouseButton.LeftButton)

        template_view = self._new_view(
            tool_active=SimpleNamespace(
                on_mouse_press=mock.Mock(side_effect=AssertionError("tool should not run"))
            )
        )
        template_view._template_insert_active = True
        CanvasView.mousePressEvent(template_view, press_event)
        self.assertEqual(template_view._commit_template_insert.call_count, 1)
        self.assertEqual(template_view._clear_hover_highlight.call_count, 1)
        self.assertEqual(template_view.tools.active.on_mouse_press.call_count, 0)

        smiles_view = self._new_view(
            tool_active=SimpleNamespace(
                on_mouse_press=mock.Mock(side_effect=AssertionError("tool should not run"))
            )
        )
        smiles_view._smiles_insert_active = True
        CanvasView.mousePressEvent(smiles_view, press_event)
        self.assertEqual(smiles_view._commit_smiles_insert.call_count, 1)
        self.assertEqual(smiles_view._clear_hover_highlight.call_count, 1)
        self.assertEqual(smiles_view.tools.active.on_mouse_press.call_count, 0)

        tool = SimpleNamespace(
            on_mouse_press=mock.Mock(return_value=True),
        )
        tool_view = self._new_view(tool_active=tool)
        CanvasView.mousePressEvent(tool_view, press_event)
        tool.on_mouse_press.assert_called_once_with(press_event)
        self.assertEqual(tool_view._clear_hover_highlight.call_count, 1)
        self.assertEqual(tool_view._commit_template_insert.call_count, 0)
        self.assertEqual(tool_view._commit_smiles_insert.call_count, 0)

    def test_mouse_move_event_handles_preview_hover_and_tool_branches(self) -> None:
        move_event = _FakeEvent(buttons=Qt.MouseButton.NoButton)

        template_view = self._new_view()
        template_view._template_insert_active = True
        CanvasView.mouseMoveEvent(template_view, move_event)
        template_view._render_template_preview.assert_called_once_with(QPointF(4.0, 5.0))
        template_view._render_smiles_preview.assert_not_called()
        template_view._update_hover_highlight.assert_not_called()

        smiles_view = self._new_view()
        smiles_view._smiles_insert_active = True
        CanvasView.mouseMoveEvent(smiles_view, move_event)
        smiles_view._render_smiles_preview.assert_called_once_with(QPointF(4.0, 5.0))
        smiles_view._render_template_preview.assert_not_called()
        smiles_view._update_hover_highlight.assert_not_called()

        hover_view = self._new_view()
        hover_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(4.0, 5.0),
            QPointF(4.0, 5.0),
            QPointF(4.0, 5.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        CanvasView.mouseMoveEvent(hover_view, hover_event)
        hover_view._update_hover_highlight.assert_called_once_with(QPointF(4.0, 5.0))
        hover_view._clear_hover_highlight.assert_not_called()

        tool = SimpleNamespace(on_mouse_move=mock.Mock(return_value=True))
        tool_view = self._new_view(tool_active=tool)
        drag_event = _FakeEvent(buttons=Qt.MouseButton.LeftButton)
        CanvasView.mouseMoveEvent(tool_view, drag_event)
        tool.on_mouse_move.assert_called_once_with(drag_event)
        self.assertEqual(tool_view._clear_hover_highlight.call_count, 1)
        tool_view._update_hover_highlight.assert_not_called()

    def test_mouse_release_event_refreshes_hover_after_tool_handler(self) -> None:
        tool = SimpleNamespace(on_mouse_release=mock.Mock(return_value=True))
        view = self._new_view(tool_active=tool)
        release_event = _FakeEvent(button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.NoButton)

        CanvasView.mouseReleaseEvent(view, release_event)

        tool.on_mouse_release.assert_called_once_with(release_event)
        view._refresh_hover_from_cursor.assert_called_once_with()

    def test_viewport_event_clears_or_refreshes_hover_on_enter_leave_and_hide(self) -> None:
        with mock.patch("ui.canvas_view.QTimer.singleShot") as single_shot, mock.patch.object(
            QGraphicsView,
            "viewportEvent",
            new=mock.Mock(return_value=False),
        ) as base_event:
            enter_view = self._new_view()
            base_event.reset_mock()
            enter_event = _FakeEvent(QEvent.Type.Enter)
            self.assertFalse(CanvasView.viewportEvent(enter_view, enter_event))
            single_shot.assert_called_once_with(0, enter_view._refresh_hover_from_cursor)
            self.assertEqual(enter_view._clear_hover_highlight.call_count, 0)
            self.assertEqual(base_event.call_count, 1)

            for event_type in (QEvent.Type.Leave, QEvent.Type.Hide):
                sub_view = self._new_view()
                base_event.reset_mock()
                sub_event = _FakeEvent(event_type)
                self.assertFalse(CanvasView.viewportEvent(sub_view, sub_event))
                sub_view._clear_hover_highlight.assert_called_once_with()
                self.assertEqual(base_event.call_count, 1)

    def test_viewport_event_mouse_move_routes_preview_and_hover_updates(self) -> None:
        with mock.patch.object(
            QGraphicsView,
            "viewportEvent",
            new=mock.Mock(return_value=False),
        ) as base_event:
            template_view = self._new_view()
            base_event.reset_mock()
            template_view._template_insert_active = True
            template_event = _FakeEvent(QEvent.Type.MouseMove, buttons=Qt.MouseButton.NoButton)
            self.assertFalse(CanvasView.viewportEvent(template_view, template_event))
            template_view._render_template_preview.assert_called_once_with(QPointF(4.0, 5.0))
            self.assertEqual(base_event.call_count, 1)

            smiles_view = self._new_view()
            base_event.reset_mock()
            smiles_view._smiles_insert_active = True
            smiles_event = _FakeEvent(QEvent.Type.MouseMove, buttons=Qt.MouseButton.NoButton)
            self.assertFalse(CanvasView.viewportEvent(smiles_view, smiles_event))
            smiles_view._render_smiles_preview.assert_called_once_with(QPointF(4.0, 5.0))
            self.assertEqual(base_event.call_count, 1)

            hover_view = self._new_view()
            base_event.reset_mock()
            hover_event = _FakeEvent(QEvent.Type.MouseMove, buttons=Qt.MouseButton.NoButton)
            self.assertFalse(CanvasView.viewportEvent(hover_view, hover_event))
            hover_view._update_hover_highlight.assert_called_once_with(QPointF(4.0, 5.0))
            self.assertEqual(base_event.call_count, 1)

            drag_view = self._new_view()
            base_event.reset_mock()
            drag_event = _FakeEvent(QEvent.Type.MouseMove, buttons=Qt.MouseButton.LeftButton)
            self.assertFalse(CanvasView.viewportEvent(drag_view, drag_event))
            drag_view._clear_hover_highlight.assert_called_once_with()
            self.assertEqual(base_event.call_count, 1)

    def test_event_accepts_shortcut_override_and_native_gesture(self) -> None:
        with mock.patch.object(QGraphicsView, "event", new=mock.Mock(return_value=False)) as base_event:
            shortcut_view = self._new_view()
            base_event.reset_mock()
            shortcut_view.hover_atom_id = 7
            shortcut_event = _FakeEvent(
                QEvent.Type.ShortcutOverride,
                modifiers=Qt.KeyboardModifier.NoModifier,
                key=Qt.Key.Key_Return,
                text="",
            )
            self.assertTrue(CanvasView.event(shortcut_view, shortcut_event))
            shortcut_event.accept.assert_called_once_with()
            shortcut_view._refresh_hover_from_cursor.assert_called_once_with()
            self.assertEqual(base_event.call_count, 0)

            class _FakeNativeGestureEvent(_FakeEvent):
                pass

            native_view = self._new_view()
            base_event.reset_mock()
            native_event = _FakeNativeGestureEvent(
                QEvent.Type.NativeGesture,
                gesture_type=Qt.NativeGestureType.PanNativeGesture,
            )
            with mock.patch("ui.canvas_view.QNativeGestureEvent", _FakeNativeGestureEvent):
                self.assertTrue(CanvasView.event(native_view, native_event))
            native_event.accept.assert_called_once_with()
            native_view._reset_view_transform.assert_called_once_with()
            self.assertEqual(base_event.call_count, 0)

    def test_scroll_contents_by_resets_transform_and_refreshes_hover(self) -> None:
        with mock.patch.object(
            QGraphicsView,
            "scrollContentsBy",
            new=mock.Mock(return_value=None),
        ) as base_scroll:
            view = self._new_view()
            base_scroll.reset_mock()
            CanvasView.scrollContentsBy(view, 12, -4)

            base_scroll.assert_called_once_with(12, -4)
            view._reset_view_transform.assert_called_once_with()
            view._refresh_hover_from_cursor.assert_called_once_with()
