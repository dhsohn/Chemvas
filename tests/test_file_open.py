import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.file_open import FileOpenEventFilter, open_document


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


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for open-document routing tests")
class OpenDocumentRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.example = str(Path(__file__).resolve().parents[1] / "examples" / "template1.chemvas")

    def setUp(self) -> None:
        from ui.main_window_app import reset_window_registry

        reset_window_registry()

    def tearDown(self) -> None:
        from ui.main_window_app import open_windows, reset_window_registry
        from ui.main_window_ports import services_for_window

        for window in list(open_windows()):
            documents = services_for_window(window).canvas_document_service
            for canvas in window.tab_references.all_canvases():
                documents.mark_clean(canvas)
            window.close()
        reset_window_registry()
        self.app.processEvents()

    def test_reuses_blank_startup_window(self) -> None:
        from ui.main_window_app import open_new_window, open_windows

        window = open_new_window()
        self.assertEqual(len(open_windows()), 1)

        open_document(self.example)

        # A blank startup window is reused in place — no extra window.
        self.assertEqual(len(open_windows()), 1)
        self.assertIs(open_windows()[0], window)

    def test_opens_new_window_when_current_holds_a_document(self) -> None:
        from ui.main_window_app import open_new_window, open_windows
        from ui.main_window_ports import services_for_window

        window = open_new_window()
        services_for_window(window).document_action_service.load_canvas_from_path(window, self.example)
        self.assertEqual(len(open_windows()), 1)

        open_document(self.example)

        # The occupied window keeps its document; the file opens in a new window
        # rather than as another tab (single-document-per-window).
        self.assertEqual(len(open_windows()), 2)
        self.assertIs(open_windows()[0], window)


if __name__ == "__main__":
    unittest.main()
