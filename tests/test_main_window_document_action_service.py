import contextlib
import math
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from chemvas.bootstrap.main_window import build_main_window
from chemvas.bootstrap.window_registry import (
    forget_window,
    open_windows,
    register_window,
)
from chemvas.core.document_io import write_document
from chemvas.core.molfile import parse_molfile, write_molfile
from chemvas.domain.document import CANVAS_FILE_VERSION, MoleculeModel
from chemvas.features.export.errors import MinimumFontSizeError
from chemvas.ui.canvas_document_metadata_state import document_file_path_for
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import model_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_document_dialogs import FigureExportOptions
from chemvas.ui.main_window_path_logic import (
    resolve_save_as_path,
    resolve_save_path,
)
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    history_service_for_window,
    services_for_window,
)
from chemvas.ui.mark_item_access import mark_kinds_by_atom_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_decoration_access import (
    add_arrow_for,
    materialize_mark_for_atom_for,
)
from chemvas.ui.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.structure_payload_access import build_3d_conversion_payload_for


class MainWindowDocumentActionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.window.show()
        self.app.processEvents()
        QTest.qWait(20)
        self.service = services_for_window(self.window).document_action_service

    def tearDown(self) -> None:
        for canvas in self.window.tab_references.all_canvases():
            services_for_window(self.window).canvas_document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_close_shortcut_preserves_dirty_document_when_cancelled(self) -> None:
        add_bond_between_points_for(
            active_canvas_for_window(self.window),
            QPointF(-20.0, 0.0),
            QPointF(20.0, 0.0),
        )
        file_menu = next(
            action.menu()
            for action in self.window.menuBar().actions()
            if action.text() == "File"
        )
        action = next(a for a in file_menu.actions() if a.text() == "Close Window")
        self.assertEqual(
            action.shortcuts(), QKeySequence.keyBindings(QKeySequence.StandardKey.Close)
        )
        with mock.patch(
            "chemvas.ui.main_window_document_action_service.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Cancel,
        ) as question:
            QTest.keySequence(self.window, action.shortcut())
            self.app.processEvents()
        question.assert_called_once()
        self.assertTrue(self.window.isVisible())
        self.assertTrue(
            services_for_window(self.window).canvas_document_service.is_dirty(
                active_canvas_for_window(self.window)
            )
        )

    def test_save_canvas_to_path_updates_only_active_canvas_path_title_and_clean_state(
        self,
    ) -> None:
        add_bond_between_points_for(
            active_canvas_for_window(self.window),
            QPointF(-20.0, 0.0),
            QPointF(20.0, 0.0),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "new.chemvas"
            result = self.service.save_canvas_to_path(self.window, str(path))

            self.assertTrue(result)
            self.assertTrue(path.exists())
            canvas = active_canvas_for_window(self.window)
            self.assertEqual(document_file_path_for(canvas), str(path))
            self.assertEqual(
                self.window.tab_references.canvas_tabs.tabText(0), "new.chemvas"
            )
            self.assertFalse(
                services_for_window(self.window).canvas_document_service.is_dirty(
                    canvas
                )
            )

    def test_save_as_keeps_sheet_status_current_without_tool_switch(self) -> None:
        canvas = active_canvas_for_window(self.window)
        status = services_for_window(self.window).status_service
        add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))
        other_status = {
            key: value
            for key, value in status.status_context_texts().items()
            if key != "sheet"
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in ("first.chemvas", "renamed.chemvas"):
                with self.subTest(name=name):
                    path = str(Path(temp_dir) / name)
                    file_dialog = mock.Mock()
                    file_dialog.getSaveFileName.return_value = (path, "")

                    self.assertTrue(
                        self.service.save_canvas_as(
                            self.window, file_dialog=file_dialog
                        )
                    )

                    self.assertEqual(
                        status.status_context_texts()["sheet"], f"Canvas: {name}"
                    )
                    self.assertEqual(
                        self.window.statusBar().currentMessage(), f"Saved: {path}"
                    )
                    self.assertEqual(
                        {
                            key: value
                            for key, value in status.status_context_texts().items()
                            if key != "sheet"
                        },
                        other_status,
                    )

    def test_sheet_status_follows_edit_undo_redo_and_save(self) -> None:
        canvas = active_canvas_for_window(self.window)
        status = services_for_window(self.window).status_service
        history = history_service_for_window(self.window)
        self.window.statusBar().showMessage("Keep this feedback")

        add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))
        self.assertEqual(status.status_context_texts()["sheet"], "Canvas: ● Canvas 1")
        history.undo()
        self.assertEqual(status.status_context_texts()["sheet"], "Canvas: Canvas 1")
        history.redo()
        self.assertEqual(status.status_context_texts()["sheet"], "Canvas: ● Canvas 1")
        self.assertEqual(self.window.statusBar().currentMessage(), "Keep this feedback")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "saved.chemvas")
            self.assertTrue(self.service.save_canvas_to_path(self.window, path))
            self.assertEqual(
                status.status_context_texts()["sheet"], "Canvas: saved.chemvas"
            )

    def test_failed_save_preserves_sheet_status_and_document_state(self) -> None:
        canvas = active_canvas_for_window(self.window)
        status = services_for_window(self.window).status_service
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = Path(temp_dir) / "original.chemvas"
            failed_path = Path(temp_dir) / "failed.chemvas"
            self.assertTrue(
                self.service.save_canvas_to_path(self.window, str(original_path))
            )
            original_bytes = original_path.read_bytes()
            add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))
            before_document = snapshot_canvas_state_for(canvas)
            before_status = status.status_context_texts()
            message_box = mock.Mock()

            with mock.patch(
                "chemvas.ui.main_window_document_action_service.save_canvas_to_file_for",
                side_effect=OSError("write failed"),
            ):
                result = self.service.save_canvas_to_path(
                    self.window, str(failed_path), message_box=message_box
                )

            self.assertFalse(result)
            self.assertFalse(failed_path.exists())
            self.assertEqual(original_path.read_bytes(), original_bytes)
            self.assertEqual(document_file_path_for(canvas), str(original_path))
            self.assertEqual(snapshot_canvas_state_for(canvas), before_document)
            self.assertEqual(status.status_context_texts(), before_status)
            self.assertTrue(
                services_for_window(self.window).canvas_document_service.is_dirty(
                    canvas
                )
            )
            message_box.warning.assert_called_once()

    def test_save_confirms_external_replacement_and_cancel_keeps_both_versions(self):
        canvas = active_canvas_for_window(self.window)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shared.chemvas"
            self.assertTrue(self.service.save_canvas_to_path(self.window, str(path)))
            add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))
            external_bytes = path.read_bytes() + b"\n"
            path.write_bytes(external_bytes)
            before = snapshot_canvas_state_for(canvas)
            message_box = mock.Mock()
            message_box.question.return_value = QMessageBox.StandardButton.No

            self.assertFalse(
                self.service.save_canvas_to_path(
                    self.window, str(path), message_box=message_box
                )
            )
            message_box.question.assert_called_once()
            self.assertEqual(path.read_bytes(), external_bytes)
            self.assertEqual(snapshot_canvas_state_for(canvas), before)
            message_box.question.return_value = QMessageBox.StandardButton.Yes
            self.assertTrue(
                self.service.save_canvas_to_path(
                    self.window, str(path), message_box=message_box
                )
            )
            message_box.question.reset_mock()
            self.assertTrue(
                self.service.save_canvas_to_path(
                    self.window, str(path), message_box=message_box
                )
            )
            message_box.question.assert_not_called()

    def test_save_does_not_adopt_another_writers_post_save_bytes(self) -> None:
        from chemvas.ui.canvas_window_access import save_canvas_to_file_for

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shared.chemvas"

            def write_then_external_change(canvas, write_path):
                warnings = save_canvas_to_file_for(canvas, write_path)
                path.write_bytes(path.read_bytes() + b"\n")
                return warnings

            with mock.patch(
                "chemvas.ui.main_window_document_action_service.save_canvas_to_file_for",
                side_effect=write_then_external_change,
            ):
                self.assertTrue(
                    self.service.save_canvas_to_path(self.window, str(path))
                )
            external_bytes = path.read_bytes()
            message_box = mock.Mock()
            message_box.question.return_value = QMessageBox.StandardButton.No
            self.assertFalse(
                self.service.save_canvas_to_path(
                    self.window,
                    str(path),
                    message_box=message_box,
                )
            )
            message_box.question.assert_called_once()
            self.assertEqual(path.read_bytes(), external_bytes)

    def test_open_records_source_bytes_and_recovery_requires_confirmation(self):
        canvas = active_canvas_for_window(self.window)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shared.chemvas"
            write_document(path, snapshot_canvas_state_for(canvas), CANVAS_FILE_VERSION)
            self.assertTrue(self.service.load_canvas_from_path(self.window, str(path)))
            message_box = mock.Mock()
            message_box.question.return_value = QMessageBox.StandardButton.No
            self.assertTrue(
                self.service.save_canvas_to_path(
                    self.window, str(path), message_box=message_box
                )
            )
            message_box.question.assert_not_called()
            # Recovery opens a state, not the original file bytes. Its baseline
            # is unknown, so Save must never silently replace the bound path.
            documents = services_for_window(self.window).canvas_document_service
            documents.replace_canvas_with_state(
                self.window,
                canvas,
                state=snapshot_canvas_state_for(canvas),
                file_path=str(path),
            )
            documents.mark_dirty(canvas)
            self.assertFalse(
                self.service.save_canvas_to_path(
                    self.window, str(path), message_box=message_box
                )
            )
            message_box.question.assert_called_once()

    def test_save_checks_stale_or_inconsistent_plan_before_writing(self) -> None:
        from chemvas.ui.canvas_calculation_plan_state import (
            calculation_plan_for,
            set_calculation_plan_for,
        )
        from tests.test_calculation_plan import _document_state, _plan

        canvas = active_canvas_for_window(self.window)
        documents = services_for_window(self.window).canvas_document_service
        for stale in (False, True):
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as temp_dir:
                state = _document_state()
                documents.replace_canvas_with_state(
                    self.window,
                    canvas,
                    state=state,
                    file_path=None,
                    display_name="draft",
                )
                plan = _plan()
                if stale:
                    plan["states"][0]["members"][0]["component_atom_ids"] = [999]
                else:
                    plan["states"][0]["charge"] = 1
                set_calculation_plan_for(canvas, plan)
                documents.mark_dirty(canvas)
                message_box = mock.Mock()
                message_box.question.return_value = QMessageBox.StandardButton.No
                path = Path(temp_dir) / "draft.chemvas"

                self.assertFalse(
                    self.service.save_canvas_to_path(
                        self.window,
                        str(path),
                        message_box=message_box,
                    )
                )
                self.assertFalse(path.exists())
                self.assertEqual(calculation_plan_for(canvas), plan)
                self.assertTrue(documents.is_dirty(canvas))
                message_box.question.assert_called_once()
                self.assertIn(
                    "calculation plan", message_box.question.call_args.args[2]
                )

                message_box.question.return_value = QMessageBox.StandardButton.Yes
                self.assertTrue(
                    self.service.save_canvas_to_path(
                        self.window,
                        str(path),
                        message_box=message_box,
                    )
                )
                from chemvas.core.document_io import read_document

                saved = read_document(path).state
                if stale:
                    self.assertNotIn("calculation_plan", saved)
                else:
                    self.assertEqual(saved["calculation_plan"], plan)

    def test_save_canvas_to_path_rejects_a_path_owned_by_another_canvas(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        other_canvas = object()
        other_window = object()
        message_box = mock.Mock()

        with (
            mock.patch(
                "chemvas.ui.main_window_document_action_service.find_open_document",
                return_value=(other_window, other_canvas),
            ) as find_open_document,
            mock.patch(
                "chemvas.ui.main_window_document_action_service.save_canvas_to_file_for"
            ) as save_canvas_to_file_for,
        ):
            result = self.service.save_canvas_to_path(
                self.window,
                "/tmp/owned.chemvas",
                canvas=canvas,
                message_box=message_box,
            )

        self.assertFalse(result)
        find_open_document.assert_called_once_with(
            "/tmp/owned.chemvas", exclude_canvas=canvas
        )
        save_canvas_to_file_for.assert_not_called()
        message_box.warning.assert_called_once_with(
            self.window,
            "Save Error",
            "This file is already open in another Chemvas window.\n"
            "Close that document before saving here.",
        )

    def test_save_canvas_to_path_updates_a_symlink_target_without_replacing_link(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target.chemvas"
            alias = Path(temp_dir) / "alias.chemvas"
            target.write_text("old", encoding="utf-8")
            alias.symlink_to(target)

            result = self.service.save_canvas_to_path(self.window, str(alias))

            self.assertTrue(result)
            self.assertTrue(alias.is_symlink())
            self.assertNotEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(
                document_file_path_for(active_canvas_for_window(self.window)),
                str(alias),
            )

    def test_save_canvas_to_path_refuses_to_split_a_hard_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target.chemvas"
            alias = Path(temp_dir) / "alias.chemvas"
            target.write_text("old", encoding="utf-8")
            os.link(target, alias)
            message_box = mock.Mock()

            result = self.service.save_canvas_to_path(
                self.window, str(alias), message_box=message_box
            )

            self.assertFalse(result)
            self.assertTrue(os.path.samefile(target, alias))
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            message_box.warning.assert_called_once_with(
                self.window,
                "Save Error",
                "This file has multiple hard-link names.\n"
                "Use Save As with a new path to preserve atomic saves.",
            )

    def test_load_canvas_from_path_switches_to_an_already_open_document(self) -> None:
        register_window(self.window)
        self.addCleanup(lambda: forget_window(self.window))
        add_bond_between_points_for(
            active_canvas_for_window(self.window),
            QPointF(-20.0, 0.0),
            QPointF(20.0, 0.0),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "dup.chemvas")
            self.assertTrue(self.service.save_canvas_to_path(self.window, path))
            windows_before = set(open_windows())
            spawned: list = []
            message_box = mock.Mock()

            with mock.patch(
                "chemvas.ui.main_window_document_action_service.record_recent"
            ) as recent:
                result = self.service.load_canvas_from_path(
                    self.window,
                    path,
                    message_box=message_box,
                    target_provider=lambda: spawned.append(object()),
                )
            recent.assert_called_once_with(path)

            self.assertTrue(result)
            self.assertEqual(spawned, [])  # no duplicate window opened
            self.assertEqual(set(open_windows()), windows_before)
            self.assertEqual(self.window.tab_references.canvas_count(), 1)
            message_box.warning.assert_not_called()
            self.assertIn("Already open", self.window.statusBar().currentMessage())

    def test_load_canvas_from_path_stores_an_absolute_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            abs_path = str(Path(temp_dir) / "rel.chemvas")
            write_document(
                abs_path,
                snapshot_canvas_state_for(active_canvas_for_window(self.window)),
                CANVAS_FILE_VERSION,
            )
            cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                ok = self.service.load_canvas_from_path(
                    self.window, "rel.chemvas", target_provider=lambda: self.window
                )
            finally:
                os.chdir(cwd)

        self.assertTrue(ok)
        stored = document_file_path_for(active_canvas_for_window(self.window))
        # A relative CLI path must be resolved so the session/recent entries
        # survive a restore from a different working directory.
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertTrue(os.path.isabs(stored))
        self.assertTrue(stored.endswith("rel.chemvas"))

    def test_load_canvas_from_path_refreshes_the_autosave_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "open.chemvas")
            write_document(
                path,
                snapshot_canvas_state_for(active_canvas_for_window(self.window)),
                CANVAS_FILE_VERSION,
            )
            calls: list[int] = []
            with mock.patch(
                "chemvas.ui.main_window_document_action_service.request_snapshot",
                lambda: calls.append(1),
            ):
                ok = self.service.load_canvas_from_path(
                    self.window, path, target_provider=lambda: self.window
                )
        # Opening a file must nudge the session so it survives a quit before the
        # next timer tick, symmetric with Save.
        self.assertTrue(ok)
        self.assertEqual(calls, [1])

    def test_close_canvas_tab_refreshes_the_autosave_snapshot(self) -> None:
        services_for_window(self.window).canvas_document_service.new_canvas(self.window)
        calls: list[int] = []
        with mock.patch(
            "chemvas.ui.main_window_document_action_service.request_snapshot",
            lambda: calls.append(1),
        ):
            closed = self.service.close_canvas_tab(self.window, 0)
        # Closing a document must drop it from the session so a clean quit does
        # not reopen it.
        self.assertTrue(closed)
        self.assertEqual(calls, [1])

    def test_save_canvas_to_path_refreshes_the_autosave_snapshot(self) -> None:
        calls: list[int] = []
        with mock.patch(
            "chemvas.ui.main_window_document_action_service.request_snapshot",
            lambda: calls.append(1),
        ):
            with tempfile.TemporaryDirectory() as temp_dir:
                path = str(Path(temp_dir) / "snap.chemvas")
                self.assertTrue(self.service.save_canvas_to_path(self.window, path))
        # A save must nudge the session manifest so a path change is captured
        # before any clean-exit flag is written.
        self.assertEqual(calls, [1])

    def test_save_canvas_to_path_rejects_noncanonical_document_suffix(self) -> None:
        message_box = mock.Mock()

        with mock.patch(
            "chemvas.ui.main_window_document_action_service.save_canvas_to_file_for"
        ) as save_canvas_to_file_for:
            result = self.service.save_canvas_to_path(
                self.window,
                "/tmp/legacy.json",
                message_box=message_box,
            )

        self.assertFalse(result)
        save_canvas_to_file_for.assert_not_called()
        message_box.warning.assert_called_once_with(
            self.window,
            "Save Error",
            "Chemvas documents must use the .chemvas filename extension.",
        )

    def test_save_canvas_to_path_reports_document_adjustments(self) -> None:
        message_box = mock.Mock()

        with mock.patch(
            "chemvas.ui.main_window_document_action_service.save_canvas_to_file_for",
            return_value=["1 invalid bond was omitted."],
        ):
            result = self.service.save_canvas_to_path(
                self.window,
                "/tmp/adjusted.chemvas",
                message_box=message_box,
            )

        self.assertTrue(result)
        message_box.warning.assert_called_once()
        self.assertIn(
            "1 invalid bond was omitted.", message_box.warning.call_args.args[2]
        )

    def test_save_canvas_prefers_current_path_and_falls_back_to_save_as(self) -> None:
        canvas = active_canvas_for_window(self.window)
        services_for_window(self.window).canvas_document_service.set_file_path(
            canvas, "/tmp/existing.chemvas"
        )

        with (
            mock.patch.object(
                self.service, "save_canvas_to_path", return_value=True
            ) as save_canvas_to_path,
            mock.patch.object(
                self.service, "save_canvas_as", return_value=True
            ) as save_canvas_as,
        ):
            self.assertTrue(
                self.service.save_canvas(
                    self.window, resolve_save_path=resolve_save_path
                )
            )

        save_canvas_to_path.assert_called_once_with(
            self.window, "/tmp/existing.chemvas", canvas=None
        )
        save_canvas_as.assert_not_called()

        services_for_window(self.window).canvas_document_service.set_file_path(
            canvas, None
        )
        with (
            mock.patch.object(
                self.service, "save_canvas_to_path", return_value=True
            ) as save_canvas_to_path,
            mock.patch.object(
                self.service, "save_canvas_as", return_value=False
            ) as save_canvas_as,
        ):
            self.assertFalse(
                self.service.save_canvas(
                    self.window, resolve_save_path=resolve_save_path
                )
            )

        save_canvas_as.assert_called_once_with(self.window, canvas=None)
        save_canvas_to_path.assert_not_called()

    def test_save_canvas_as_uses_default_dialog_path_and_normalizes_extension(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        services_for_window(self.window).canvas_document_service.set_file_path(
            canvas, "/tmp/current.chemvas"
        )
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("/tmp/new-drawing", "")

        with mock.patch.object(
            self.service, "save_canvas_to_path", return_value=True
        ) as save_canvas_to_path:
            self.assertTrue(
                self.service.save_canvas_as(
                    self.window,
                    file_dialog=file_dialog,
                    resolve_save_as_path=resolve_save_as_path,
                )
            )

        file_dialog.getSaveFileName.assert_called_once()
        self.assertEqual(
            file_dialog.getSaveFileName.call_args.args[2], "/tmp/current.chemvas"
        )
        self.assertEqual(
            file_dialog.getSaveFileName.call_args.args[3],
            "Chemvas (*.chemvas);;All Files (*)",
        )
        save_canvas_to_path.assert_called_once_with(
            self.window, "/tmp/new-drawing.chemvas", canvas=None
        )

    def test_save_canvas_as_confirms_overwrite_when_normalization_retargets(
        self,
    ) -> None:
        # The dialog's own overwrite prompt covers the typed name only; when
        # suffix normalization redirects the write to an existing .chemvas
        # file, that file was never confirmed and must not be replaced
        # silently.
        with tempfile.TemporaryDirectory() as temp_dir:
            existing = Path(temp_dir) / "aspirin.chemvas"
            existing.write_text("sentinel")
            for typed in ("aspirin", "aspirin.v2"):
                with self.subTest(typed=typed):
                    file_dialog = mock.Mock()
                    file_dialog.getSaveFileName.return_value = (
                        str(Path(temp_dir) / typed),
                        "",
                    )
                    message_box = mock.Mock()
                    message_box.question.return_value = QMessageBox.StandardButton.No

                    with mock.patch.object(
                        self.service, "save_canvas_to_path", return_value=True
                    ) as save_canvas_to_path:
                        self.assertFalse(
                            self.service.save_canvas_as(
                                self.window,
                                file_dialog=file_dialog,
                                resolve_save_as_path=resolve_save_as_path,
                                message_box=message_box,
                            )
                        )
                    save_canvas_to_path.assert_not_called()
                    message_box.question.assert_called_once()

                    message_box.question.return_value = QMessageBox.StandardButton.Yes
                    with mock.patch.object(
                        self.service, "save_canvas_to_path", return_value=True
                    ) as save_canvas_to_path:
                        self.assertTrue(
                            self.service.save_canvas_as(
                                self.window,
                                file_dialog=file_dialog,
                                resolve_save_as_path=resolve_save_as_path,
                                message_box=message_box,
                            )
                        )
                    save_canvas_to_path.assert_called_once_with(
                        self.window, str(existing), canvas=None
                    )

    def test_save_canvas_as_does_not_reprompt_a_dialog_confirmed_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            existing = Path(temp_dir) / "confirmed.chemvas"
            existing.write_text("sentinel")
            file_dialog = mock.Mock()
            file_dialog.getSaveFileName.return_value = (str(existing), "")
            message_box = mock.Mock()

            with mock.patch.object(
                self.service, "save_canvas_to_path", return_value=True
            ) as save_canvas_to_path:
                self.assertTrue(
                    self.service.save_canvas_as(
                        self.window,
                        file_dialog=file_dialog,
                        resolve_save_as_path=resolve_save_as_path,
                        message_box=message_box,
                    )
                )
            save_canvas_to_path.assert_called_once_with(
                self.window, str(existing), canvas=None
            )
            message_box.question.assert_not_called()

    def test_selected_mol_export_requires_structure_before_asking_for_a_path(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))
        arrow = add_arrow_for(canvas, QPointF(0, 50), QPointF(80, 50), "forward")
        canvas.scene().clearSelection()
        before = snapshot_canvas_state_for(canvas)
        self.window.statusBar().showMessage("Keep this feedback")

        for annotation_selected in (False, True):
            with self.subTest(annotation_selected=annotation_selected):
                arrow.setSelected(annotation_selected)
                file_dialog = mock.Mock()
                file_dialog.getSaveFileName.return_value = ("", "")
                message_box = mock.Mock()
                status_sink = mock.Mock()
                with mock.patch.object(
                    self.service, "_document_session_service_for_window"
                ) as session_service:
                    self.service.export_mol(
                        self.window,
                        selected_only=True,
                        file_dialog=file_dialog,
                        message_box=message_box,
                        dialog_parent=canvas,
                        status_sink=status_sink,
                    )

                file_dialog.getSaveFileName.assert_not_called()
                session_service.assert_not_called()
                message = "Select a molecular structure on the canvas first."
                message_box.warning.assert_called_once_with(
                    canvas, "Export Error", message
                )
                status_sink.assert_called_once_with(f"Export failed: {message}")
                self.assertEqual(snapshot_canvas_state_for(canvas), before)
                self.assertEqual(
                    self.window.statusBar().currentMessage(), "Keep this feedback"
                )

    def test_mol_export_preserves_atom_bond_and_atom_mark_selection(self) -> None:
        canvas = active_canvas_for_window(self.window)
        add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))
        atom_id = min(model_for(canvas).atoms)
        mark = materialize_mark_for_atom_for(
            canvas, atom_id, QPointF(-20, -10), kind="plus"
        )
        self.assertIsNotNone(mark)
        before = snapshot_canvas_state_for(canvas)

        with tempfile.TemporaryDirectory() as temp_dir:
            for kind, expected_atoms, expected_bonds in (
                ("atom", 1, 0),
                ("bond", 2, 1),
                ("mark", 1, 0),
                ("all", 2, 1),
            ):
                with self.subTest(selection=kind):
                    canvas.scene().clearSelection()
                    if kind != "all":
                        item = next(
                            item
                            for item in canvas.scene().items()
                            if item.data(0) == kind
                            and (kind != "atom" or item.data(1) == atom_id)
                        )
                        item.setSelected(True)
                    path = Path(temp_dir) / f"{kind}.mol"
                    file_dialog = mock.Mock()
                    file_dialog.getSaveFileName.return_value = (str(path), "")
                    message_box = mock.Mock()

                    self.service.export_mol(
                        self.window,
                        selected_only=kind != "all",
                        file_dialog=file_dialog,
                        message_box=message_box,
                    )

                    file_dialog.getSaveFileName.assert_called_once()
                    message_box.warning.assert_not_called()
                    exported = parse_molfile(path.read_text(encoding="utf-8"))
                    self.assertEqual(len(exported.atoms), expected_atoms)
                    self.assertEqual(len(exported.bonds), expected_bonds)
                    self.assertEqual(
                        list(exported.atom_annotations.values()), [{"formal_charge": 1}]
                    )
                    self.assertEqual(snapshot_canvas_state_for(canvas), before)

    def test_export_paths_do_not_reprompt_a_dialog_confirmed_target(self) -> None:
        # The normalizers round-trip through Path(), so the returned string can
        # differ from the typed one (collapsed slashes here, backslashes on
        # Windows) while naming the same file the dialog already confirmed —
        # the guard must compare path identity, not strings.
        with tempfile.TemporaryDirectory() as temp_dir:
            existing = Path(temp_dir) / "target.xyz"
            existing.write_text("sentinel")
            file_dialog = mock.Mock()
            file_dialog.getSaveFileName.return_value = (
                f"{temp_dir}//./target.xyz",
                "",
            )
            message_box = mock.Mock()
            session_service = mock.Mock()

            with mock.patch.object(
                self.service,
                "_document_session_service_for_window",
                return_value=session_service,
            ):
                self.service.export_xyz(
                    self.window,
                    file_dialog=file_dialog,
                    message_box=message_box,
                )
            message_box.question.assert_not_called()
            session_service.export_xyz_async.assert_called_once()

    def test_export_figure_confirms_replacing_the_file_the_format_retargets_to(
        self,
    ) -> None:
        # Typing another format's extension retargets the write, so the file
        # that gets replaced is not the name the save dialog confirmed.
        with tempfile.TemporaryDirectory() as temp_dir:
            existing = Path(temp_dir) / "target.svg"
            existing.write_text("sentinel")
            file_dialog = mock.Mock()
            file_dialog.getSaveFileName.return_value = (
                str(Path(temp_dir) / "target.pdf"),
                "",
            )
            message_box = mock.Mock()
            message_box.question.return_value = QMessageBox.StandardButton.No
            session_service = mock.Mock()

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        self.service,
                        "_document_session_service_for_window",
                        return_value=session_service,
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "chemvas.ui.main_window_document_action_service."
                        "prompt_export_options",
                        return_value=SimpleNamespace(
                            fmt="svg",
                            scope="sheet",
                            dpi=300,
                            background="transparent",
                            sizing="bond",
                            editable_svg=False,
                        ),
                    )
                )
                self.service.export_figure(
                    self.window,
                    file_dialog=file_dialog,
                    message_box=message_box,
                )
            session_service.export_figure.assert_not_called()
            message_box.question.assert_called_once()
            self.assertEqual(existing.read_text(), "sentinel")

    def test_export_paths_confirm_overwrite_when_normalization_retargets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cases = (
                ("target.xyz", "export_xyz", "export_xyz_async"),
                ("target.mol", "export_mol", "export_mol"),
                ("target.svg", "export_figure", "export_figure"),
            )
            for existing_name, method_name, session_method in cases:
                with self.subTest(surface=method_name):
                    existing = Path(temp_dir) / existing_name
                    existing.write_text("sentinel")
                    file_dialog = mock.Mock()
                    file_dialog.getSaveFileName.return_value = (
                        str(Path(temp_dir) / "target"),
                        "",
                    )
                    message_box = mock.Mock()
                    message_box.question.return_value = QMessageBox.StandardButton.No
                    session_service = mock.Mock()

                    with contextlib.ExitStack() as stack:
                        stack.enter_context(
                            mock.patch.object(
                                self.service,
                                "_document_session_service_for_window",
                                return_value=session_service,
                            )
                        )
                        if method_name == "export_figure":
                            stack.enter_context(
                                mock.patch(
                                    "chemvas.ui.main_window_document_action_service."
                                    "prompt_export_options",
                                    return_value=SimpleNamespace(
                                        fmt="svg",
                                        scope="sheet",
                                        dpi=300,
                                        background="transparent",
                                        sizing="bond",
                                        editable_svg=False,
                                    ),
                                )
                            )
                        getattr(self.service, method_name)(
                            self.window,
                            file_dialog=file_dialog,
                            message_box=message_box,
                        )
                    getattr(session_service, session_method).assert_not_called()
                    message_box.question.assert_called_once()

    def test_export_figure_forwards_limits_and_reports_guard_failure(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("figure.svg", "")
        message_box = mock.Mock()
        session = mock.Mock()
        session.export_figure.side_effect = MinimumFontSizeError(
            5.762193,
            7.25,
            {"kind": "arrow", "index": 1, "part": "label", "script": True},
        )
        options = FigureExportOptions(
            fmt="svg",
            sizing="custom",
            scope="sheet",
            dpi=300,
            background="transparent",
            target_width_mm=83.75,
            max_height_mm=120.25,
            min_font_pt=7.25,
        )
        with (
            mock.patch(
                "chemvas.ui.main_window_document_action_service.prompt_export_options",
                return_value=options,
            ),
            mock.patch.object(
                self.service,
                "_document_session_service_for_window",
                return_value=session,
            ),
        ):
            self.service.export_figure(
                self.window, file_dialog=file_dialog, message_box=message_box
            )
        session.export_figure.assert_called_once_with(
            "figure.svg",
            fmt="svg",
            scope="sheet",
            dpi=300,
            background="transparent",
            sizing="custom",
            editable_svg=False,
            target_width_mm=83.75,
            max_height_mm=120.25,
            min_font_pt=7.25,
        )
        message_box.warning.assert_called_once()
        message = message_box.warning.call_args.args[2]
        self.assertIn("5.76 pt", message)
        self.assertIn("7.25 pt", message)
        self.assertIn("Increase the export width", message)
        self.assertIn("No file was written", message)
        self.assertNotIn("--min-font-pt", message)
        self.assertNotIn("'kind'", message)
        self.assertNotIn("Exported:", self.window.statusBar().currentMessage())

    def test_export_height_failure_explains_gui_controls_and_preserves_destination(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        add_bond_between_points_for(canvas, QPointF(-20, -30), QPointF(20, 30))
        before = snapshot_canvas_state_for(canvas)
        with tempfile.TemporaryDirectory() as temp_dir:
            for fmt in ("svg", "pdf", "png", "tiff"):
                for existing in (False, True):
                    with self.subTest(fmt=fmt, existing=existing):
                        path = Path(temp_dir) / f"figure-{existing}.{fmt}"
                        sentinel = b"previous successful export"
                        if existing:
                            path.write_bytes(sentinel)
                        options = FigureExportOptions(
                            fmt=fmt,
                            sizing="custom",
                            scope="sheet",
                            dpi=300,
                            background="white",
                            target_width_mm=84,
                            max_height_mm=1,
                        )
                        file_dialog = mock.Mock()
                        file_dialog.getSaveFileName.return_value = (str(path), "")
                        message_box = mock.Mock()
                        with mock.patch(
                            "chemvas.ui.main_window_document_action_service."
                            "prompt_export_options",
                            return_value=options,
                        ):
                            self.service.export_figure(
                                self.window,
                                file_dialog=file_dialog,
                                message_box=message_box,
                            )
                        message_box.warning.assert_called_once()
                        message = message_box.warning.call_args.args[2]
                        self.assertIn("The exported figure is", message)
                        self.assertIn("the maximum is 1 mm", message)
                        self.assertIn("Reduce the export width", message)
                        self.assertIn("Limit exported height", message)
                        self.assertIn("No file was written or resized", message)
                        self.assertNotIn("--max-height-mm", message)
                        self.assertNotIn(
                            "Exported:", self.window.statusBar().currentMessage()
                        )
                        if existing:
                            self.assertEqual(path.read_bytes(), sentinel)
                        else:
                            self.assertFalse(path.exists())
                        self.assertEqual(snapshot_canvas_state_for(canvas), before)

    def test_export_figure_cancel_does_not_request_path_or_session(self) -> None:
        file_dialog = mock.Mock()
        with (
            mock.patch(
                "chemvas.ui.main_window_document_action_service.prompt_export_options",
                return_value=None,
            ),
            mock.patch.object(
                self.service, "_document_session_service_for_window"
            ) as session,
        ):
            self.service.export_figure(self.window, file_dialog=file_dialog)
        file_dialog.getSaveFileName.assert_not_called()
        session.assert_not_called()

    def test_export_figure_cancelled_destination_does_not_call_session(self) -> None:
        file_dialog = mock.Mock()
        file_dialog.getSaveFileName.return_value = ("", "")
        options = FigureExportOptions(
            fmt="svg",
            sizing="custom",
            scope="sheet",
            dpi=300,
            background="transparent",
            target_width_mm=84,
            min_font_pt=7,
        )
        with (
            mock.patch(
                "chemvas.ui.main_window_document_action_service.prompt_export_options",
                return_value=options,
            ),
            mock.patch.object(
                self.service, "_document_session_service_for_window"
            ) as session,
        ):
            self.service.export_figure(self.window, file_dialog=file_dialog)
        file_dialog.getSaveFileName.assert_called_once()
        session.assert_not_called()

    def test_load_canvas_dialog_advertises_only_public_document_suffixes(
        self,
    ) -> None:
        file_dialog = mock.Mock()
        file_dialog.getOpenFileName.return_value = ("", "")

        self.assertFalse(self.service.load_canvas(self.window, file_dialog=file_dialog))

        file_dialog.getOpenFileName.assert_called_once()
        self.assertEqual(
            file_dialog.getOpenFileName.call_args.args[3],
            (
                "Chemvas / Editable SVG / MDL Molfile (*.chemvas *.svg *.mol);;"
                "Chemvas (*.chemvas);;Editable SVG (*.svg);;"
                "MDL Molfile (*.mol);;All Files (*)"
            ),
        )

    def test_load_canvas_from_path_reuses_clean_untitled_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "input.chemvas"
            state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
            write_document(path, state, version=CANVAS_FILE_VERSION)

            result = self.service.load_canvas_from_path(self.window, str(path))

        self.assertTrue(result)
        self.assertEqual(self.window.tab_references.canvas_count(), 1)
        self.assertEqual(
            self.window.tab_references.canvas_tabs.tabText(0), "input.chemvas"
        )
        self.assertEqual(
            document_file_path_for(active_canvas_for_window(self.window)), str(path)
        )

    def test_load_canvas_from_path_rejects_legacy_json_document(self) -> None:
        message_box = mock.Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "recent-legacy.json"
            state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
            write_document(path, state, version=CANVAS_FILE_VERSION)

            with mock.patch(
                "chemvas.ui.main_window_document_action_service.default_read_document"
            ) as read_document:
                result = self.service.load_canvas_from_path(
                    self.window, str(path), message_box=message_box
                )

        self.assertFalse(result)
        read_document.assert_not_called()
        message_box.warning.assert_called_once_with(
            self.window,
            "Load Error",
            "Unsupported file type. Open a .chemvas, .svg, or .mol file.",
        )
        self.assertIsNone(document_file_path_for(active_canvas_for_window(self.window)))

    def test_load_canvas_from_path_imports_mol_as_untitled_document(self) -> None:
        source = MoleculeModel()
        a = source.add_atom("C", 0.0, 0.0)
        b = source.add_atom("N", 30.0, 0.0)
        c = source.add_atom("O", 60.0, 0.0)
        source.add_bond(a, b, 1)
        source.add_bond(b, c, 1)
        message_box = mock.Mock()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ethanol.mol"
            path.write_text(
                write_molfile(
                    source,
                    atom_annotations={
                        b: {"formal_charge": 2, "radical_electrons": 2},
                        c: {"formal_charge": -1},
                    },
                ),
                encoding="utf-8",
            )
            with mock.patch(
                "chemvas.ui.main_window_document_action_service.record_recent"
            ) as record_recent:
                result = self.service.load_canvas_from_path(
                    self.window,
                    str(path),
                    message_box=message_box,
                    target_provider=lambda: self.window,
                )

        self.assertTrue(result)
        message_box.warning.assert_not_called()
        # The import has no backing .chemvas document: it must stay untitled
        # (Save prompts for a new path instead of overwriting the .mol) and
        # must not enter the recent-files list.
        record_recent.assert_not_called()
        canvas = active_canvas_for_window(self.window)
        self.assertIsNone(document_file_path_for(canvas))
        self.assertEqual(
            self.window.tab_references.canvas_tabs.tabText(0), "ethanol.mol"
        )
        model = model_for(canvas)
        self.assertEqual(
            sorted(atom.element for atom in model.atoms.values()), ["C", "N", "O"]
        )
        expected_annotations = {
            b: {"formal_charge": 2, "radical_electrons": 2},
            c: {"formal_charge": -1},
        }
        self.assertEqual(model.atom_annotations, expected_annotations)
        self.assertEqual(
            mark_kinds_by_atom_for(canvas),
            {b: ["plus", "plus", "radical", "radical"], c: ["minus"]},
        )
        base_mark_distance = bond_length_px_for(canvas) * 0.2
        for atom_id in (b, c):
            for mark in mark_registry_for(canvas).get_for_atom(atom_id) or ():
                mark_data = mark.data(1)
                self.assertGreater(
                    math.hypot(mark_data["dx"], mark_data["dy"]),
                    base_mark_distance,
                )
        export_model, export_annotations = build_3d_conversion_payload_for(canvas)
        self.assertEqual(export_annotations, expected_annotations)
        reparsed = parse_molfile(
            write_molfile(export_model, atom_annotations=export_annotations)
        )
        self.assertEqual(reparsed.atom_annotations, expected_annotations)
        self.assertFalse(
            services_for_window(self.window).canvas_document_service.is_dirty(canvas)
        )
        self.assertTrue(
            all(
                "_auto_position" not in mark
                for mark in snapshot_canvas_state_for(canvas)["marks"]
            )
        )
        live_bonds = [bond for bond in model.bonds if bond is not None]
        self.assertEqual(len(live_bonds), 2)
        # The structure is rescaled to the canvas bond length and centred on
        # the sheet (the sheet is centred on the scene origin).
        for bond in live_bonds:
            self.assertAlmostEqual(
                math.hypot(
                    model.atoms[bond.a].x - model.atoms[bond.b].x,
                    model.atoms[bond.a].y - model.atoms[bond.b].y,
                ),
                bond_length_px_for(canvas),
                delta=0.1,
            )
        min_x, min_y, max_x, max_y = model.bounds()
        self.assertAlmostEqual(min_x + (max_x - min_x) / 2.0, 0.0, delta=0.1)
        self.assertAlmostEqual(min_y + (max_y - min_y) / 2.0, 0.0, delta=0.1)

    def test_mol_annotation_mark_failure_restores_the_previous_document(self) -> None:
        canvas = active_canvas_for_window(self.window)
        before = snapshot_canvas_state_for(canvas)
        source = MoleculeModel()
        atom_id = source.add_atom("N", 0.0, 0.0)
        message_box = mock.Mock()
        mark_calls = 0

        def fail_second_mark(*args, **kwargs):
            nonlocal mark_calls
            mark_calls += 1
            if mark_calls == 2:
                return None
            return materialize_mark_for_atom_for(*args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "charged.mol"
            path.write_text(
                write_molfile(source, atom_annotations={atom_id: {"formal_charge": 2}}),
                encoding="utf-8",
            )
            with mock.patch(
                "chemvas.ui.canvas_document_state.materialize_mark_for_atom_for",
                side_effect=fail_second_mark,
            ):
                result = self.service.load_canvas_from_path(
                    self.window,
                    str(path),
                    message_box=message_box,
                    target_provider=lambda: self.window,
                )

        self.assertFalse(result)
        self.assertEqual(mark_calls, 2)
        message_box.warning.assert_called_once()
        self.assertIn("atom annotation", message_box.warning.call_args.args[2])
        self.assertEqual(snapshot_canvas_state_for(canvas), before)

    def test_load_canvas_from_path_rejects_invalid_mol_without_a_new_window(
        self,
    ) -> None:
        message_box = mock.Mock()
        spawned: list[object] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.mol"
            path.write_text(
                write_molfile(MoleculeModel()).replace("V2000", "V3000"),
                encoding="utf-8",
            )
            result = self.service.load_canvas_from_path(
                self.window,
                str(path),
                message_box=message_box,
                target_provider=lambda: spawned.append(object()),
            )

        self.assertFalse(result)
        # The file is rejected before a destination window is resolved, so a
        # broken .mol never spawns an empty window.
        self.assertEqual(spawned, [])
        message_box.warning.assert_called_once()
        self.assertIn("V3000", message_box.warning.call_args.args[2])
        self.assertEqual(self.window.tab_references.canvas_count(), 1)

    def test_load_canvas_rejects_workbook_payload_without_importing(self) -> None:
        state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
        read_document = mock.Mock(
            return_value=SimpleNamespace(
                state={
                    "active_sheet_index": 0,
                    "sheets": [
                        {"name": "Canvas 1", "kind": "canvas", "content": state}
                    ],
                }
            )
        )
        message_box = mock.Mock()

        result = self.service.load_canvas_from_path(
            self.window,
            "/tmp/workbook.chemvas",
            message_box=message_box,
            read_document=read_document,
        )

        self.assertFalse(result)
        self.assertEqual(self.window.tab_references.canvas_count(), 1)
        message_box.warning.assert_called_once()

    def test_confirm_close_canvas_handles_save_discard_and_cancel(self) -> None:
        canvas = active_canvas_for_window(self.window)
        add_bond_between_points_for(canvas, QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        message_box = mock.Mock()
        message_box.question.return_value = QMessageBox.StandardButton.Cancel

        self.assertFalse(
            self.service.confirm_close_canvas(
                self.window, canvas, message_box=message_box
            )
        )

        message_box.question.return_value = QMessageBox.StandardButton.Discard
        self.assertTrue(
            self.service.confirm_close_canvas(
                self.window, canvas, message_box=message_box
            )
        )

        message_box.question.return_value = QMessageBox.StandardButton.Save
        with mock.patch.object(
            self.service, "save_canvas", return_value=True
        ) as save_canvas:
            self.assertTrue(
                self.service.confirm_close_canvas(
                    self.window, canvas, message_box=message_box
                )
            )
        save_canvas.assert_called_once_with(self.window, canvas=canvas)

    def test_confirm_close_canvas_rejects_active_xyz_export_until_job_finishes(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        message_box = mock.Mock()

        with mock.patch(
            "chemvas.ui.main_window_document_action_service.rdkit_export_jobs_for",
            return_value=[(object(), object())],
        ):
            self.assertFalse(
                self.service.confirm_close_canvas(
                    self.window, canvas, message_box=message_box
                )
            )

        message_box.warning.assert_called_once_with(
            self.window,
            "XYZ Export in Progress",
            "Wait for the 3D XYZ export from Canvas 1 to finish before closing it.",
        )
        message_box.question.assert_not_called()

        with mock.patch(
            "chemvas.ui.main_window_document_action_service.rdkit_export_jobs_for",
            return_value=[],
        ):
            self.assertTrue(
                self.service.confirm_close_canvas(
                    self.window, canvas, message_box=message_box
                )
            )
