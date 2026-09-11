import errno
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

    def test_menu_open_and_recent_reuse_the_same_blank_rule(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        from chemvas.bootstrap.window_registry import open_new_window, open_windows
        from chemvas.ui.main_window_ports import (
            active_canvas_for_window,
            services_for_window,
        )

        for route in ("Open...", "Open Recent"):
            with self.subTest(route=route):
                window = open_new_window()
                menu = next(
                    action.menu()
                    for action in window.menuBar().actions()
                    if action.text() == "File"
                )
                if route == "Open...":
                    with mock.patch.object(
                        QFileDialog, "getOpenFileName", return_value=(self.example, "")
                    ):
                        next(
                            action
                            for action in menu.actions()
                            if action.text() == route
                        ).trigger()
                else:
                    from chemvas.ui.recent_documents_store import record_recent

                    record_recent(self.example)
                    recent = next(
                        action.menu()
                        for action in menu.actions()
                        if action.text() == route
                    )
                    recent.aboutToShow.emit()
                    next(
                        action
                        for action in recent.actions()
                        if "template1.chemvas" in action.text()
                    ).trigger()
                self.assertEqual(open_windows(), (window,))
                self.assertEqual(
                    services_for_window(window).canvas_document_service.file_path(
                        active_canvas_for_window(window)
                    ),
                    self.example,
                )
                window.close()
                self.app.processEvents()

    def test_failed_menu_open_keeps_blank_document_and_redo_history(self) -> None:
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        from chemvas.bootstrap.window_registry import open_new_window, open_windows
        from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
        from chemvas.ui.main_window_ports import (
            active_canvas_for_window,
            services_for_window,
        )
        from chemvas.ui.structure_mutation_access import add_bond_between_points_for

        window = open_new_window()
        canvas = active_canvas_for_window(window)
        add_bond_between_points_for(canvas, QPointF(0, 0), QPointF(40, 0))
        history = canvas.services.history_service
        history.undo()
        before = snapshot_canvas_state_for(canvas)
        before_history = history.capture_stack_snapshot()
        self.assertIsNotNone(
            services_for_window(window).canvas_document_service.reusable_open_target(
                window
            )
        )
        menu = next(
            action.menu()
            for action in window.menuBar().actions()
            if action.text() == "File"
        )
        with (
            mock.patch.object(
                QFileDialog, "getOpenFileName", return_value=(self.example, "")
            ),
            mock.patch.object(QMessageBox, "warning"),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items",
                side_effect=RuntimeError("injected load failure"),
            ),
        ):
            next(
                action for action in menu.actions() if action.text() == "Open..."
            ).trigger()

        self.assertEqual(open_windows(), (window,))
        self.assertEqual(snapshot_canvas_state_for(canvas), before)
        self.assertEqual(history.capture_stack_snapshot(), before_history)
        history.redo()
        self.assertTrue(snapshot_canvas_state_for(canvas)["model"]["bonds"])

    def test_missing_svg_open_routes_show_filesystem_reason_without_mutation(
        self,
    ) -> None:
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        from chemvas.bootstrap.window_registry import open_new_window, open_windows
        from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
        from chemvas.ui.main_window_ports import active_canvas_for_window
        from chemvas.ui.recent_documents_store import record_recent
        from chemvas.ui.structure_mutation_access import add_bond_between_points_for

        window = open_new_window()
        canvas = active_canvas_for_window(window)
        add_bond_between_points_for(canvas, QPointF(0, 0), QPointF(40, 0))
        add_bond_between_points_for(canvas, QPointF(80, 0), QPointF(120, 0))
        history = canvas.services.history_service
        history.undo()
        self.assertTrue(history.can_redo())
        before = snapshot_canvas_state_for(canvas)
        stacks = history.capture_stack_snapshot()
        menu = next(
            action.menu()
            for action in window.menuBar().actions()
            if action.text() == "File"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "moved-그림.svg"
            for route in ("Open...", "Open Recent", "startup"):
                with self.subTest(route=route):
                    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
                    if route == "Open Recent":
                        record_recent(str(path))
                        recent = next(
                            action.menu()
                            for action in menu.actions()
                            if action.text() == route
                        )
                        recent.aboutToShow.emit()
                        action = next(
                            action
                            for action in recent.actions()
                            if path.name in action.text()
                        )
                    # A file can disappear after the Recent menu was populated.
                    path.unlink()
                    with mock.patch.object(QMessageBox, "warning") as warning:
                        if route == "Open...":
                            with mock.patch.object(
                                QFileDialog,
                                "getOpenFileName",
                                return_value=(str(path), ""),
                            ):
                                next(
                                    action
                                    for action in menu.actions()
                                    if action.text() == route
                                ).trigger()
                        elif route == "Open Recent":
                            action.trigger()
                        else:
                            # Both the desktop CLI argument and OS-open event
                            # invoke this public application entrypoint.
                            open_document(str(path))
                    warning.assert_called_once_with(
                        window,
                        "Load Error",
                        "Failed to load file:\n"
                        + str(
                            FileNotFoundError(
                                errno.ENOENT, os.strerror(errno.ENOENT), str(path)
                            )
                        ),
                    )
                    self.assertEqual(open_windows(), (window,))
                    self.assertEqual(snapshot_canvas_state_for(canvas), before)
                    self.assertEqual(history.capture_stack_snapshot(), stacks)
                    self.assertFalse(path.exists())

    def test_clean_import_is_not_a_blank_menu_open_target(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        from chemvas.bootstrap.window_registry import open_new_window, open_windows
        from chemvas.core.molfile import write_molfile
        from chemvas.core.svg_roundtrip import (
            CHEMVAS_SVG_SCOPE_SHEET,
            create_editable_svg_payload,
            embed_chemvas_document_in_svg,
        )
        from chemvas.domain.document import CANVAS_FILE_VERSION, deserialize_model_state
        from chemvas.features.document_composition import compose_document_state
        from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
        from chemvas.ui.main_window_ports import (
            active_canvas_for_window,
            services_for_window,
        )

        state = compose_document_state(
            {
                "format": "chemvas-document-composition",
                "version": 1,
                "atoms": [{"id": 0, "element": "N", "x": 0, "y": 0}],
                "bonds": [],
            }
        )
        for suffix in (".mol", ".svg"):
            with (
                self.subTest(suffix=suffix),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory) / ("imported" + suffix)
                if suffix == ".mol":
                    path.write_text(
                        write_molfile(deserialize_model_state(state["model"]))
                    )
                else:
                    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
                    embed_chemvas_document_in_svg(
                        path,
                        create_editable_svg_payload(
                            state,
                            document_version=CANVAS_FILE_VERSION,
                            scope=CHEMVAS_SVG_SCOPE_SHEET,
                        ),
                    )
                window = open_new_window()
                menu = next(
                    action.menu()
                    for action in window.menuBar().actions()
                    if action.text() == "File"
                )
                action = next(
                    action for action in menu.actions() if action.text() == "Open..."
                )
                with mock.patch.object(
                    QFileDialog, "getOpenFileName", return_value=(str(path), "")
                ):
                    action.trigger()
                canvas = active_canvas_for_window(window)
                documents = services_for_window(window).canvas_document_service
                self.assertFalse(documents.is_dirty(canvas))
                self.assertIsNone(documents.file_path(canvas))
                before = snapshot_canvas_state_for(canvas)
                self.assertTrue(before["model"]["atoms"])
                with mock.patch.object(
                    QFileDialog, "getOpenFileName", return_value=("", "")
                ):
                    action.trigger()
                self.assertEqual(open_windows(), (window,))
                with mock.patch.object(
                    QFileDialog, "getOpenFileName", return_value=(self.example, "")
                ):
                    action.trigger()
                self.assertEqual(len(open_windows()), 2)
                self.assertEqual(snapshot_canvas_state_for(canvas), before)
                for opened in open_windows():
                    opened.close()
                self.app.processEvents()

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
