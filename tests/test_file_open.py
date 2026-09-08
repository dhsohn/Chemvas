import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF
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

    def test_filter_can_be_owned_by_the_application(self) -> None:
        event_filter = FileOpenEventFilter(lambda _path: None, parent=self.app)

        self.assertIs(event_filter.parent(), self.app)


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

    def test_new_chemvas_window_keeps_its_ui_callbacks(self) -> None:
        self._assert_new_document_window_keeps_its_ui_callbacks(".chemvas")

    def test_new_editable_svg_window_keeps_its_ui_callbacks(self) -> None:
        self._assert_new_document_window_keeps_its_ui_callbacks(".svg")

    def test_new_mol_window_keeps_its_ui_callbacks(self) -> None:
        self._assert_new_document_window_keeps_its_ui_callbacks(".mol")

    def _assert_new_document_window_keeps_its_ui_callbacks(self, suffix: str) -> None:
        from chemvas.bootstrap.window_registry import open_new_window, open_windows
        from chemvas.core.document_io import write_document
        from chemvas.core.molfile import write_molfile
        from chemvas.core.svg_roundtrip import (
            CHEMVAS_SVG_SCOPE_SHEET,
            create_editable_svg_payload,
            embed_chemvas_document_in_svg,
        )
        from chemvas.domain.document import CANVAS_FILE_VERSION
        from chemvas.ui.canvas_model_access import model_for
        from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
        from chemvas.ui.main_window_ports import (
            active_canvas_for_window,
            services_for_window,
            set_zoom_percent_for_window,
            tool_action_for_window,
            tool_mode_controller_for_window,
        )
        from chemvas.ui.scene_decoration_access import add_arrow_for
        from chemvas.ui.structure_mutation_access import add_bond_between_points_for

        reference = open_new_window()
        reference_services = services_for_window(reference)
        reference_canvas = active_canvas_for_window(reference)
        add_bond_between_points_for(reference_canvas, QPointF(-20, 0), QPointF(20, 0))
        with tempfile.TemporaryDirectory() as temp_dir:
            reference_path = Path(temp_dir) / "reference.chemvas"
            self.assertTrue(
                reference_services.document_action_service.save_canvas_to_path(
                    reference, str(reference_path)
                )
            )
            state = snapshot_canvas_state_for(reference_canvas)
            path = Path(temp_dir) / f"opened{suffix}"
            if suffix == ".mol":
                path.write_text(
                    write_molfile(model_for(reference_canvas)), encoding="utf-8"
                )
            elif suffix == ".svg":
                path.write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8"
                )
                embed_chemvas_document_in_svg(
                    path,
                    create_editable_svg_payload(
                        state,
                        document_version=CANVAS_FILE_VERSION,
                        scope=CHEMVAS_SVG_SCOPE_SHEET,
                    ),
                )
            else:
                write_document(path, state, version=CANVAS_FILE_VERSION)
            tool_mode_controller_for_window(reference).set_tool("line")
            self.app.processEvents()
            reference_status = reference_services.status_service.status_context_texts()
            reference_page = (
                reference_services.context_bar_service._stack.currentWidget()
            )
            reference_document = snapshot_canvas_state_for(reference_canvas)

            open_document(str(path))
            self.app.processEvents()

            self.assertEqual(len(open_windows()), 2)
            target = open_windows()[-1]
            target_services = services_for_window(target)
            target_canvas = active_canvas_for_window(target)
            self.assertEqual(len(model_for(target_canvas).atoms), 2)
            tool_mode_controller_for_window(target).set_tool("arrow")
            arrow = add_arrow_for(
                target_canvas, QPointF(0, 70), QPointF(100, 70), "arrow"
            )
            arrow.setSelected(True)
            set_zoom_percent_for_window(target, 150)
            self.app.processEvents()

            target_status = target_services.status_service.status_context_texts()
            self.assertEqual(target_status["tool"], "Tool: Arrow")
            self.assertEqual(target_status["selection"], "Selection: 1")
            self.assertEqual(target_status["zoom"], "150%")
            self.assertTrue(tool_action_for_window(target, "arrow").isChecked())
            self.assertIs(
                target_services.context_bar_service._stack.currentWidget(),
                target_services.context_bar_service._pages["arrow"],
            )
            self.assertTrue(
                target_services.canvas_document_service.is_dirty(target_canvas)
            )
            self.assertTrue(target.isWindowModified())
            self.assertEqual(
                reference_services.status_service.status_context_texts(),
                reference_status,
            )
            self.assertIs(
                reference_services.context_bar_service._stack.currentWidget(),
                reference_page,
            )
            self.assertEqual(
                snapshot_canvas_state_for(reference_canvas), reference_document
            )
            self.assertFalse(reference.isWindowModified())

            # Returning to the original window must not update the new one.
            tool_mode_controller_for_window(reference).set_tool("bond")
            self.assertEqual(
                reference_services.status_service.status_context_texts()["tool"],
                "Tool: Bond",
            )
            self.assertEqual(
                target_services.status_service.status_context_texts(), target_status
            )

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
