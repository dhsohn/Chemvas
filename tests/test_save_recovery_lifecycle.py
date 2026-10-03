"""Save/recovery lifecycle: metadata invariants through failure and success.

Exercises the full save owner path in MainWindowDocumentActionService with
real atomic writes, verifying that file_path, source_sha256, dirty, and
display_name remain correct through:
- a first Save-As that establishes the saved baseline,
- a failed Save (injected at os.fsync) that must leave every invariant intact,
- a successful retry,
- a subsequent Save that must not trigger a false "File Changed" prompt.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtWidgets import QApplication, QMessageBox

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document
from chemvas.ui.molecule.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.session.open_document_lookup import (
    paths_refer_to_same_document,
    resolved_document_path,
)
from chemvas.ui.window.main_window_ports import active_canvas_for_window


class SaveRecoveryLifecycleTest(unittest.TestCase):
    """source_sha256 preservation across failed and successful saves."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.window.show()
        self.app.processEvents()
        self.service = self.window.services.document_action_service
        self.documents = self.window.services.canvas_document_service

    def tearDown(self) -> None:
        for canvas in self.window.tab_references.all_canvases():
            self.documents.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_failed_save_preserves_source_sha256_for_external_change_detection(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "drawing.chemvas"

            # --- Step 1: initial save establishes the baseline ---
            add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))
            self.assertTrue(self.service.save_canvas_to_path(self.window, str(path)))
            self.assertTrue(path.exists())

            saved_sha256 = canvas.runtime_state.document_metadata_state.source_sha256
            self.assertIsNotNone(saved_sha256)
            saved_bytes = path.read_bytes()
            self.assertEqual(
                hashlib.sha256(saved_bytes).hexdigest(),
                saved_sha256,
            )
            self.assertFalse(self.documents.is_dirty(canvas))
            self.assertEqual(
                canvas.runtime_state.document_metadata_state.file_path, str(path)
            )

            # --- Step 2: edit makes the document dirty ---
            add_bond_between_points_for(canvas, QPointF(40, 0), QPointF(80, 0))
            self.assertTrue(self.documents.is_dirty(canvas))
            edited_state = (
                canvas.services.canvas_document_session_service.snapshot_state()
            )

            # --- Step 3: save fails at fsync → all invariants must survive ---
            message_box = mock.Mock()
            with mock.patch(
                "chemvas.core.document_io.os.fsync", side_effect=OSError("disk full")
            ):
                result = self.service.save_canvas_to_path(
                    self.window, str(path), message_box=message_box
                )
            self.assertFalse(result)
            message_box.warning.assert_called_once()

            # file_path is still the original path
            self.assertEqual(
                canvas.runtime_state.document_metadata_state.file_path, str(path)
            )
            # source_sha256 is still the hash from the FIRST save, not contaminated
            self.assertEqual(
                canvas.runtime_state.document_metadata_state.source_sha256,
                saved_sha256,
            )
            # the file on disk is unchanged
            self.assertEqual(path.read_bytes(), saved_bytes)
            # the document is still dirty with the edited state
            self.assertTrue(self.documents.is_dirty(canvas))
            self.assertEqual(
                canvas.services.canvas_document_session_service.snapshot_state(),
                edited_state,
            )
            # display name is unchanged
            self.assertEqual(
                canvas.runtime_state.document_metadata_state.display_name,
                "drawing.chemvas",
            )

            # --- Step 4: successful retry saves the edited state ---
            self.assertTrue(self.service.save_canvas_to_path(self.window, str(path)))
            retry_sha256 = canvas.runtime_state.document_metadata_state.source_sha256
            self.assertIsNotNone(retry_sha256)
            self.assertNotEqual(retry_sha256, saved_sha256)
            retry_bytes = path.read_bytes()
            self.assertEqual(
                hashlib.sha256(retry_bytes).hexdigest(),
                retry_sha256,
            )
            self.assertFalse(self.documents.is_dirty(canvas))
            self.assertEqual(
                read_document(path).state,
                json.loads(json.dumps(edited_state)),
            )

            # --- Step 5: subsequent Save must not prompt "File Changed" ---
            add_bond_between_points_for(canvas, QPointF(100, 0), QPointF(140, 0))
            self.assertTrue(self.documents.is_dirty(canvas))
            question_box = mock.Mock()
            question_box.question.return_value = QMessageBox.StandardButton.No
            self.assertTrue(
                self.service.save_canvas_to_path(
                    self.window, str(path), message_box=question_box
                )
            )
            question_box.question.assert_not_called()
            self.assertFalse(self.documents.is_dirty(canvas))

    def test_save_as_on_recovered_document_clears_dirty_sentinel_and_sets_path(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))

        # Simulate recovery: no file_path, no source_sha256, forced dirty.
        self.documents.set_file_path(canvas, None)
        self.documents.set_display_name(canvas, "Draft (recovered copy)")
        self.documents.mark_dirty(canvas)
        self.assertIsNone(canvas.runtime_state.document_metadata_state.file_path)
        self.assertIsNone(canvas.runtime_state.document_metadata_state.source_sha256)
        self.assertTrue(self.documents.is_dirty(canvas))

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "recovered.chemvas"

            # Save-As to a new path.
            self.assertTrue(self.service.save_canvas_to_path(self.window, str(path)))

            # file_path points to the new path
            self.assertEqual(
                canvas.runtime_state.document_metadata_state.file_path, str(path)
            )
            # source_sha256 is set from the written bytes
            sha256 = canvas.runtime_state.document_metadata_state.source_sha256
            self.assertIsNotNone(sha256)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                sha256,
            )
            # no longer dirty
            self.assertFalse(self.documents.is_dirty(canvas))
            # display name updated (no "recovered copy")
            self.assertEqual(
                canvas.runtime_state.document_metadata_state.display_name,
                "recovered.chemvas",
            )
            # tab title updated
            self.assertEqual(
                self.window.tab_references.canvas_tabs.tabText(0),
                "recovered.chemvas",
            )

            # A subsequent Save uses the new path, not Save-As.
            add_bond_between_points_for(canvas, QPointF(40, 0), QPointF(80, 0))
            self.assertTrue(self.documents.is_dirty(canvas))

            question_box = mock.Mock()
            question_box.question.return_value = QMessageBox.StandardButton.No
            self.assertTrue(
                self.service.save_canvas_to_path(
                    self.window, str(path), message_box=question_box
                )
            )
            # No "File Changed" prompt (source_sha256 matches disk)
            question_box.question.assert_not_called()
            self.assertFalse(self.documents.is_dirty(canvas))

            # source_sha256 updated to the new file's bytes
            new_sha256 = canvas.runtime_state.document_metadata_state.source_sha256
            self.assertNotEqual(new_sha256, sha256)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                new_sha256,
            )

    def test_case_alias_save_triggers_external_change_check(self) -> None:
        """Saving via a case-variant alias of the current path must not skip
        the external-change guard on case-insensitive volumes.

        On macOS APFS (case-insensitive), ``resolved_document_path`` preserves
        the caller-supplied case, so ``drawing.chemvas`` and ``DRAWING.chemvas``
        resolve to different strings even though ``os.path.samefile`` confirms
        they share an inode.  ``save_canvas_to_path`` delegates to
        ``paths_refer_to_same_document`` to detect this identity and run the
        external-change SHA check.
        """
        canvas = active_canvas_for_window(self.window)

        with tempfile.TemporaryDirectory() as temp_dir:
            original = Path(temp_dir) / "drawing.chemvas"
            alias = Path(temp_dir) / "DRAWING.chemvas"

            # Probe: does this volume treat the two names as the same file?
            original.write_bytes(b"probe")
            try:
                same = os.path.samefile(str(original), str(alias))
            except OSError:
                same = False
            original.unlink()
            if not same:
                self.skipTest(
                    "case-sensitive filesystem: case alias is a distinct path"
                )

            # --- Step 1: establish saved baseline ---
            add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))
            self.assertTrue(
                self.service.save_canvas_to_path(self.window, str(original))
            )
            saved_sha = canvas.runtime_state.document_metadata_state.source_sha256
            self.assertIsNotNone(saved_sha)
            saved_file_path = canvas.runtime_state.document_metadata_state.file_path
            saved_display = canvas.runtime_state.document_metadata_state.display_name

            # Confirm the alias is the same inode.
            self.assertTrue(os.path.samefile(str(original), str(alias)))
            # On Darwin, resolved strings preserve caller-supplied case and
            # therefore differ; on Windows, realpath canonicalizes to on-disk
            # case, so they may be equal.  Assert only where the premise holds.
            if sys.platform == "darwin":
                self.assertNotEqual(
                    resolved_document_path(str(original)),
                    resolved_document_path(str(alias)),
                )

            # --- Step 2: local edit ---
            add_bond_between_points_for(canvas, QPointF(40, 0), QPointF(80, 0))
            self.assertTrue(self.documents.is_dirty(canvas))
            edited_state = (
                canvas.services.canvas_document_session_service.snapshot_state()
            )

            # --- Step 3: external modification (trailing whitespace) ---
            original_bytes = original.read_bytes()
            modified_bytes = original_bytes + b"  \n"
            original.write_bytes(modified_bytes)

            # --- Step 4: save via case-alias, answer No to keep both ---
            question_box = mock.Mock()
            question_box.question.return_value = QMessageBox.StandardButton.No
            result = self.service.save_canvas_to_path(
                self.window, str(alias), message_box=question_box
            )

            # The save must be refused and the "File Changed" prompt shown.
            self.assertFalse(result)
            question_box.question.assert_called_once()
            self.assertEqual(question_box.question.call_args[0][1], "File Changed")

            # External bytes on disk are preserved.
            self.assertEqual(original.read_bytes(), modified_bytes)

            # Canvas metadata is unchanged.
            self.assertEqual(
                canvas.runtime_state.document_metadata_state.source_sha256,
                saved_sha,
            )
            self.assertEqual(
                canvas.runtime_state.document_metadata_state.file_path,
                saved_file_path,
            )
            self.assertEqual(
                canvas.runtime_state.document_metadata_state.display_name,
                saved_display,
            )
            self.assertTrue(self.documents.is_dirty(canvas))
            self.assertEqual(
                canvas.services.canvas_document_session_service.snapshot_state(),
                edited_state,
            )

    def test_paths_refer_to_same_document_identifies_case_aliases(self) -> None:
        """The shared identity helper must recognise case-variant paths as the
        same document on case-insensitive volumes.  ``save_canvas_to_path``
        delegates to this helper for the external-change guard.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "sample.chemvas"
            alias = Path(temp_dir) / "SAMPLE.chemvas"

            target.write_bytes(b"probe")
            try:
                same = os.path.samefile(str(target), str(alias))
            except OSError:
                same = False

            if same:
                # Case-insensitive: helper must agree with samefile.
                self.assertTrue(paths_refer_to_same_document(str(target), str(alias)))
                # On Darwin, resolved strings preserve caller case and differ;
                # on Windows, realpath canonicalizes to on-disk case.
                if sys.platform == "darwin":
                    self.assertNotEqual(
                        resolved_document_path(str(target)),
                        resolved_document_path(str(alias)),
                    )
            else:
                # Case-sensitive: they are genuinely different paths.
                self.assertFalse(paths_refer_to_same_document(str(target), str(alias)))
            target.unlink()
