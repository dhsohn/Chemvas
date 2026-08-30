import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt import FileOpenEventFilter
from chemvas.bootstrap.file_open import open_document


class _FakeEvent:
    def __init__(self, event_type: "QEvent.Type", path: str = "") -> None:
        self._type = event_type
        self._path = path

    def type(self) -> "QEvent.Type":
        return self._type

    def file(self) -> str:
        return self._path


class FileOpenEventFilterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_file_open_event_routes_path_to_handler(self) -> None:
        opened: list[str] = []
        event_filter = FileOpenEventFilter(opened.append)

        handled = event_filter.eventFilter(
            None, _FakeEvent(QEvent.Type.FileOpen, "/tmp/molecule.chemvas")
        )

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


class OpenDocumentRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        examples = Path(__file__).resolve().parents[1] / "examples"
        cls.example = str(examples / "template1.chemvas")
        cls.other = str(examples / "template2.chemvas")

    def setUp(self) -> None:
        from chemvas.bootstrap.window_registry import reset_window_registry

        reset_window_registry()

    def tearDown(self) -> None:
        from chemvas.bootstrap.window_registry import (
            open_windows,
            reset_window_registry,
        )
        from chemvas.ui.main_window_ports import services_for_window

        for window in list(open_windows()):
            documents = services_for_window(window).canvas_document_service
            for canvas in window.tab_references.all_canvases():
                documents.mark_clean(canvas)
            window.close()
        reset_window_registry()
        self.app.processEvents()

    def test_reuses_blank_startup_window(self) -> None:
        from chemvas.bootstrap.window_registry import open_new_window, open_windows

        window = open_new_window()
        self.assertEqual(len(open_windows()), 1)

        open_document(self.example)

        # A blank startup window is reused in place — no extra window.
        self.assertEqual(len(open_windows()), 1)
        self.assertIs(open_windows()[0], window)

    def test_opens_new_window_when_current_holds_a_document(self) -> None:
        from chemvas.bootstrap.window_registry import open_new_window, open_windows
        from chemvas.ui.main_window_ports import services_for_window

        window = open_new_window()
        services_for_window(window).document_action_service.load_canvas_from_path(
            window, self.example
        )
        self.assertEqual(len(open_windows()), 1)

        open_document(self.other)

        # The occupied window keeps its document; a *different* file opens in a
        # new window rather than as another tab (single-document-per-window).
        self.assertEqual(len(open_windows()), 2)
        self.assertIs(open_windows()[0], window)

    def test_reopening_the_same_file_switches_instead_of_duplicating(self) -> None:
        from chemvas.bootstrap.window_registry import open_new_window, open_windows
        from chemvas.ui.main_window_ports import services_for_window

        window = open_new_window()
        services_for_window(window).document_action_service.load_canvas_from_path(
            window, self.example
        )
        self.assertEqual(len(open_windows()), 1)

        open_document(self.example)

        # The file is already open, so we switch to its window — no duplicate.
        self.assertEqual(len(open_windows()), 1)
        self.assertIs(open_windows()[0], window)

    def test_reopening_symlink_and_hard_link_aliases_does_not_duplicate(self) -> None:
        from chemvas.bootstrap.window_registry import open_new_window, open_windows
        from chemvas.ui.main_window_ports import services_for_window

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.chemvas"
            source.write_bytes(Path(self.example).read_bytes())
            symlink = Path(temp_dir) / "symlink.chemvas"
            symlink.symlink_to(source)
            hard_link = Path(temp_dir) / "hard-link.chemvas"
            os.link(source, hard_link)

            window = open_new_window()
            services_for_window(window).document_action_service.load_canvas_from_path(
                window, str(source)
            )

            open_document(str(symlink))
            open_document(str(hard_link))

            self.assertEqual(len(open_windows()), 1)
            self.assertIs(open_windows()[0], window)

    def test_save_as_rejects_a_symlink_alias_owned_by_another_window(self) -> None:
        from chemvas.bootstrap.window_registry import open_new_window
        from chemvas.ui.main_window_ports import services_for_window

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.chemvas"
            source.write_bytes(Path(self.example).read_bytes())
            alias = Path(temp_dir) / "alias.chemvas"
            alias.symlink_to(source)
            original_bytes = source.read_bytes()

            owner_window = open_new_window()
            services_for_window(
                owner_window
            ).document_action_service.load_canvas_from_path(owner_window, str(source))
            saving_window = open_new_window()
            message_box = mock.Mock()

            saved = services_for_window(
                saving_window
            ).document_action_service.save_canvas_to_path(
                saving_window,
                str(alias),
                message_box=message_box,
            )

            self.assertFalse(saved)
            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertTrue(alias.is_symlink())
            message_box.warning.assert_called_once()
