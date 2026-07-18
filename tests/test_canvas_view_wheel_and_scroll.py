import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import QApplication, QGraphicsView
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.canvas_view import CanvasView
    from chemvas.ui.input_view_state import input_view_state_for
    from chemvas.ui.selection_info_state import selection_info_state_for


class _FakeWheelEvent:
    def __init__(
        self,
        pixel_delta: QPoint,
        angle_delta: QPoint,
        modifiers: "Qt.KeyboardModifier | None" = None,
    ) -> None:
        self._pixel_delta = pixel_delta
        self._angle_delta = angle_delta
        self._modifiers = (
            modifiers if modifiers is not None else Qt.KeyboardModifier.NoModifier
        )
        self.accept = mock.Mock()

    def pixelDelta(self) -> QPoint:
        return self._pixel_delta

    def angleDelta(self) -> QPoint:
        return self._angle_delta

    def modifiers(self) -> "Qt.KeyboardModifier":
        return self._modifiers

    def position(self) -> QPointF:
        return QPointF(10.0, 10.0)


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewWheelAndScrollTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _new_view(self):
        view = CanvasView()
        input_view_state_for(view).base_transform = QTransform().translate(3.0, 4.0)
        view.setTransform(QTransform().scale(2.0, 2.0))
        selection_info_state_for(view).last_interaction_time = 0.0
        hbar = SimpleNamespace(value=mock.Mock(return_value=120), setValue=mock.Mock())
        vbar = SimpleNamespace(value=mock.Mock(return_value=240), setValue=mock.Mock())
        view.horizontalScrollBar = lambda: hbar
        view.verticalScrollBar = lambda: vbar
        return view, hbar, vbar

    def test_wheel_event_uses_pixel_delta_and_accepts(self) -> None:
        with mock.patch.object(
            QGraphicsView, "wheelEvent", new=mock.Mock(return_value=None)
        ) as base_wheel:
            view, hbar, vbar = self._new_view()
            event = _FakeWheelEvent(QPoint(15, -7), QPoint(99, 99))

            CanvasView.wheelEvent(view, event)

            self.assertGreater(
                selection_info_state_for(view).last_interaction_time, 0.0
            )
            self.assertTrue(input_view_state_for(view).base_transform.isIdentity())
            self.assertTrue(view.transform().isIdentity())
            hbar.setValue.assert_called_once_with(105)
            vbar.setValue.assert_called_once_with(247)
            event.accept.assert_called_once_with()
            self.assertEqual(base_wheel.call_count, 0)

    def test_wheel_event_falls_back_to_angle_delta_when_pixel_delta_is_null(
        self,
    ) -> None:
        with mock.patch.object(
            QGraphicsView, "wheelEvent", new=mock.Mock(return_value=None)
        ) as base_wheel:
            view, hbar, vbar = self._new_view()
            event = _FakeWheelEvent(QPoint(0, 0), QPoint(8, -6))

            CanvasView.wheelEvent(view, event)

            self.assertGreater(
                selection_info_state_for(view).last_interaction_time, 0.0
            )
            self.assertTrue(input_view_state_for(view).base_transform.isIdentity())
            self.assertTrue(view.transform().isIdentity())
            hbar.setValue.assert_called_once_with(116)
            vbar.setValue.assert_called_once_with(243)
            event.accept.assert_called_once_with()
            self.assertEqual(base_wheel.call_count, 0)

    def test_wheel_event_delegates_to_super_when_deltas_are_zero(self) -> None:
        with mock.patch.object(
            QGraphicsView, "wheelEvent", new=mock.Mock(return_value=None)
        ) as base_wheel:
            view, hbar, vbar = self._new_view()
            event = _FakeWheelEvent(QPoint(0, 0), QPoint(0, 0))

            CanvasView.wheelEvent(view, event)

            self.assertGreater(
                selection_info_state_for(view).last_interaction_time, 0.0
            )
            self.assertTrue(input_view_state_for(view).base_transform.isIdentity())
            self.assertTrue(view.transform().isIdentity())
            hbar.setValue.assert_not_called()
            vbar.setValue.assert_not_called()
            event.accept.assert_not_called()
            base_wheel.assert_called_once_with(event)

    def test_ctrl_wheel_zooms_in_and_out_without_scrolling(self) -> None:
        with mock.patch.object(
            QGraphicsView, "wheelEvent", new=mock.Mock(return_value=None)
        ) as base_wheel:
            view, hbar, vbar = self._new_view()
            input_view_state_for(view).zoom = 1.0

            zoom_in = _FakeWheelEvent(
                QPoint(0, 0),
                QPoint(0, 120),
                modifiers=Qt.KeyboardModifier.ControlModifier,
            )
            CanvasView.wheelEvent(view, zoom_in)
            self.assertGreater(input_view_state_for(view).zoom, 1.0)
            zoom_in.accept.assert_called_once_with()

            zoomed = input_view_state_for(view).zoom
            zoom_out = _FakeWheelEvent(
                QPoint(0, 0),
                QPoint(0, -120),
                modifiers=Qt.KeyboardModifier.ControlModifier,
            )
            CanvasView.wheelEvent(view, zoom_out)
            self.assertLess(input_view_state_for(view).zoom, zoomed)

            hbar.setValue.assert_not_called()
            vbar.setValue.assert_not_called()
            self.assertEqual(base_wheel.call_count, 0)
