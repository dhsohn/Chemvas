import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_view import CanvasView


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


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewKeyPressRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_key_press_event_delegates_to_input_controller(self) -> None:
        event = _FakeKeyEvent(Qt.Key.Key_A)
        input_controller = mock.Mock()
        view = SimpleNamespace(_input_controller=input_controller)

        CanvasView.keyPressEvent(view, event)

        input_controller.key_press_event.assert_called_once_with(event)


if __name__ == "__main__":
    unittest.main()
