import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication, QGraphicsView
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_view import CanvasView


class _FakeWheelEvent:
    def __init__(self, pixel_delta: QPoint, angle_delta: QPoint) -> None:
        self._pixel_delta = pixel_delta
        self._angle_delta = angle_delta
        self.accept = mock.Mock()

    def pixelDelta(self) -> QPoint:
        return self._pixel_delta

    def angleDelta(self) -> QPoint:
        return self._angle_delta


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewWheelAndScrollTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _new_view(self):
        view = CanvasView()
        view._touch_interaction = mock.Mock()
        view._reset_view_transform = mock.Mock()
        hbar = SimpleNamespace(value=mock.Mock(return_value=120), setValue=mock.Mock())
        vbar = SimpleNamespace(value=mock.Mock(return_value=240), setValue=mock.Mock())
        view.horizontalScrollBar = lambda: hbar
        view.verticalScrollBar = lambda: vbar
        return view, hbar, vbar

    def test_wheel_event_uses_pixel_delta_and_accepts(self) -> None:
        with mock.patch.object(QGraphicsView, "wheelEvent", new=mock.Mock(return_value=None)) as base_wheel:
            view, hbar, vbar = self._new_view()
            event = _FakeWheelEvent(QPoint(15, -7), QPoint(99, 99))

            CanvasView.wheelEvent(view, event)

            view._touch_interaction.assert_called_once_with()
            view._reset_view_transform.assert_called_once_with()
            hbar.setValue.assert_called_once_with(105)
            vbar.setValue.assert_called_once_with(247)
            event.accept.assert_called_once_with()
            self.assertEqual(base_wheel.call_count, 0)

    def test_wheel_event_falls_back_to_angle_delta_when_pixel_delta_is_null(self) -> None:
        with mock.patch.object(QGraphicsView, "wheelEvent", new=mock.Mock(return_value=None)) as base_wheel:
            view, hbar, vbar = self._new_view()
            event = _FakeWheelEvent(QPoint(0, 0), QPoint(8, -6))

            CanvasView.wheelEvent(view, event)

            view._touch_interaction.assert_called_once_with()
            view._reset_view_transform.assert_called_once_with()
            hbar.setValue.assert_called_once_with(116)
            vbar.setValue.assert_called_once_with(243)
            event.accept.assert_called_once_with()
            self.assertEqual(base_wheel.call_count, 0)

    def test_wheel_event_delegates_to_super_when_deltas_are_zero(self) -> None:
        with mock.patch.object(QGraphicsView, "wheelEvent", new=mock.Mock(return_value=None)) as base_wheel:
            view, hbar, vbar = self._new_view()
            event = _FakeWheelEvent(QPoint(0, 0), QPoint(0, 0))

            CanvasView.wheelEvent(view, event)

            view._touch_interaction.assert_called_once_with()
            view._reset_view_transform.assert_called_once_with()
            hbar.setValue.assert_not_called()
            vbar.setValue.assert_not_called()
            event.accept.assert_not_called()
            base_wheel.assert_called_once_with(event)
