import os
import sys
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


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.document_io import read_document
    from core.model import MoleculeModel
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
        self.window.raise_()
        self.window.activateWindow()
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

    def test_save_canvas_appends_extension_and_writes_document_payload(self) -> None:
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        self.window.canvas.add_text_note(QPointF(60.0, 10.0), "Scheme")
        self.window.canvas.add_mark(QPointF(20.0, 20.0), kind="plus", atom_id=0, record=False)
        self.window.canvas.add_arrow(QPointF(-40.0, -20.0), QPointF(40.0, -20.0), "reaction")
        self.window.canvas.last_smiles_input = "CCO"

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "example"
            saved_path = Path(f"{raw_path}.ldraw")
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
            path = Path(temp_dir) / "roundtrip.ldraw"
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

    def test_save_canvas_cancel_keeps_current_path_and_status_message(self) -> None:
        self.window._current_file_path = None
        self.window.statusBar().showMessage("Idle")

        with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
            self.window._save_canvas()

        self.assertIsNone(self.window._current_file_path)
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_load_canvas_cancel_keeps_current_path_and_status_message(self) -> None:
        self.window._current_file_path = "/tmp/original.ldraw"
        self.window.statusBar().showMessage("Idle")

        with patch("ui.main_window.QFileDialog.getOpenFileName", return_value=("", "")):
            self.window._load_canvas()

        self.assertEqual(self.window._current_file_path, "/tmp/original.ldraw")
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_save_canvas_failure_warns_and_preserves_current_path(self) -> None:
        self.window._current_file_path = "/tmp/original.ldraw"
        self.window.statusBar().showMessage("Before save")

        with (
            patch.object(self.window.canvas, "save_to_file", side_effect=OSError("disk full")) as save_mock,
            patch("ui.main_window.QMessageBox.warning") as warning,
        ):
            self.window._save_canvas()

        save_mock.assert_called_once_with("/tmp/original.ldraw")
        warning.assert_called_once_with(
            self.window,
            "Save Error",
            "Failed to save file:\ndisk full",
        )
        self.assertEqual(self.window._current_file_path, "/tmp/original.ldraw")
        self.assertEqual(self.window.statusBar().currentMessage(), "Before save")

    def test_load_canvas_failure_warns_and_preserves_existing_scene(self) -> None:
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        self.window.canvas.add_text_note(QPointF(75.0, 10.0), "Keep me")
        self.window.canvas.last_smiles_input = "CCO"
        self.window.canvas._history = ["keep-history"]
        self.window.canvas._redo_stack = ["keep-redo"]
        self.window._current_file_path = "/tmp/original.ldraw"
        self.window.statusBar().showMessage("Before load")

        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.ldraw"
            invalid_path.write_text(dumps({"state": {}}), encoding="utf-8")

            with (
                patch("ui.main_window.QFileDialog.getOpenFileName", return_value=(str(invalid_path), "")),
                patch("ui.main_window.QMessageBox.warning") as warning,
            ):
                self.window._load_canvas()

        warning.assert_called_once_with(
            self.window,
            "Load Error",
            "Failed to load file:\nInvalid LiteDraw file.",
        )
        self.assertEqual(self.window._current_file_path, "/tmp/original.ldraw")
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
            patch("ui.canvas_view.QMessageBox.warning") as warning,
        ):
            self.window.canvas.begin_smiles_insert("not-a-smiles")

        warning.assert_called_once_with(self.window.canvas, "SMILES Error", "bad smiles")
        self.assertFalse(self.window.canvas._smiles_insert_active)
        self.assertIsNone(self.window.canvas._smiles_preview_model)
        self.assertEqual(self.window.canvas._smiles_preview_items, [])


if __name__ == "__main__":
    unittest.main()
