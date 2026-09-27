import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from chemvas.bootstrap.window_registry import open_new_window
from chemvas.core.document_io import read_document
from chemvas.shell.window_registry import forget_window, open_windows
from chemvas.ui.molecule.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.session import session_snapshot_store as session_store_module
from chemvas.ui.session.app_data_paths import sessions_dir
from chemvas.ui.session.session_recovery_service import (
    SessionRecoveryService,
    collect_open_documents,
)
from chemvas.ui.session.session_snapshot_store import SessionSnapshotStore
from chemvas.ui.window.main_window_ports import active_canvas_for_window


class SessionRecoveryIntegrationTest(unittest.TestCase):
    """End-to-end: a real window is drawn on, autosaved, 'crashes', and its
    unsaved drawing is rebuilt into a fresh window on the next launch.

    app-data is redirected to a tmp dir by the autouse conftest fixture, so this
    reads and writes only throwaway session files.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _activate(self, window):
        self.assertTrue(QTest.qWaitForWindowExposed(window, 5000))
        window.raise_()
        window.activateWindow()
        if QApplication.platformName() != "offscreen":
            self.assertTrue(QTest.qWaitForWindowActive(window, 5000))
        canvas = active_canvas_for_window(window)
        canvas.setFocus()
        self.app.processEvents()
        self.assertTrue(canvas.hasFocus())

    def _document_service(self, window):
        return window.services.canvas_document_service

    def tearDown(self) -> None:
        # Also close windows if an assertion fails before recovery starts.
        for window in list(open_windows()):
            canvas = active_canvas_for_window(window)
            self._document_service(window).mark_clean(canvas)
            forget_window(window)
            window.close()
        self.app.processEvents()

    def test_saved_document_edit_undo_redo_crash_and_recovery(self) -> None:
        self._exercise_recovery(saved_source=True)

    def test_untitled_document_edit_undo_redo_crash_and_recovery(self) -> None:
        self._exercise_recovery(saved_source=False)

    def _exercise_recovery(self, *, saved_source: bool) -> None:
        prev_window = open_new_window()
        self._activate(prev_window)
        canvas = active_canvas_for_window(prev_window)
        add_bond_between_points_for(canvas, QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        self.assertTrue(self._document_service(prev_window).is_dirty(canvas))

        source = sessions_dir().parent / "source.chemvas"
        original_bytes = None
        if saved_source:
            self.assertTrue(
                prev_window.services.document_action_service.save_canvas_to_path(
                    prev_window, str(source), canvas=canvas
                )
            )
            original_bytes = source.read_bytes()
            forget_window(prev_window)
            prev_window.close()
            self.app.processEvents()

            prev_window = open_new_window()
            self.app.processEvents()
            self.assertTrue(
                prev_window.services.document_action_service.load_canvas_from_path(
                    prev_window, str(source)
                )
            )
        self._activate(prev_window)
        canvas = active_canvas_for_window(prev_window)
        documents = canvas.services.canvas_document_session_service
        self.assertEqual(
            self._document_service(prev_window).is_dirty(canvas), not saved_source
        )
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [{"id": 0, "element": "N", "x": 180, "y": 80}],
            "bonds": [],
            "rings": [],
            "marks": [],
            "scene_items": [],
        }
        edits = (
            (
                "bond",
                lambda: add_bond_between_points_for(
                    canvas, QPointF(80.0, 0.0), QPointF(120.0, 0.0)
                ),
            ),
            (
                "paste",
                lambda: (
                    canvas.services.scene_clipboard_controller.paste_selection_from_clipboard(
                        payload_provider=lambda: (payload, "recovery-lifecycle-paste")
                    )
                ),
            ),
            ("delete", lambda: canvas.services.scene_delete_controller.delete_bond(0)),
        )
        for name, edit in edits:
            with self.subTest(edit=name):
                before = documents.snapshot_state()
                was_dirty = self._document_service(prev_window).is_dirty(canvas)
                edit()
                edited = documents.snapshot_state()
                self.assertNotEqual(edited, before)
                QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Undo))
                self.app.processEvents()
                self.assertEqual(documents.snapshot_state(), before)
                self.assertEqual(
                    self._document_service(prev_window).is_dirty(canvas), was_dirty
                )
                QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Redo))
                self.app.processEvents()
                self.assertEqual(documents.snapshot_state(), edited)
                self.assertTrue(self._document_service(prev_window).is_dirty(canvas))

        prev_store = SessionSnapshotStore(
            sessions_dir(), session_id="prev-session", pid=os.getpid()
        )
        prev_store.begin()
        prev_store.save_documents(collect_open_documents())
        # No mark_clean_exit() → the manifest stays "unclean", i.e. a crash.

        # Cancelling an actual window close keeps both the dirty drawing and
        # the last recovery copy, before the simulated crash below.
        recovery_bytes = {
            path: path.read_bytes()
            for path in prev_store.session_dir.iterdir()
            if path.is_file()
        }
        with mock.patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel
        ) as question:
            self.assertFalse(prev_window.close())
        question.assert_called_once()
        self.assertIn(prev_window, open_windows())
        self.assertEqual(documents.snapshot_state(), edited)
        self.assertTrue(self._document_service(prev_window).is_dirty(canvas))
        self.assertEqual(
            {
                path: path.read_bytes()
                for path in prev_store.session_dir.iterdir()
                if path.is_file()
            },
            recovery_bytes,
        )

        # The crashed instance disappears. Mark clean only to skip the unsaved
        # close prompt, drop it from the registry, and close it.
        self._document_service(prev_window).mark_clean(canvas)
        forget_window(prev_window)
        prev_window.close()
        self.app.processEvents()

        # --- relaunch: a fresh window restores the previous session ----------
        # Force the previous pid to read as dead so it counts as a crash rather
        # than a live instance (both share this test process's pid otherwise).
        new_window = open_new_window()
        self._activate(new_window)
        restored_canvas = None
        recovery = SessionRecoveryService(
            SessionSnapshotStore(
                sessions_dir(), session_id="cur-session", pid=os.getpid()
            ),
            open_new_window=open_new_window,
        )
        try:
            recovery.start(SimpleNamespace())
            with mock.patch.object(
                session_store_module, "_pid_alive", return_value=False
            ):
                recovered = recovery.restore_previous(new_window)

            self.assertEqual(recovered, 1)
            restored_canvas = active_canvas_for_window(new_window)
            restored_state = restored_canvas.services.canvas_document_session_service.snapshot_state()
            # Recover the complete edited document, without overwriting its source.
            self.assertEqual(restored_state, edited)
            self.assertIsNone(
                restored_canvas.runtime_state.document_metadata_state.file_path
            )
            if saved_source:
                self.assertEqual(source.read_bytes(), original_bytes)
            # ...and the restored document is flagged unsaved for the user.
            self.assertTrue(
                self._document_service(new_window).is_dirty(restored_canvas)
            )
            # The copy is snapshotted into this session before its original
            # session is released.
            manifest = json.loads(
                (sessions_dir() / "cur-session" / "session.json").read_bytes()
            )
            self.assertEqual([entry["dirty"] for entry in manifest["docs"]], [True])
            self.assertFalse((sessions_dir() / "prev-session").exists())
            recovered_path = source.with_name("recovered.chemvas")
            self.assertTrue(
                new_window.services.document_action_service.save_canvas_to_path(
                    new_window, str(recovered_path), canvas=restored_canvas
                )
            )
            self.assertEqual(
                read_document(recovered_path).state, json.loads(json.dumps(edited))
            )
            self.assertFalse(
                self._document_service(new_window).is_dirty(restored_canvas)
            )
            if saved_source:
                self.assertEqual(source.read_bytes(), original_bytes)
        finally:
            if recovery._timer is not None:
                recovery._timer.stop()
            if restored_canvas is not None:
                self._document_service(new_window).mark_clean(restored_canvas)
            forget_window(new_window)
            new_window.close()
            self.app.processEvents()
