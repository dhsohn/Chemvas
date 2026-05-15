import os
import tempfile
import unittest
from json import dumps
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QTest = None
    Qt = None
    QPointF = None

if QApplication is not None:
    from core.document_io import read_document, write_document
    from core.model import MoleculeModel
    from core.rdkit_adapter import Molecule3DAtom, Molecule3DBond, Molecule3DScene
    from ui.main_window import MainWindow


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI tests")
class GuiDocumentAndTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.window.canvas.setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _hover_scene_point(self, point: QPointF) -> None:
        viewport_pos = self.window.canvas.mapFromScene(point)
        QTest.mouseMove(self.window.canvas.viewport(), viewport_pos)
        self.app.processEvents()
        if self.window.canvas._template_insert_active:
            self.window.canvas._render_template_preview(point)
        if self.window.canvas._smiles_insert_active:
            self.window.canvas._render_smiles_preview(point)
        self.app.processEvents()
        QTest.qWait(10)

    def _click_scene_point(self, point: QPointF) -> None:
        viewport_pos = self.window.canvas.mapFromScene(point)
        QTest.mouseClick(
            self.window.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def _press_key(self, key: int, modifiers=None) -> None:
        if modifiers is None:
            modifiers = Qt.KeyboardModifier.NoModifier
        QTest.keyClick(self.window.canvas, key, modifiers)
        self.app.processEvents()
        QTest.qWait(10)

    def _template_handler(self, label: str):
        entries = dict(self.window._template_entries())
        return entries[label]

    @staticmethod
    def _canvas_note_text(canvas) -> str:
        return "\n".join(item.toPlainText() for item in canvas.note_items)

    def test_save_canvas_appends_extension_and_writes_document_payload(self) -> None:
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        self.window.canvas.add_text_note(QPointF(60.0, 10.0), "Scheme")
        self.window.canvas.add_mark(QPointF(20.0, 20.0), kind="plus", atom_id=0, record=False)
        self.window.canvas.add_arrow(QPointF(-40.0, -20.0), QPointF(40.0, -20.0), "reaction")
        self.window.canvas.last_smiles_input = "CCO"

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "example"
            saved_path = Path(f"{raw_path}.chemvas")
            with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=(str(raw_path), "")):
                self.window._save_canvas()

            self.assertTrue(saved_path.exists())
            document = read_document(saved_path)

        self.assertEqual(self.window._current_file_path, str(saved_path))
        self.assertEqual(self.window.statusBar().currentMessage(), f"Saved: {saved_path}")
        self.assertEqual(len(document.state["ring_fills"]), 1)
        self.assertEqual(len(document.state["notes"]), 1)
        self.assertEqual(len(document.state["marks"]), 1)
        self.assertEqual(len(document.state["arrows"]), 1)
        self.assertEqual(document.state["last_smiles_input"], "CCO")

    def test_load_canvas_restores_document_and_resets_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "roundtrip.chemvas"
            self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
            self.window.canvas.add_text_note(QPointF(75.0, 10.0), "Roundtrip")
            self.window.canvas.add_mark(QPointF(20.0, 20.0), kind="minus", atom_id=0, record=False)
            self.window.canvas.add_arrow(QPointF(-50.0, -10.0), QPointF(50.0, -10.0), "equilibrium")
            self.window.canvas.last_smiles_input = "NCCO"
            self.window.canvas.save_to_file(str(path))

            self.window.canvas.clear_scene()
            self.window.canvas._history = ["dirty"]
            self.window.canvas._redo_stack = ["dirty"]
            self.window.canvas.last_smiles_input = None

            preview_model = MoleculeModel()
            left = preview_model.add_atom("C", -10.0, 0.0)
            right = preview_model.add_atom("C", 10.0, 0.0)
            preview_model.add_bond(left, right)
            with patch.object(self.window.canvas.rdkit, "smiles_to_2d", return_value=preview_model):
                self.window.canvas.begin_smiles_insert("CC")
            self.assertTrue(self.window.canvas._smiles_insert_active)

            with patch("ui.main_window.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                self.window._load_canvas()

        self.assertEqual(self.window._current_file_path, str(path))
        self.assertEqual(self.window.statusBar().currentMessage(), f"Loaded: {path}")
        self.assertEqual(len(self.window.canvas.ring_items), 1)
        self.assertEqual(len(self.window.canvas.note_items), 1)
        self.assertEqual(len(self.window.canvas.mark_items), 1)
        self.assertEqual(len(self.window.canvas.arrow_items), 1)
        self.assertEqual(self.window.canvas.last_smiles_input, "NCCO")
        self.assertEqual(self.window.canvas._history, [])
        self.assertEqual(self.window.canvas._redo_stack, [])
        self.assertFalse(self.window.canvas._smiles_insert_active)
        self.assertIsNone(self.window.canvas._smiles_preview_model)
        self.assertIsNone(self.window.canvas._smiles_preview_smiles)
        self.assertIsNone(self.window.canvas._smiles_preview_center)
        self.assertEqual(self.window.canvas._smiles_preview_items, [])

    def test_snapshot_restore_reapplies_saved_settings_before_recreating_items(self) -> None:
        saved_weight = 77
        self.window.canvas.set_bond_length(28.0)
        self.window.canvas.set_arrow_line_width(3.6)
        self.window.canvas.set_arrow_head_scale(0.55)
        self.window.canvas.set_orbital_phase_enabled(True)
        self.window.canvas.set_text_size(18)
        self.window.canvas.set_text_weight(saved_weight)
        self.window.canvas.set_text_italic(True)
        self.window.canvas.add_text_note(QPointF(30.0, 15.0), "Styled")
        self.window.canvas.add_arrow(QPointF(-40.0, 0.0), QPointF(40.0, 0.0), "arrow")

        state = self.window.canvas.snapshot_state()

        self.window.canvas.set_bond_length(16.0)
        self.window.canvas.set_arrow_line_width(1.1)
        self.window.canvas.set_arrow_head_scale(0.2)
        self.window.canvas.set_orbital_phase_enabled(False)
        self.window.canvas.set_text_size(10)
        self.window.canvas.set_text_weight(24)
        self.window.canvas.set_text_italic(False)
        self.window.canvas.clear_scene()

        self.window.canvas.restore_state(state)

        self.assertAlmostEqual(self.window.canvas.renderer.style.bond_length_px, 28.0)
        self.assertAlmostEqual(self.window.canvas.get_arrow_line_width(), 3.6)
        self.assertAlmostEqual(self.window.canvas.get_arrow_head_scale(), 0.55)
        self.assertTrue(self.window.canvas.orbital_phase_enabled)
        self.assertEqual(len(self.window.canvas.note_items), 1)
        restored_font = self.window.canvas.note_items[0].font()
        self.assertEqual(restored_font.pointSize(), 18)
        self.assertEqual(restored_font.weight(), saved_weight)
        self.assertTrue(restored_font.italic())
        self.assertEqual(len(self.window.canvas.arrow_items), 1)
        self.assertAlmostEqual(self.window.canvas.arrow_items[0].pen().widthF(), 3.6)

    def test_snapshot_restore_preserves_atom_bound_mark_offsets(self) -> None:
        atom_id = self.window.canvas.add_atom("C", 12.0, -8.0)
        self.window.canvas.add_mark_for_atom(atom_id, QPointF(42.0, -20.0), kind="minus", record=False)

        state = self.window.canvas.snapshot_state()
        self.assertEqual(len(state["marks"]), 1)
        saved_mark = state["marks"][0]

        self.window.canvas.clear_scene()
        self.window.canvas.restore_state(state)

        self.assertIn(atom_id, self.window.canvas._marks_by_atom)
        self.assertEqual(len(self.window.canvas._marks_by_atom[atom_id]), 1)
        restored_mark = self.window.canvas._marks_by_atom[atom_id][0]
        restored_data = restored_mark.data(1) or {}
        self.assertEqual(restored_data.get("kind"), "minus")
        self.assertEqual(restored_data.get("atom_id"), atom_id)
        self.assertAlmostEqual(restored_data.get("dx"), saved_mark["dx"])
        self.assertAlmostEqual(restored_data.get("dy"), saved_mark["dy"])
        restored_center = self.window.canvas._mark_center(restored_mark)
        self.assertAlmostEqual(restored_center.x(), saved_mark["x"])
        self.assertAlmostEqual(restored_center.y(), saved_mark["y"])

    def test_snapshot_restore_rebuilds_orbital_metadata_from_restored_settings(self) -> None:
        self.window.canvas.set_bond_length(28.0)
        self.window.canvas.set_orbital_phase_enabled(True)
        self.window.canvas.active_orbital_type = "p"
        self.window.canvas.add_orbital(QPointF(18.0, -12.0))
        orbital = self.window.canvas.orbital_items[0]
        orbital.setScale(1.35)
        orbital.setRotation(22.0)

        state = self.window.canvas.snapshot_state()

        self.window.canvas.set_bond_length(16.0)
        self.window.canvas.set_orbital_phase_enabled(False)
        self.window.canvas.clear_scene()

        self.window.canvas.restore_state(state)

        self.assertEqual(len(self.window.canvas.orbital_items), 1)
        restored = self.window.canvas.orbital_items[0]
        data = restored.data(1) or {}
        center = data.get("center")
        meta = restored.data(2) or {}
        self.assertTrue(self.window.canvas.orbital_phase_enabled)
        self.assertEqual(meta.get("kind"), "p")
        self.assertAlmostEqual(self.window.canvas.renderer.style.bond_length_px, 28.0)
        self.assertAlmostEqual(data.get("base_handle_dist"), 22.4)
        self.assertAlmostEqual(center.x(), 18.0)
        self.assertAlmostEqual(center.y(), -12.0)
        self.assertAlmostEqual(restored.scale(), 1.35)
        self.assertAlmostEqual(restored.rotation(), 22.0)
        self.assertIs(restored.scene(), self.window.canvas.scene())

    def test_save_canvas_writes_workbook_state_for_multiple_canvas_sheets(self) -> None:
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        first_sheet_state = self.window.canvas.snapshot_state()

        self.window._new_canvas_sheet()
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        second_sheet_state = self.window.canvas.snapshot_state()

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "workbook"
            saved_path = Path(f"{raw_path}.chemvas")
            with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=(str(raw_path), "")):
                self.window._save_canvas()

            document = read_document(saved_path)

        self.assertEqual(document.state["active_sheet_index"], 1)
        self.assertEqual(len(document.state["sheets"]), 2)
        self.assertEqual(
            len(document.state["sheets"][0]["content"]["model"]["atoms"]),
            len(first_sheet_state["model"]["atoms"]),
        )
        self.assertEqual(
            len(document.state["sheets"][0]["content"]["model"]["bonds"]),
            len(first_sheet_state["model"]["bonds"]),
        )
        self.assertEqual(
            len(document.state["sheets"][1]["content"]["ring_fills"]),
            len(second_sheet_state["ring_fills"]),
        )
        self.assertEqual(
            document.state["sheets"][1]["content"]["model"]["next_atom_id"],
            second_sheet_state["model"]["next_atom_id"],
        )
        self.assertNotIn("result_sheets", document.state)

    def test_load_canvas_restores_workbook_sheets_and_ignores_legacy_result_payloads(self) -> None:
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        first_sheet_state = self.window.canvas.snapshot_state()

        self.window._new_canvas_sheet()
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        second_sheet_state = self.window.canvas.snapshot_state()

        workbook_state = {
            "active_sheet_index": 1,
            "sheets": [
                {"name": "Reactant Sheet", "kind": "canvas", "content": first_sheet_state},
                {"name": "Product Sheet", "kind": "canvas", "content": second_sheet_state},
            ],
            "result_sheets": {
                "active_index": 0,
                "sheets": [
                    {
                        "title": "Path 1",
                        "content": {
                            "title": "Reaction Path Analysis",
                            "subtitle": "RMSD push/pull path finder via xtb --path",
                            "reactant_text": "Reactant Sheet: 2 atoms, 1 bonds, charge +0, radicals 0",
                            "product_text": "Product Sheet: 6 atoms, 6 bonds, charge +0, radicals 0",
                            "cue_text": "Inspect the barrier direction.",
                            "notes_text": "forward barrier (kcal) : 12.5",
                            "summary_text": "Reaction path analysis complete.",
                            "metadata": [{"label": "Workflow", "value": "PATH", "emphasis": True}],
                            "result_bullets": [
                                {"label": "Forward barrier", "value": "12.5000 kcal/mol", "emphasis": True}
                            ],
                        },
                    }
                ],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workbook.chemvas"
            write_document(path, workbook_state, version=2)

            with patch("ui.main_window.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                self.window._load_canvas()

        self.assertEqual(self.window._canvas_sheet_count(), 2)
        self.assertEqual(self.window.canvas_tabs.tabText(0), "Reactant Sheet")
        self.assertEqual(self.window.canvas_tabs.tabText(1), "Product Sheet")
        self.assertEqual(self.window.canvas_tabs.currentIndex(), 1)
        self.assertEqual(len(self.window.canvas.ring_items), 1)

    def test_save_canvas_cancel_keeps_current_path_and_status_message(self) -> None:
        self.window._current_file_path = None
        self.window.statusBar().showMessage("Idle")

        with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
            self.window._save_canvas()

        self.assertIsNone(self.window._current_file_path)
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_save_canvas_reuses_current_path_without_opening_dialog(self) -> None:
        self.window._current_file_path = "/tmp/existing.chemvas"

        with (
            patch.object(self.window.canvas, "save_to_file") as save_mock,
            patch("ui.main_window.QFileDialog.getSaveFileName") as dialog_mock,
        ):
            self.window._save_canvas()

        save_mock.assert_called_once_with("/tmp/existing.chemvas")
        dialog_mock.assert_not_called()
        self.assertEqual(self.window._current_file_path, "/tmp/existing.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Saved: /tmp/existing.chemvas")

    def test_save_canvas_as_updates_current_path_and_status_message(self) -> None:
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        self.window._current_file_path = "/tmp/original.chemvas"

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "renamed"
            saved_path = Path(f"{raw_path}.chemvas")
            with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=(str(raw_path), "")):
                self.window._save_canvas_as()

            self.assertTrue(saved_path.exists())

        self.assertEqual(self.window._current_file_path, str(saved_path))
        self.assertEqual(self.window.statusBar().currentMessage(), f"Saved: {saved_path}")

    def test_save_canvas_as_cancel_keeps_current_path_and_status_message(self) -> None:
        self.window._current_file_path = "/tmp/original.chemvas"
        self.window.statusBar().showMessage("Idle")

        with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
            self.window._save_canvas_as()

        self.assertEqual(self.window._current_file_path, "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_save_canvas_as_failure_warns_and_preserves_current_path(self) -> None:
        self.window._current_file_path = "/tmp/original.chemvas"
        self.window.statusBar().showMessage("Before save as")

        with (
            patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("/tmp/renamed.chemvas", "")),
            patch.object(self.window.canvas, "save_to_file", side_effect=OSError("disk full")) as save_mock,
            patch("ui.main_window.QMessageBox.warning") as warning,
        ):
            self.window._save_canvas_as()

        save_mock.assert_called_once_with("/tmp/renamed.chemvas")
        warning.assert_called_once_with(
            self.window,
            "Save Error",
            "Failed to save file:\ndisk full",
        )
        self.assertEqual(self.window._current_file_path, "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Before save as")

    def test_export_xyz_appends_extension_and_updates_status_message(self) -> None:
        self.window._current_file_path = "/tmp/example.chemvas"

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "exported_structure"
            expected_path = Path(f"{raw_path}.xyz")
            with (
                patch("ui.main_window.QFileDialog.getSaveFileName", return_value=(str(raw_path), "")),
                patch.object(self.window.canvas, "export_xyz") as export_mock,
            ):
                self.window._export_xyz()

        export_mock.assert_called_once_with(str(expected_path))
        self.assertEqual(self.window._current_file_path, "/tmp/example.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), f"Exported XYZ: {expected_path}")

    def test_export_xyz_cancel_keeps_current_path_and_status_message(self) -> None:
        self.window._current_file_path = "/tmp/original.chemvas"
        self.window.statusBar().showMessage("Idle")

        with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
            self.window._export_xyz()

        self.assertEqual(self.window._current_file_path, "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_export_xyz_failure_warns_and_preserves_status_message(self) -> None:
        self.window._current_file_path = "/tmp/original.chemvas"
        self.window.statusBar().showMessage("Before export")

        with (
            patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("/tmp/output.xyz", "")),
            patch.object(self.window.canvas, "export_xyz", side_effect=ValueError("RDKit missing")) as export_mock,
            patch("ui.main_window.QMessageBox.warning") as warning,
        ):
            self.window._export_xyz()

        export_mock.assert_called_once_with("/tmp/output.xyz")
        warning.assert_called_once_with(
            self.window,
            "Export Error",
            "Failed to export XYZ:\nRDKit missing",
        )
        self.assertEqual(self.window._current_file_path, "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Before export")

    def test_load_canvas_cancel_keeps_current_path_and_status_message(self) -> None:
        self.window._current_file_path = "/tmp/original.chemvas"
        self.window.statusBar().showMessage("Idle")

        with patch("ui.main_window.QFileDialog.getOpenFileName", return_value=("", "")):
            self.window._load_canvas()

        self.assertEqual(self.window._current_file_path, "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_save_canvas_failure_warns_and_preserves_current_path(self) -> None:
        self.window._current_file_path = "/tmp/original.chemvas"
        self.window.statusBar().showMessage("Before save")

        with (
            patch.object(self.window.canvas, "save_to_file", side_effect=OSError("disk full")) as save_mock,
            patch("ui.main_window.QMessageBox.warning") as warning,
        ):
            self.window._save_canvas()

        save_mock.assert_called_once_with("/tmp/original.chemvas")
        warning.assert_called_once_with(
            self.window,
            "Save Error",
            "Failed to save file:\ndisk full",
        )
        self.assertEqual(self.window._current_file_path, "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Before save")

    def test_load_canvas_failure_warns_and_preserves_existing_scene(self) -> None:
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        self.window.canvas.add_text_note(QPointF(75.0, 10.0), "Keep me")
        self.window.canvas.last_smiles_input = "CCO"
        self.window.canvas._history = ["keep-history"]
        self.window.canvas._redo_stack = ["keep-redo"]
        self.window._current_file_path = "/tmp/original.chemvas"
        self.window.statusBar().showMessage("Before load")

        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.chemvas"
            invalid_path.write_text(dumps({"state": {}}), encoding="utf-8")

            with (
                patch("ui.main_window.QFileDialog.getOpenFileName", return_value=(str(invalid_path), "")),
                patch("ui.main_window.QMessageBox.warning") as warning,
            ):
                self.window._load_canvas()

        warning.assert_called_once_with(
            self.window,
            "Load Error",
            "Failed to load file:\nInvalid Chemvas file.",
        )
        self.assertEqual(self.window._current_file_path, "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Before load")
        self.assertEqual(len(self.window.canvas.ring_items), 1)
        self.assertEqual(len(self.window.canvas.note_items), 1)
        self.assertEqual(self.window.canvas.last_smiles_input, "CCO")
        self.assertEqual(self.window.canvas._history, ["keep-history"])
        self.assertEqual(self.window.canvas._redo_stack, ["keep-redo"])

    def test_regular_template_preview_reuses_existing_preview_items(self) -> None:
        self._template_handler("Cyclopropane")()
        self.assertTrue(self.window.canvas._template_insert_active)

        self._hover_scene_point(QPointF(-30.0, 0.0))
        self.assertEqual(len(self.window.canvas._template_preview_lines), 3)
        self.assertEqual(len(self.window.canvas._template_preview_dots), 3)
        preview_lines = list(self.window.canvas._template_preview_lines)
        first_line_before = preview_lines[0].line()

        self._hover_scene_point(QPointF(30.0, 20.0))

        self.assertEqual(len(self.window.canvas._template_preview_lines), 3)
        self.assertEqual(len(self.window.canvas._template_preview_dots), 3)
        self.assertIs(self.window.canvas._template_preview_lines[0], preview_lines[0])
        self.assertNotEqual(self.window.canvas._template_preview_lines[0].line(), first_line_before)

    def test_large_regular_template_preview_uses_requested_ring_size(self) -> None:
        for label, ring_size in (("Cycloheptane", 7), ("Cyclooctane", 8)):
            with self.subTest(label=label):
                self._template_handler(label)()
                self.assertTrue(self.window.canvas._template_insert_active)
                self.assertEqual(self.window.canvas._template_ring_size, ring_size)
                self.assertEqual(self.window.canvas._template_ring_style, "regular")

                self._hover_scene_point(QPointF(20.0, 20.0))

                self.assertEqual(len(self.window.canvas._template_preview_lines), ring_size)
                self.assertEqual(len(self.window.canvas._template_preview_dots), ring_size)
                self.window.canvas._cancel_template_insert()

    def test_regular_template_commit_on_bond_merges_existing_endpoints(self) -> None:
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        before_atom_count = len(self.window.canvas.model.atoms)
        before_bond_count = sum(1 for bond in self.window.canvas.model.bonds if bond is not None)

        self._template_handler("Cyclobutane")()
        self._hover_scene_point(QPointF(0.0, 0.0))
        self.assertEqual(len(self.window.canvas._template_preview_lines), 4)

        self._click_scene_point(QPointF(0.0, 0.0))

        self.assertFalse(self.window.canvas._template_insert_active)
        self.assertEqual(self.window.canvas._template_preview_lines, [])
        self.assertEqual(self.window.canvas._template_preview_dots, [])
        self.assertEqual(len(self.window.canvas.model.atoms), before_atom_count + 2)
        self.assertEqual(
            sum(1 for bond in self.window.canvas.model.bonds if bond is not None),
            before_bond_count + 3,
        )

    def test_chair_template_commit_on_ring_bond_places_new_atoms_outside_existing_ring(self) -> None:
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        ring_item = self.window.canvas.ring_items[0]
        original_polygon = ring_item.polygon()
        ring_atom_ids = ring_item.data(2)
        self.assertIsInstance(ring_atom_ids, list)
        original_atom_ids = set(self.window.canvas.model.atoms)
        bond_id = self.window.canvas._bond_id_between(ring_atom_ids[0], ring_atom_ids[1])
        self.assertIsNotNone(bond_id)
        atom_a = self.window.canvas.model.atoms[ring_atom_ids[0]]
        atom_b = self.window.canvas.model.atoms[ring_atom_ids[1]]
        midpoint = QPointF((atom_a.x + atom_b.x) / 2.0, (atom_a.y + atom_b.y) / 2.0)

        self._template_handler("Cyclohexane (Chair)")()
        self._hover_scene_point(midpoint)
        self.assertEqual(len(self.window.canvas._template_preview_lines), 6)

        self._click_scene_point(midpoint)

        self.assertFalse(self.window.canvas._template_insert_active)
        new_atom_ids = set(self.window.canvas.model.atoms) - original_atom_ids
        self.assertEqual(len(new_atom_ids), 4)
        for atom_id in new_atom_ids:
            atom = self.window.canvas.model.atoms[atom_id]
            self.assertFalse(
                original_polygon.containsPoint(QPointF(atom.x, atom.y), Qt.FillRule.WindingFill),
            )

    def test_escape_cancels_template_insert_and_prevents_commit(self) -> None:
        self._template_handler("Cyclopropane")()
        self._hover_scene_point(QPointF(25.0, 10.0))
        preview_items = list(self.window.canvas._template_preview_items)

        self.assertTrue(self.window.canvas._template_insert_active)
        self.assertGreater(len(preview_items), 0)

        self._press_key(Qt.Key.Key_Escape)
        atom_count_before = len(self.window.canvas.model.atoms)
        bond_count_before = sum(1 for bond in self.window.canvas.model.bonds if bond is not None)
        self.window.canvas._commit_template_insert(QPointF(25.0, 10.0))

        self.assertFalse(self.window.canvas._template_insert_active)
        self.assertIsNone(self.window.canvas._template_ring_size)
        self.assertIsNone(self.window.canvas._template_ring_style)
        self.assertEqual(self.window.canvas._template_preview_items, [])
        self.assertEqual(self.window.canvas._template_preview_lines, [])
        self.assertEqual(self.window.canvas._template_preview_dots, [])
        self.assertEqual(len(self.window.canvas.model.atoms), atom_count_before)
        self.assertEqual(
            sum(1 for bond in self.window.canvas.model.bonds if bond is not None),
            bond_count_before,
        )
        self.assertTrue(all(item.scene() is None for item in preview_items))

    def test_begin_smiles_insert_cancels_active_template_preview(self) -> None:
        self._template_handler("Cyclobutane")()
        self._hover_scene_point(QPointF(15.0, 15.0))
        preview_items = list(self.window.canvas._template_preview_items)

        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(self.window.canvas.rdkit, "smiles_to_2d", return_value=model):
            self.window.canvas.begin_smiles_insert("CC")

        self.assertFalse(self.window.canvas._template_insert_active)
        self.assertEqual(self.window.canvas._template_preview_items, [])
        self.assertEqual(self.window.canvas._template_preview_lines, [])
        self.assertEqual(self.window.canvas._template_preview_dots, [])
        self.assertTrue(all(item.scene() is None for item in preview_items))
        self.assertTrue(self.window.canvas._smiles_insert_active)
        self.assertEqual(self.window.canvas._smiles_preview_smiles, "CC")
        self.assertGreater(len(self.window.canvas._smiles_preview_items), 0)

    def test_begin_template_insert_cancels_active_smiles_preview(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(self.window.canvas.rdkit, "smiles_to_2d", return_value=model):
            self.window.canvas.begin_smiles_insert("CC")

        self.assertTrue(self.window.canvas._smiles_insert_active)
        smiles_preview_items = list(self.window.canvas._smiles_preview_items)

        self._template_handler("Cyclobutane")()

        self.assertFalse(self.window.canvas._smiles_insert_active)
        self.assertIsNone(self.window.canvas._smiles_preview_model)
        self.assertIsNone(self.window.canvas._smiles_preview_smiles)
        self.assertIsNone(self.window.canvas._smiles_preview_center)
        self.assertEqual(self.window.canvas._smiles_preview_items, [])
        self.assertTrue(all(item.scene() is None for item in smiles_preview_items))
        self.assertTrue(self.window.canvas._template_insert_active)
        self.assertEqual(self.window.canvas._template_ring_size, 4)
        self.assertEqual(self.window.canvas._template_ring_style, "regular")
        self.assertGreater(len(self.window.canvas._template_preview_items), 0)
        self.assertGreater(len(self.window.canvas._template_preview_lines), 0)
        self.assertGreater(len(self.window.canvas._template_preview_dots), 0)

    def test_smiles_preview_reuses_existing_preview_items(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(self.window.canvas.rdkit, "smiles_to_2d", return_value=model):
            self.window.canvas.begin_smiles_insert("CC")

        self.assertTrue(self.window.canvas._smiles_insert_active)
        self._hover_scene_point(QPointF(-30.0, 0.0))
        self.assertEqual(len(self.window.canvas._smiles_preview_bond_items[0]), 1)
        preview_line = self.window.canvas._smiles_preview_bond_items[0][0]
        preview_rect = self.window.canvas._smiles_preview_atom_items[left].rect()
        preview_atom = self.window.canvas._smiles_preview_atom_items[left]

        self._hover_scene_point(QPointF(30.0, 20.0))

        self.assertIs(self.window.canvas._smiles_preview_bond_items[0][0], preview_line)
        self.assertIs(self.window.canvas._smiles_preview_atom_items[left], preview_atom)
        self.assertNotEqual(self.window.canvas._smiles_preview_atom_items[left].rect(), preview_rect)

    def test_clear_scene_resets_active_smiles_insert_state(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(self.window.canvas.rdkit, "smiles_to_2d", return_value=model):
            self.window.canvas.begin_smiles_insert("CC")

        self.assertTrue(self.window.canvas._smiles_insert_active)
        self.assertIsNotNone(self.window.canvas._smiles_preview_model)
        self.assertGreater(len(self.window.canvas._smiles_preview_items), 0)

        self.window.canvas.clear_scene()

        self.assertFalse(self.window.canvas._smiles_insert_active)
        self.assertIsNone(self.window.canvas._smiles_preview_model)
        self.assertIsNone(self.window.canvas._smiles_preview_smiles)
        self.assertIsNone(self.window.canvas._smiles_preview_center)
        self.assertEqual(self.window.canvas._smiles_preview_items, [])

    def test_smiles_insert_commit_adds_atoms_bonds_and_clears_preview(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("N", 10.0, 0.0)
        model.atoms[right].color = "#336699"
        model.atoms[right].explicit_label = True
        model.add_bond(left, right, 2)
        model.bonds[0].style = "double"
        model.bonds[0].color = "#123456"

        with patch.object(self.window.canvas.rdkit, "smiles_to_2d", return_value=model):
            self.window.canvas.begin_smiles_insert("CN")

        self.assertTrue(self.window.canvas._smiles_insert_active)
        preview_items = list(self.window.canvas._smiles_preview_items)
        self.window.canvas._commit_smiles_insert(QPointF(40.0, 10.0))

        self.assertFalse(self.window.canvas._smiles_insert_active)
        self.assertEqual(len(self.window.canvas.model.atoms), 2)
        self.assertEqual(sum(1 for bond in self.window.canvas.model.bonds if bond is not None), 1)
        atom0 = self.window.canvas.model.atoms[0]
        atom1 = self.window.canvas.model.atoms[1]
        self.assertEqual((atom0.x, atom0.y), (30.0, 10.0))
        self.assertEqual((atom1.x, atom1.y), (50.0, 10.0))
        self.assertEqual(atom1.color, "#336699")
        self.assertIn(1, self.window.canvas.atom_items)
        self.assertEqual(self.window.canvas.atom_items[1].toPlainText(), "N")
        self.assertEqual(self.window.canvas.last_smiles_input, "CN")
        self.assertEqual(self.window.canvas._smiles_preview_items, [])
        self.assertTrue(all(item.scene() is None for item in preview_items))

    def test_escape_cancels_smiles_insert_and_prevents_commit(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(self.window.canvas.rdkit, "smiles_to_2d", return_value=model):
            self.window.canvas.begin_smiles_insert("CC")

        preview_items = list(self.window.canvas._smiles_preview_items)
        self.assertTrue(self.window.canvas._smiles_insert_active)

        self._press_key(Qt.Key.Key_Escape)
        self.window.canvas._commit_smiles_insert(QPointF(20.0, 0.0))

        self.assertFalse(self.window.canvas._smiles_insert_active)
        self.assertIsNone(self.window.canvas._smiles_preview_model)
        self.assertIsNone(self.window.canvas._smiles_preview_smiles)
        self.assertIsNone(self.window.canvas._smiles_preview_center)
        self.assertEqual(self.window.canvas._smiles_preview_items, [])
        self.assertEqual(len(self.window.canvas.model.atoms), 0)
        self.assertEqual(len(self.window.canvas.model.bonds), 0)
        self.assertTrue(all(item.scene() is None for item in preview_items))

    def test_begin_smiles_insert_invalid_smiles_warns_without_entering_mode(self) -> None:
        self.window.canvas.rdkit.last_error = "bad smiles"

        with (
            patch.object(self.window.canvas.rdkit, "smiles_to_2d", return_value=None),
            patch("ui.insert_controller.QMessageBox.warning") as warning,
        ):
            self.window.canvas.begin_smiles_insert("not-a-smiles")

        warning.assert_called_once_with(self.window.canvas, "SMILES Error", "bad smiles")
        self.assertFalse(self.window.canvas._smiles_insert_active)
        self.assertIsNone(self.window.canvas._smiles_preview_model)
        self.assertEqual(self.window.canvas._smiles_preview_items, [])

    def test_canvas_export_xyz_uses_selected_structure_submodel(self) -> None:
        left = self.window.canvas.add_atom("C", -20.0, 0.0)
        middle = self.window.canvas.add_atom("C", 0.0, 0.0)
        right = self.window.canvas.add_atom("O", 20.0, 0.0)
        self.window.canvas.add_bond(left, middle, 1)
        self.window.canvas.add_bond(middle, right, 1)
        self.window.canvas.model.bonds[0].style = "bold_in"
        self.window.canvas._add_bond_graphics(0)
        self.window.canvas._add_bond_graphics(1)

        bond_item = self.window.canvas.bond_items[0][0]
        bond_item.setSelected(True)

        captured = {}

        def _capture_export(model, atom_annotations=None):
            captured["model"] = model
            captured["atom_annotations"] = atom_annotations
            return "2\nChemvas XYZ export\nC 0.000000 0.000000 0.000000\nC 1.000000 0.000000 0.000000\n"

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "selected.xyz"
            with patch.object(self.window.canvas.rdkit, "model_to_xyz_block", side_effect=_capture_export):
                self.window.canvas.export_xyz(str(export_path))
            xyz_text = export_path.read_text(encoding="utf-8")

        exported_model = captured["model"]
        self.assertEqual(len(exported_model.atoms), 2)
        self.assertEqual(len(exported_model.bonds), 1)
        self.assertEqual(exported_model.bonds[0].style, "bold_in")
        self.assertEqual(captured["atom_annotations"], {})
        self.assertIn("Chemvas XYZ export", xyz_text)

    def test_canvas_export_xyz_passes_charge_and_radical_annotations(self) -> None:
        atom_id = self.window.canvas.add_atom("C", 0.0, 0.0)
        self.window.canvas.add_mark_for_atom(atom_id, QPointF(10.0, -10.0), kind="plus", record=False)
        self.window.canvas.add_mark_for_atom(atom_id, QPointF(12.0, -12.0), kind="radical", record=False)

        captured = {}

        def _capture_export(model, atom_annotations=None):
            captured["annotations"] = atom_annotations
            return "1\nChemvas XYZ export\nC 0.000000 0.000000 0.000000\n"

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "charged.xyz"
            with patch.object(self.window.canvas.rdkit, "model_to_xyz_block", side_effect=_capture_export):
                self.window.canvas.export_xyz(str(export_path))

        self.assertEqual(
            captured["annotations"],
            {0: {"formal_charge": 1, "radical_electrons": 1}},
        )

    def test_build_3d_conversion_payload_ignores_scene_only_items_in_mixed_selection(self) -> None:
        left = self.window.canvas.add_atom("C", -20.0, 0.0)
        middle = self.window.canvas.add_atom("C", 0.0, 0.0)
        right = self.window.canvas.add_atom("O", 20.0, 0.0)
        self.window.canvas.add_bond(left, middle, 1)
        self.window.canvas.add_bond(middle, right, 1)
        self.window.canvas._add_bond_graphics(0)
        self.window.canvas._add_bond_graphics(1)
        arrow = self.window.canvas.add_arrow(QPointF(-40.0, -20.0), QPointF(40.0, -20.0), "reaction")
        ts_bracket = self.window.canvas.add_ts_bracket_from_points(QPointF(-8.0, -28.0), QPointF(8.0, 28.0))
        note = self.window.canvas.add_text_note(QPointF(55.0, 10.0), "Scheme")

        self.window.canvas.scene().clearSelection()
        self.window.canvas.bond_items[0][0].setSelected(True)
        arrow.setSelected(True)
        ts_bracket.setSelected(True)
        note.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

        export_model, atom_annotations = self.window.canvas.build_3d_conversion_payload()

        self.assertEqual(len(export_model.atoms), 2)
        self.assertEqual(len(export_model.bonds), 1)
        self.assertEqual(atom_annotations, {})

    def test_build_3d_conversion_payload_uses_atom_bound_mark_selection(self) -> None:
        left = self.window.canvas.add_atom("N", -20.0, 0.0)
        self.window.canvas.add_atom("O", 20.0, 0.0)
        mark = self.window.canvas.add_mark_for_atom(left, QPointF(-12.0, -10.0), kind="plus", record=False)
        arrow = self.window.canvas.add_arrow(QPointF(-40.0, -20.0), QPointF(40.0, -20.0), "reaction")

        self.window.canvas.scene().clearSelection()
        mark.setSelected(True)
        arrow.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

        export_model, atom_annotations = self.window.canvas.build_3d_conversion_payload()

        self.assertEqual(len(export_model.atoms), 1)
        self.assertEqual(len(export_model.bonds), 0)
        self.assertEqual(atom_annotations, {0: {"formal_charge": 1}})

    def test_preview_panel_updates_from_canvas_structure(self) -> None:
        atom_id = self.window.canvas.add_atom("N", 0.0, 0.0)
        self.window.canvas.add_mark_for_atom(atom_id, QPointF(10.0, -10.0), kind="plus", record=False)

        scene = Molecule3DScene(
            atoms=(
                Molecule3DAtom("N", 0.0, 0.0, 0.0),
                Molecule3DAtom("H", 0.8, 0.0, 0.4),
            ),
            bonds=(Molecule3DBond(0, 1, 1),),
        )

        with (
            patch.object(self.window.canvas.rdkit, "compute_props", return_value=("NH4", 18.04, "[NH4+]")),
            patch.object(self.window.canvas.rdkit, "model_to_3d_scene", return_value=scene),
        ):
            self.window.preview_3d.refresh_from_canvas(self.window.canvas)
            self.app.processEvents()
            QTest.qWait(150)
            self.app.processEvents()

        self.assertIsNotNone(self.window.preview_3d._scene)
        self.assertEqual(self.window.preview_3d._formula_text, "NH4")
        self.assertEqual(self.window.preview_3d._mw_text, "18.04")
        self.assertIs(self.window.panel_splitter.widget(0), self.window.preview_3d)
        self.assertEqual(self.window.panel_splitter.count(), 1)
        self.assertFalse(
            bool(
                self.window.panel_dock.features()
                & self.window.panel_dock.DockWidgetFeature.DockWidgetClosable
            )
        )

    def test_preview_panel_uses_selected_structure_when_scene_only_items_are_also_selected(self) -> None:
        left = self.window.canvas.add_atom("C", -20.0, 0.0)
        middle = self.window.canvas.add_atom("C", 0.0, 0.0)
        right = self.window.canvas.add_atom("O", 20.0, 0.0)
        self.window.canvas.add_bond(left, middle, 1)
        self.window.canvas.add_bond(middle, right, 1)
        self.window.canvas._add_bond_graphics(0)
        self.window.canvas._add_bond_graphics(1)
        arrow = self.window.canvas.add_arrow(QPointF(-40.0, -20.0), QPointF(40.0, -20.0), "reaction")
        ts_bracket = self.window.canvas.add_ts_bracket_from_points(QPointF(-8.0, -28.0), QPointF(8.0, 28.0))
        note = self.window.canvas.add_text_note(QPointF(55.0, 10.0), "Scheme")

        self.window.canvas.scene().clearSelection()
        self.window.canvas.bond_items[0][0].setSelected(True)
        arrow.setSelected(True)
        ts_bracket.setSelected(True)
        note.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

        scene = Molecule3DScene(
            atoms=(
                Molecule3DAtom("C", 0.0, 0.0, 0.0),
                Molecule3DAtom("C", 1.0, 0.0, 0.0),
            ),
            bonds=(Molecule3DBond(0, 1, 1),),
        )

        with patch.object(self.window.preview_3d._rdkit, "model_to_3d_scene", return_value=scene) as mocked:
            self.window.preview_3d.refresh_from_canvas(self.window.canvas)
            self.app.processEvents()
            QTest.qWait(150)
            self.app.processEvents()

        called_model = mocked.call_args.args[0]
        self.assertEqual(len(called_model.atoms), 2)
        self.assertEqual(len(called_model.bonds), 1)

    def test_preview_panel_hint_font_is_zoom_independent(self) -> None:
        initial_size = self.window.preview_3d._overlay_font().pixelSize()

        self.window.preview_3d._zoom = 0.4
        zoomed_out_size = self.window.preview_3d._overlay_font().pixelSize()

        self.window.preview_3d._zoom = 2.8
        zoomed_in_size = self.window.preview_3d._overlay_font().pixelSize()

        self.assertEqual(initial_size, 12)
        self.assertEqual(zoomed_out_size, initial_size)
        self.assertEqual(zoomed_in_size, initial_size)

    def test_arrow_default_preset_matches_legacy_acs_values(self) -> None:
        self.window.canvas.set_arrow_line_width(4.0)
        self.window.canvas.set_arrow_head_scale(0.6)

        self.window._set_arrow_preset("Default")
        self.assertAlmostEqual(self.window.canvas.get_arrow_line_width(), 1.2)
        self.assertAlmostEqual(self.window.canvas.get_arrow_head_scale(), 0.3)

        self.window.canvas.set_arrow_line_width(4.0)
        self.window.canvas.set_arrow_head_scale(0.6)
        self.window._set_arrow_preset("ACS")
        self.assertAlmostEqual(self.window.canvas.get_arrow_line_width(), 1.2)
        self.assertAlmostEqual(self.window.canvas.get_arrow_head_scale(), 0.3)


if __name__ == "__main__":
    unittest.main()
