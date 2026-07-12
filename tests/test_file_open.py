import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.file_open import FileOpenEventFilter


class _FakeEvent:
    def __init__(self, event_type: "QEvent.Type", path: str = "") -> None:
        self._type = event_type
        self._path = path

    def type(self) -> "QEvent.Type":
        return self._type

    def file(self) -> str:
        return self._path


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for file-open filter tests")
class FileOpenEventFilterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_file_open_event_routes_path_to_handler(self) -> None:
        opened: list[str] = []
        event_filter = FileOpenEventFilter(opened.append)

        handled = event_filter.eventFilter(None, _FakeEvent(QEvent.Type.FileOpen, "/tmp/molecule.chemvas"))

        self.assertTrue(handled)
        self.assertEqual(opened, ["/tmp/molecule.chemvas"])

    def test_empty_path_is_swallowed_without_calling_handler(self) -> None:
        opened: list[str] = []
        event_filter = FileOpenEventFilter(opened.append)

        handled = event_filter.eventFilter(None, _FakeEvent(QEvent.Type.FileOpen, ""))

        self.assertTrue(handled)
        self.assertEqual(opened, [])

    def test_other_events_pass_through(self) -> None:
        opened: list[str] = []
        event_filter = FileOpenEventFilter(opened.append)

        handled = event_filter.eventFilter(None, _FakeEvent(QEvent.Type.Close))

        self.assertFalse(handled)
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
