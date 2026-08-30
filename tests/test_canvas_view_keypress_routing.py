import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas_view import CanvasView
from tests.canvas_factory import build_canvas_view


class _FakeKeyEvent:
    def __init__(self, key, *, matches=None) -> None:
        self._key = key
        self._matches = set(matches or ())
        self.accept = mock.Mock()

    def key(self):
        return self._key

    def matches(self, standard_key) -> bool:
        return standard_key in self._matches

    def modifiers(self):
        return Qt.KeyboardModifier.NoModifier

    def text(self):
        return ""


class CanvasViewKeyPressRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_key_press_event_delegates_to_input_controller(self) -> None:
        event = _FakeKeyEvent(Qt.Key.Key_A)
        input_controller = mock.Mock()
        view = build_canvas_view()
        view.services.input.input_controller = input_controller

        CanvasView.keyPressEvent(view, event)

        input_controller.key_press_event.assert_called_once_with(event)
