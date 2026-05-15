import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, QPointF, Qt
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
    ) -> None:
        self._event_type = event_type
        self._button = button
        self._buttons = buttons
        self.accept = mock.Mock()

    def type(self):
        return self._event_type

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewEventFallthroughTest(unittest.TestCase):
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
        view.scene_pos_from_event = mock.Mock(return_value=QPointF(4.0, 5.0))
        view._should_override_chemdraw_shortcut = mock.Mock(return_value=False)
        view.tools = SimpleNamespace(active=tool_active)
        return view

    def test_mouse_press_event_right_click_and_tool_false_fall_through_to_super(self) -> None:
        with mock.patch.object(QGraphicsView, "mousePressEvent", new=mock.Mock(return_value=None)) as base_press:
            template_view = self._new_view()
            template_view._template_insert_active = True

            CanvasView.mousePressEvent(template_view, _FakeEvent(button=Qt.MouseButton.RightButton))

            template_view._commit_template_insert.assert_not_called()
            base_press.assert_called_once()
            template_view._clear_hover_highlight.assert_called_once_with()

            tool = SimpleNamespace(on_mouse_press=mock.Mock(return_value=False))
            tool_view = self._new_view(tool_active=tool)
            base_press.reset_mock()

            CanvasView.mousePressEvent(tool_view, _FakeEvent(button=Qt.MouseButton.LeftButton))

            tool.on_mouse_press.assert_called_once()
            base_press.assert_called_once()
            tool_view._clear_hover_highlight.assert_called_once_with()

    def test_mouse_double_click_event_routes_non_select_tools_and_select_tool_falls_through(self) -> None:
        with mock.patch.object(
            QGraphicsView,
            "mouseDoubleClickEvent",
            new=mock.Mock(return_value=None),
        ) as base_double:
            tool = SimpleNamespace(name="bond", on_mouse_press=mock.Mock(return_value=True))
            tool_view = self._new_view(tool_active=tool)

            CanvasView.mouseDoubleClickEvent(tool_view, _FakeEvent(button=Qt.MouseButton.LeftButton))

            tool.on_mouse_press.assert_called_once()
            base_double.assert_not_called()
            tool_view._clear_hover_highlight.assert_called_once_with()

            select_tool = SimpleNamespace(name="select", on_mouse_press=mock.Mock(return_value=True))
            select_view = self._new_view(tool_active=select_tool)
            base_double.reset_mock()

            CanvasView.mouseDoubleClickEvent(select_view, _FakeEvent(button=Qt.MouseButton.LeftButton))

            select_tool.on_mouse_press.assert_not_called()
            base_double.assert_called_once()
            select_view._clear_hover_highlight.assert_called_once_with()

    def test_mouse_move_event_fallthrough_calls_super_for_hover_and_drag_paths(self) -> None:
        with mock.patch.object(QGraphicsView, "mouseMoveEvent", new=mock.Mock(return_value=None)) as base_move:
            hover_tool = SimpleNamespace(on_mouse_move=mock.Mock(return_value=False))
            hover_view = self._new_view(tool_active=hover_tool)

            CanvasView.mouseMoveEvent(hover_view, _FakeEvent(buttons=Qt.MouseButton.NoButton))

            hover_view._update_hover_highlight.assert_called_once_with(QPointF(4.0, 5.0))
            hover_view._clear_hover_highlight.assert_not_called()
            base_move.assert_called_once()

            drag_tool = SimpleNamespace(on_mouse_move=mock.Mock(return_value=False))
            drag_view = self._new_view(tool_active=drag_tool)
            base_move.reset_mock()

            CanvasView.mouseMoveEvent(drag_view, _FakeEvent(buttons=Qt.MouseButton.LeftButton))

            drag_view._clear_hover_highlight.assert_called_once_with()
            drag_view._update_hover_highlight.assert_not_called()
            base_move.assert_called_once()

    def test_mouse_release_event_tool_false_path_calls_super_and_refresh(self) -> None:
        tool = SimpleNamespace(on_mouse_release=mock.Mock(return_value=False))
        view = self._new_view(tool_active=tool)

        with mock.patch.object(QGraphicsView, "mouseReleaseEvent", new=mock.Mock(return_value=None)) as base_release:
            CanvasView.mouseReleaseEvent(view, _FakeEvent(button=Qt.MouseButton.LeftButton))

        tool.on_mouse_release.assert_called_once()
        base_release.assert_called_once()
        view._refresh_hover_from_cursor.assert_called_once_with()

    def test_viewport_event_generic_passthrough_and_event_false_paths_use_super(self) -> None:
        with mock.patch.object(QGraphicsView, "viewportEvent", new=mock.Mock(return_value=True)) as base_viewport:
            view = self._new_view()
            base_viewport.reset_mock()
            self.assertTrue(CanvasView.viewportEvent(view, _FakeEvent(QEvent.Type.FocusIn)))
            base_viewport.assert_called_once()
            view._clear_hover_highlight.assert_not_called()
            view._update_hover_highlight.assert_not_called()

        with mock.patch.object(QGraphicsView, "event", new=mock.Mock(return_value=False)) as base_event:
            view = self._new_view()
            base_event.reset_mock()
            self.assertFalse(CanvasView.event(view, _FakeEvent(QEvent.Type.ShortcutOverride)))
            base_event.assert_called_once()
            view._should_override_chemdraw_shortcut.assert_called_once()


if __name__ == "__main__":
    unittest.main()
