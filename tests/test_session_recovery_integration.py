import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QPointF = None

if QApplication is not None:
    from ui import session_snapshot_store as session_store_module
    from ui.app_data_paths import sessions_dir
    from ui.canvas_window_access import snapshot_canvas_state_for
    from ui.main_window_app import forget_window, open_new_window
    from ui.main_window_ports import active_canvas_for_window, services_for_window
    from ui.session_recovery_service import (
        SessionRecoveryService,
        collect_open_documents,
    )
    from ui.session_snapshot_store import SessionSnapshotStore
    from ui.structure_mutation_access import add_bond_between_points_for


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for session recovery integration tests")
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

    def _document_service(self, window):
        return services_for_window(window).canvas_document_service

    def test_crash_then_relaunch_restores_the_unsaved_drawing(self) -> None:
        # --- previous session: draw something, then autosave a snapshot -------
        prev_window = open_new_window()
        self.app.processEvents()
        canvas = active_canvas_for_window(prev_window)
        add_bond_between_points_for(canvas, QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        self.assertTrue(self._document_service(prev_window).is_dirty(canvas))

        prev_store = SessionSnapshotStore(sessions_dir(), session_id="prev-session", pid=os.getpid())
        prev_store.begin()
        prev_store.save_documents(collect_open_documents())
        # No mark_clean_exit() → the manifest stays "unclean", i.e. a crash.

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
        self.app.processEvents()
        restored_canvas = None
        try:
            with mock.patch.object(session_store_module, "_pid_alive", return_value=False):
                recovery = SessionRecoveryService(
                    SessionSnapshotStore(sessions_dir(), session_id="cur-session", pid=os.getpid())
                )
                recovered = recovery.restore_previous(new_window)

            self.assertEqual(recovered, 1)
            restored_canvas = active_canvas_for_window(new_window)
            restored_state = snapshot_canvas_state_for(restored_canvas)
            # The drawn bond (and its two atoms) survived the crash round-trip...
            self.assertTrue(restored_state["model"]["atoms"])
            # ...and the restored document is flagged unsaved for the user.
            self.assertTrue(self._document_service(new_window).is_dirty(restored_canvas))
            # Deferred prune: the source dir survives restore_previous and is only
            # deleted by start() after the recovered work is re-snapshotted.
            self.assertTrue((sessions_dir() / "prev-session").exists())
        finally:
            if restored_canvas is not None:
                self._document_service(new_window).mark_clean(restored_canvas)
            forget_window(new_window)
            new_window.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
