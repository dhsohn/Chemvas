import os
import sys
import unittest
from pathlib import Path

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
    from ui.main_window import MainWindow


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI smoke tests")
class GuiShortcutSmokeTest(unittest.TestCase):
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

    def _press_key(self, key: int, modifiers=None) -> None:
        if modifiers is None:
            modifiers = Qt.KeyboardModifier.NoModifier
        QTest.keyClick(self.window.canvas, key, modifiers)
        self.app.processEvents()
        QTest.qWait(10)

    def _select_atom_ids(self, *atom_ids: int) -> None:
        self.window.canvas.scene().clearSelection()
        for atom_id in atom_ids:
            item = self.window.canvas.atom_items.get(atom_id) or self.window.canvas.atom_dots.get(atom_id)
            self.assertIsNotNone(item)
            item.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

    def _select_items(self, *items) -> None:
        self.window.canvas.scene().clearSelection()
        for item in items:
            self.assertIsNotNone(item)
            item.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

    def test_generic_tool_shortcuts_switch_active_tool(self) -> None:
        self._press_key(Qt.Key.Key_X)
        self.assertEqual(self.window.canvas.tools.active.name, "bond")
        self.assertEqual(self.window.canvas.active_bond_style, "single")
        self.assertEqual(self.window.canvas.active_bond_order, 1)

        self._press_key(Qt.Key.Key_T)
        self.assertEqual(self.window.canvas.tools.active.name, "text")

        self._press_key(Qt.Key.Key_E)
        self.assertEqual(self.window.canvas.tools.active.name, "arrow")

        self._press_key(Qt.Key.Key_J)
        self.assertEqual(self.window.canvas.tools.active.name, "benzene")

        self._press_key(Qt.Key.Key_G, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.window.canvas.tools.active.name, "orbital")

        self._press_key(Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(self.window.canvas.tools.active.name, "perspective")

        self._press_key(Qt.Key.Key_Space)
        self.assertEqual(self.window.canvas.tools.active.name, "select")

    def test_legacy_tool_shortcuts_do_not_switch_active_tool(self) -> None:
        self.window.canvas.set_tool("text")

        self._press_key(Qt.Key.Key_V)
        self.assertEqual(self.window.canvas.tools.active.name, "text")

        self._press_key(Qt.Key.Key_B)
        self.assertEqual(self.window.canvas.tools.active.name, "text")

        self._press_key(Qt.Key.Key_R)
        self.assertEqual(self.window.canvas.tools.active.name, "text")

        self._press_key(Qt.Key.Key_A)
        self.assertEqual(self.window.canvas.tools.active.name, "text")

        self._press_key(Qt.Key.Key_O)
        self.assertEqual(self.window.canvas.tools.active.name, "text")

    def test_perspective_tool_keeps_selection_drag_mode(self) -> None:
        self.window.canvas.set_tool("perspective")
        self.assertEqual(
            self.window.canvas.dragMode(),
            self.window.canvas.DragMode.RubberBandDrag,
        )

    def test_atom_hotkeys_apply_label_mark_and_sprout_bond(self) -> None:
        atom_id = self.window.canvas.add_atom("C", 0.0, 0.0)
        atom_point = QPointF(0.0, 0.0)
        self._hover_scene_point(atom_point)

        self._press_key(Qt.Key.Key_N)
        self.assertEqual(self.window.canvas.model.atoms[atom_id].element, "N")

        self._press_key(Qt.Key.Key_Plus)
        marks = self.window.canvas._marks_by_atom.get(atom_id, [])
        self.assertEqual(len(marks), 1)
        self.assertEqual((marks[0].data(1) or {}).get("kind"), "plus")

        initial_bond_count = sum(1 for bond in self.window.canvas.model.bonds if bond is not None)
        self._press_key(Qt.Key.Key_1)
        bond_count = sum(1 for bond in self.window.canvas.model.bonds if bond is not None)
        self.assertGreater(bond_count, initial_bond_count)

    def test_bond_hotkeys_modify_hovered_bond(self) -> None:
        start = QPointF(-40.0, 0.0)
        end = QPointF(40.0, 0.0)
        self.window.canvas.add_bond_from_points(start, end)
        bond_id = next(i for i, bond in enumerate(self.window.canvas.model.bonds) if bond is not None)
        bond = self.window.canvas.model.bonds[bond_id]
        self.assertIsNotNone(bond)
        midpoint = QPointF(0.0, 0.0)
        self._hover_scene_point(midpoint)

        self._press_key(Qt.Key.Key_2)
        bond = self.window.canvas.model.bonds[bond_id]
        self.assertEqual(bond.order, 2)
        self.assertEqual(bond.style, "double")

        self._press_key(Qt.Key.Key_B, Qt.KeyboardModifier.ShiftModifier)
        bond = self.window.canvas.model.bonds[bond_id]
        self.assertEqual(bond.order, 2)
        self.assertEqual(bond.style, "bold_in")

        self._press_key(Qt.Key.Key_H, Qt.KeyboardModifier.ShiftModifier)
        bond = self.window.canvas.model.bonds[bond_id]
        self.assertEqual(bond.order, 1)
        self.assertEqual(bond.style, "hash")

        ring_count_before = len(self.window.canvas.ring_items)
        self._press_key(Qt.Key.Key_A)
        self.assertEqual(self.window.canvas.tools.active.name, "bond")
        self.assertGreater(len(self.window.canvas.ring_items), ring_count_before)

    def test_color_preset_preserves_ring_fill_on_selected_ring(self) -> None:
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        ring_item = self.window.canvas.ring_items[0]
        ring_atom_ids = ring_item.data(2)

        self.window.canvas.scene().clearSelection()
        ring_item.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

        fill_color = "#c77c00"
        stroke_color = "#1f5eff"
        self.window._apply_ring_fill_preset(fill_color)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(ring_item.brush().color().name(), fill_color)

        self.window._apply_color_preset(stroke_color)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(ring_item.brush().color().name(), fill_color)
        self.assertIsInstance(ring_atom_ids, list)
        for atom_id in ring_atom_ids:
            self.assertEqual(self.window.canvas.model.atoms[atom_id].color, stroke_color)

    def test_object_shortcuts_flip_selected_structures_in_place(self) -> None:
        left_a = self.window.canvas.add_atom("C", -60.0, 0.0)
        right_a = self.window.canvas.add_atom("O", -20.0, 20.0)
        self.window.canvas.add_bond(left_a, right_a)

        left_b = self.window.canvas.add_atom("N", 40.0, 10.0)
        right_b = self.window.canvas.add_atom("S", 80.0, 30.0)
        self.window.canvas.add_bond(left_b, right_b)

        untouched_left = self.window.canvas.add_atom("F", 140.0, -10.0)
        untouched_right = self.window.canvas.add_atom("Cl", 180.0, 10.0)
        self.window.canvas.add_bond(untouched_left, untouched_right)

        self._select_atom_ids(left_a, right_a, left_b, right_b)

        self._press_key(Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertAlmostEqual(self.window.canvas.model.atoms[left_a].x, -20.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[right_a].x, -60.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[left_a].y, 0.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[right_a].y, 20.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[left_b].x, 80.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[right_b].x, 40.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[left_b].y, 10.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[right_b].y, 30.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[untouched_left].x, 140.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[untouched_right].x, 180.0)

        self._press_key(Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertAlmostEqual(self.window.canvas.model.atoms[left_a].x, -20.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[right_a].x, -60.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[left_a].y, 20.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[right_a].y, 0.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[left_b].x, 80.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[right_b].x, 40.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[left_b].y, 30.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[right_b].y, 10.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[untouched_left].x, 140.0)
        self.assertAlmostEqual(self.window.canvas.model.atoms[untouched_right].x, 180.0)

    def test_object_shortcuts_flip_selected_arrow(self) -> None:
        arrow = self.window.canvas.add_arrow(QPointF(-40.0, 0.0), QPointF(20.0, 20.0), "arrow")
        self._select_items(arrow)

        self._press_key(Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        data = arrow.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.assertAlmostEqual(start.x(), 20.0)
        self.assertAlmostEqual(start.y(), 0.0)
        self.assertAlmostEqual(end.x(), -40.0)
        self.assertAlmostEqual(end.y(), 20.0)

        self._press_key(Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        data = arrow.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.assertAlmostEqual(start.x(), 20.0)
        self.assertAlmostEqual(start.y(), 20.0)
        self.assertAlmostEqual(end.x(), -40.0)
        self.assertAlmostEqual(end.y(), 0.0)

    def test_perspective_rotation_without_axis_hint_uses_rigid_mode(self) -> None:
        left_id = self.window.canvas.add_atom("C", -80.0, 0.0)
        center_id = self.window.canvas.add_atom("C", 0.0, 0.0)
        right_id = self.window.canvas.add_atom("C", 80.0, 0.0)
        self.window.canvas.add_bond(left_id, center_id)
        self.window.canvas.add_bond(center_id, right_id)
        self.window.canvas._render_model()

        self._select_atom_ids(left_id, center_id, right_id)

        rotating = self.window.canvas.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 20.0),
        )

        self.assertTrue(rotating)
        self.assertEqual(self.window.canvas._rotation_mode, "rigid")
        self.assertEqual(self.window.canvas.rotation_atom_ids, {left_id, center_id, right_id})
        self.window.canvas.end_selection_3d_rotation()

    def test_perspective_rotation_without_axis_hint_uses_rigid_mode_for_partial_selection(self) -> None:
        left_id = self.window.canvas.add_atom("C", -80.0, 0.0)
        center_id = self.window.canvas.add_atom("C", 0.0, 0.0)
        right_id = self.window.canvas.add_atom("C", 80.0, 0.0)
        self.window.canvas.add_bond(left_id, center_id)
        self.window.canvas.add_bond(center_id, right_id)
        self.window.canvas._render_model()

        self._select_atom_ids(center_id, right_id)

        rotating = self.window.canvas.begin_selection_3d_rotation(
            press_pos=QPointF(40.0, 20.0),
        )

        self.assertTrue(rotating)
        self.assertEqual(self.window.canvas._rotation_mode, "rigid")
        self.assertEqual(self.window.canvas.rotation_atom_ids, {center_id, right_id})
        self.window.canvas.end_selection_3d_rotation()

    def test_perspective_rigid_rotation_uses_bounding_box_center(self) -> None:
        left_id = self.window.canvas.add_atom("C", 0.0, 0.0)
        center_id = self.window.canvas.add_atom("C", 10.0, 20.0)
        right_id = self.window.canvas.add_atom("C", 100.0, 0.0)
        self.window.canvas.add_bond(left_id, center_id)
        self.window.canvas.add_bond(center_id, right_id)
        self.window.canvas._render_model()

        self._select_atom_ids(left_id, center_id, right_id)

        rotating = self.window.canvas.begin_selection_3d_rotation(
            press_pos=QPointF(40.0, 10.0),
        )

        self.assertTrue(rotating)
        self.assertEqual(self.window.canvas._rotation_mode, "rigid")
        self.assertEqual(self.window.canvas.rotation_center_3d, (50.0, 10.0, 0.0))
        self.window.canvas.end_selection_3d_rotation()

    def test_perspective_diagonal_rigid_rotation_preserves_average_bond_length(self) -> None:
        left_id = self.window.canvas.add_atom("C", -80.0, 0.0)
        center_id = self.window.canvas.add_atom("C", 0.0, 0.0)
        right_id = self.window.canvas.add_atom("C", 80.0, 0.0)
        self.window.canvas.add_bond(left_id, center_id)
        self.window.canvas.add_bond(center_id, right_id)
        self.window.canvas._render_model()

        atom_ids = {left_id, center_id, right_id}
        base_coords = {
            atom_id: (self.window.canvas.model.atoms[atom_id].x, self.window.canvas.model.atoms[atom_id].y, 0.0)
            for atom_id in atom_ids
        }
        base_avg = self.window.canvas._average_bond_length_for_atoms(atom_ids, base_coords)
        self.assertIsNotNone(base_avg)

        self._select_atom_ids(left_id, center_id, right_id)
        rotating = self.window.canvas.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 20.0),
        )
        self.assertTrue(rotating)

        self.window.canvas.update_selection_3d_rotation(200.0, 200.0)

        after_coords = {
            atom_id: (self.window.canvas.model.atoms[atom_id].x, self.window.canvas.model.atoms[atom_id].y, 0.0)
            for atom_id in atom_ids
        }
        after_avg = self.window.canvas._average_bond_length_for_atoms(atom_ids, after_coords)
        self.assertIsNotNone(after_avg)
        self.assertAlmostEqual(after_avg, base_avg, delta=0.05)
        self.window.canvas.end_selection_3d_rotation()

    def test_perspective_rotation_on_selected_bond_chooses_clicked_side(self) -> None:
        left_id = self.window.canvas.add_atom("C", -80.0, 0.0)
        center_id = self.window.canvas.add_atom("C", 0.0, 0.0)
        right_id = self.window.canvas.add_atom("C", 80.0, 0.0)
        self.window.canvas.add_bond(left_id, center_id)
        bond_id = self.window.canvas.add_bond(center_id, right_id)
        self.window.canvas._render_model()

        self._select_atom_ids(left_id, center_id, right_id)

        rotating = self.window.canvas.begin_selection_3d_rotation(
            axis_hint=bond_id,
            press_pos=QPointF(65.0, 0.0),
        )

        self.assertTrue(rotating)
        self.assertEqual(self.window.canvas._rotation_mode, "bond")
        self.assertEqual(self.window.canvas.rotation_atom_ids, {right_id})
        self.window.canvas.end_selection_3d_rotation()


if __name__ == "__main__":
    unittest.main()
