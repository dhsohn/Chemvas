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

    def test_clicking_near_carbon_endpoint_prefers_atom_selection_over_bond(self) -> None:
        self.window.canvas.set_tool("select")
        self.window.canvas.add_bond_from_points(QPointF(0.0, 0.0), QPointF(20.0, 0.0))

        carbon_dot = self.window.canvas.atom_dots[0]
        self.assertEqual(carbon_dot.brush().color().alpha(), 0)

        self._click_scene_point(QPointF(3.0, 0.0))

        atom_ids, bond_ids = self.window.canvas._selected_ids()
        self.assertEqual(atom_ids, {0})
        self.assertEqual(bond_ids, set())
        self.assertTrue(self.window.canvas.selection_outlines)
        max_width = max(item.sceneBoundingRect().width() for item in self.window.canvas.selection_outlines)
        self.assertGreaterEqual(max_width, self.window.canvas.renderer.style.bond_length_px * 0.5)

    def test_explicit_atom_label_uses_circular_selection_indicator(self) -> None:
        atom_id = self.window.canvas.add_atom("P", 0.0, 0.0)
        self.window.canvas.add_or_update_atom_label(atom_id, "P", record=False)
        label = self.window.canvas.atom_items[atom_id]

        self._select_atom_ids(atom_id)

        self.assertEqual(len(self.window.canvas.selection_outlines), 1)
        rect = self.window.canvas.selection_outlines[0].sceneBoundingRect()
        self.assertAlmostEqual(rect.width(), rect.height(), delta=0.5)
        hit_rect = label.shape().boundingRect()
        self.assertGreaterEqual(hit_rect.width(), self.window.canvas._atom_pick_radius() * 2.0)

    def test_selected_atom_remains_hoverable_and_selected_when_dot_becomes_label(self) -> None:
        self.window.canvas.set_tool("select")
        atom_id = self.window.canvas.add_atom("C", 0.0, 0.0)
        self._select_atom_ids(atom_id)

        self.window.canvas.add_or_update_atom_label(atom_id, "N", show_carbon=True, record=False)

        atom_ids, bond_ids = self.window.canvas._selected_ids()
        self.assertEqual(atom_ids, {atom_id})
        self.assertEqual(bond_ids, set())
        self.assertTrue(self.window.canvas.atom_items[atom_id].isSelected())

        self._hover_scene_point(QPointF(40.0, 40.0))
        self._hover_scene_point(QPointF(0.0, 0.0))
        self.assertEqual(self.window.canvas.hover_atom_id, atom_id)

    def test_selected_atom_remains_hoverable_and_selected_when_label_becomes_dot(self) -> None:
        self.window.canvas.set_tool("select")
        atom_id = self.window.canvas.add_atom("N", 0.0, 0.0)
        self.window.canvas.add_or_update_atom_label(atom_id, "N", record=False)
        self._select_atom_ids(atom_id)

        self.window.canvas.clear_atom_label(atom_id)

        atom_ids, bond_ids = self.window.canvas._selected_ids()
        self.assertEqual(atom_ids, {atom_id})
        self.assertEqual(bond_ids, set())
        self.assertTrue(self.window.canvas.atom_dots[atom_id].isSelected())

        self._hover_scene_point(QPointF(40.0, 40.0))
        self._hover_scene_point(QPointF(0.0, 0.0))
        self.assertEqual(self.window.canvas.hover_atom_id, atom_id)

    def test_clicking_left_side_of_ch3_label_selects_atom(self) -> None:
        self.window.canvas.set_tool("select")
        atom_id = self.window.canvas.add_atom("C", 0.0, 0.0)
        self.window.canvas.add_or_update_atom_label(atom_id, "CH3", show_carbon=True, record=False)
        label = self.window.canvas.atom_items[atom_id]
        rect = label.sceneBoundingRect()
        hit_rect = label.shape().boundingRect()
        self.assertGreater(hit_rect.width(), self.window.canvas._atom_pick_radius() * 2.0)

        self._click_scene_point(QPointF(rect.left() + 1.0, rect.center().y()))

        atom_ids, bond_ids = self.window.canvas._selected_ids()
        self.assertEqual(atom_ids, {atom_id})
        self.assertEqual(bond_ids, set())

    def test_preferred_structure_item_on_labeled_atom_and_bond_prefers_atom(self) -> None:
        self.window.canvas.add_bond_from_points(QPointF(0.0, 0.0), QPointF(20.0, 0.0))
        self.window.canvas.add_or_update_atom_label(0, "P", record=False)

        item = self.window.canvas.preferred_structure_item_at_scene_pos(QPointF(4.0, 0.0))

        self.assertIsNotNone(item)
        self.assertEqual(item.data(0), "atom")

    def test_preferred_structure_item_near_ring_vertex_returns_atom(self) -> None:
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        ring_atom_ids = self.window.canvas.ring_items[0].data(2)
        self.assertIsInstance(ring_atom_ids, list)
        atom = self.window.canvas.model.atoms[ring_atom_ids[0]]

        item = self.window.canvas.preferred_structure_item_at_scene_pos(QPointF(atom.x + 1.0, atom.y + 1.0))

        self.assertIsNotNone(item)
        self.assertEqual(item.data(0), "atom")
        self.assertEqual(item.data(1), ring_atom_ids[0])

    def test_hover_on_labeled_atom_and_bond_prefers_atom(self) -> None:
        self.window.canvas.add_bond_from_points(QPointF(0.0, 0.0), QPointF(20.0, 0.0))
        self.window.canvas.add_or_update_atom_label(0, "P", record=False)

        self.window.canvas._update_hover_highlight(QPointF(4.0, 0.0))

        self.assertEqual(self.window.canvas.hover_atom_id, 0)
        self.assertIsNone(self.window.canvas.hover_bond_id)

    def test_clicking_visible_left_side_of_compact_label_connected_bond_selects_atom(self) -> None:
        self.window.canvas.set_tool("select")
        left = self.window.canvas.add_atom("N", 0.0, 0.0)
        right = self.window.canvas.add_atom("C", 20.0, 0.0)
        self.window.canvas.add_or_update_atom_label(left, "N", record=False)
        self.window.canvas.add_bond(left, right)
        self.window.canvas._add_bond_graphics(0)
        label = self.window.canvas.atom_items[left]
        rect = label.sceneBoundingRect()

        self._click_scene_point(QPointF(rect.left() + 1.0, rect.center().y()))

        atom_ids, bond_ids = self.window.canvas._selected_ids()
        self.assertEqual(atom_ids, {left})
        self.assertEqual(bond_ids, set())

    def test_hover_near_ring_vertex_prefers_atom(self) -> None:
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        ring_atom_ids = self.window.canvas.ring_items[0].data(2)
        self.assertIsInstance(ring_atom_ids, list)
        target_atom_id = ring_atom_ids[0]
        atom = self.window.canvas.model.atoms[target_atom_id]

        self.window.canvas._update_hover_highlight(QPointF(atom.x + 1.0, atom.y + 1.0))

        self.assertEqual(self.window.canvas.hover_atom_id, target_atom_id)
        self.assertIsNone(self.window.canvas.hover_bond_id)

    def test_benzene_ring_carbons_have_selectable_atom_dots(self) -> None:
        self.window.canvas.set_tool("select")
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        ring_atom_ids = self.window.canvas.ring_items[0].data(2)

        self.assertIsInstance(ring_atom_ids, list)
        first_atom_id = ring_atom_ids[0]
        self.assertIn(first_atom_id, self.window.canvas.atom_dots)

        atom = self.window.canvas.model.atoms[first_atom_id]
        self._hover_scene_point(QPointF(atom.x, atom.y))
        self._click_scene_point(QPointF(atom.x, atom.y))

        atom_ids, bond_ids = self.window.canvas._selected_ids()
        self.assertEqual(atom_ids, {first_atom_id})
        self.assertEqual(bond_ids, set())

    def test_multi_atom_selection_adds_component_overlay_without_center_marker(self) -> None:
        left = self.window.canvas.add_atom("C", -10.0, 0.0)
        right = self.window.canvas.add_atom("C", 10.0, 0.0)
        self.window.canvas.add_bond(left, right)
        self.window.canvas._add_bond_graphics(0)

        self._select_atom_ids(left, right)

        kinds = [item.data(2) or {} for item in self.window.canvas.selection_outlines]
        self.assertEqual(sum(1 for data in kinds if data.get("kind") == "component"), 1)
        self.assertEqual(sum(1 for data in kinds if data.get("kind") == "center"), 0)
        self.assertTrue(all(data.get("kind") == "component" for data in kinds))
        component_outline = next(
            item
            for item in self.window.canvas.selection_outlines
            if (item.data(2) or {}).get("kind") == "component"
        )
        self.assertEqual(component_outline.path().fillRule(), Qt.FillRule.WindingFill)
        self.assertEqual(component_outline.brush().color().name(), "#1f5eff")

    def test_perspective_tool_toggles_center_marker_for_multi_atom_selection(self) -> None:
        left = self.window.canvas.add_atom("C", -10.0, 0.0)
        right = self.window.canvas.add_atom("C", 10.0, 0.0)
        self.window.canvas.add_bond(left, right)
        self.window.canvas._add_bond_graphics(0)

        self._select_atom_ids(left, right)
        self.assertFalse(any((item.data(2) or {}).get("kind") == "center" for item in self.window.canvas.selection_outlines))

        self.window.canvas.set_tool("perspective")

        self.assertEqual(
            sum(1 for item in self.window.canvas.selection_outlines if (item.data(2) or {}).get("kind") == "center"),
            2,
        )

        self.window.canvas.set_tool("select")

        self.assertFalse(any((item.data(2) or {}).get("kind") == "center" for item in self.window.canvas.selection_outlines))

    def test_ring_double_bond_selection_overlay_tracks_outer_bond_line(self) -> None:
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        ring_atom_ids = self.window.canvas.ring_items[0].data(2)

        self.assertIsInstance(ring_atom_ids, list)
        self._select_atom_ids(*ring_atom_ids)

        outer_mid = None
        inner_mid = None
        overlay_center = None
        for bond_id, items in self.window.canvas.bond_items.items():
            if len(items) < 2 or not all(hasattr(item, "line") for item in items):
                continue
            first = items[0].line()
            second = items[1].line()
            outer_mid = QPointF((first.x1() + first.x2()) * 0.5, (first.y1() + first.y2()) * 0.5)
            inner_mid = QPointF((second.x1() + second.x2()) * 0.5, (second.y1() + second.y2()) * 0.5)
            overlay_center = self.window.canvas._selection_path_for_bond(bond_id).boundingRect().center()
            break
        self.assertIsNotNone(outer_mid)
        self.assertIsNotNone(inner_mid)
        self.assertIsNotNone(overlay_center)
        outer_distance = (overlay_center - outer_mid).manhattanLength()
        inner_distance = (overlay_center - inner_mid).manhattanLength()
        self.assertLess(outer_distance, inner_distance)

    def test_double_bond_selection_path_uses_single_bond_width(self) -> None:
        single_left = self.window.canvas.add_atom("C", -20.0, 0.0)
        single_right = self.window.canvas.add_atom("C", 20.0, 0.0)
        self.window.canvas.add_bond(single_left, single_right)
        self.window.canvas._add_bond_graphics(0)

        double_left = self.window.canvas.add_atom("C", -20.0, 30.0)
        double_right = self.window.canvas.add_atom("C", 20.0, 30.0)
        self.window.canvas.add_bond(double_left, double_right, order=2)
        self.window.canvas._add_bond_graphics(1)

        single_rect = self.window.canvas._selection_path_for_bond(0).boundingRect()
        double_rect = self.window.canvas._selection_path_for_bond(1).boundingRect()

        self.assertAlmostEqual(single_rect.height(), double_rect.height(), delta=0.5)

    def test_clicking_near_bond_selects_bond(self) -> None:
        self.window.canvas.set_tool("select")
        left = self.window.canvas.add_atom("C", -10.0, 0.0)
        right = self.window.canvas.add_atom("C", 10.0, 0.0)
        self.window.canvas.add_bond(left, right)
        self.window.canvas._add_bond_graphics(0)

        self._click_scene_point(QPointF(0.0, 3.5))

        atom_ids, bond_ids = self.window.canvas._selected_ids()
        self.assertEqual(atom_ids, set())
        self.assertEqual(bond_ids, {0})

    def test_preferred_structure_item_outside_labeled_atom_toward_bond_prefers_bond(self) -> None:
        left = self.window.canvas.add_atom("N", 0.0, 0.0)
        right = self.window.canvas.add_atom("C", 20.0, 0.0)
        self.window.canvas.add_or_update_atom_label(left, "N", record=False)
        self.window.canvas.add_bond(left, right)
        self.window.canvas._add_bond_graphics(0)
        label = self.window.canvas.atom_items[left]
        rect = label.sceneBoundingRect()

        item = self.window.canvas.preferred_structure_item_at_scene_pos(QPointF(rect.right() + 1.0, rect.center().y()))

        self.assertIsNotNone(item)
        self.assertEqual(item.data(0), "bond")

    def test_select_tool_drag_context_matches_selection_hit_test_for_selected_bond_endpoints(self) -> None:
        self.window.canvas.set_tool("select")
        left = self.window.canvas.add_atom("C", -20.0, 0.0)
        right = self.window.canvas.add_atom("C", 20.0, 0.0)
        self.window.canvas.add_bond(left, right)
        self.window.canvas._add_bond_graphics(0)

        self._select_items(*self.window.canvas.bond_items[0])

        select_tool = self.window.canvas.tools.tools["select"]
        atom_ids, selection_items = select_tool._selection_drag_context()

        self.assertEqual(atom_ids, {left, right})
        self.assertTrue(selection_items)
        self.assertEqual({item.data(1) for item in selection_items}, {0})

        left_atom = self.window.canvas.model.atoms[left]
        right_atom = self.window.canvas.model.atoms[right]
        self.assertIsNotNone(left_atom)
        self.assertIsNotNone(right_atom)
        self.assertTrue(self.window.canvas.selection_hit_test(QPointF(left_atom.x, left_atom.y)))
        self.assertTrue(self.window.canvas.selection_hit_test(QPointF(right_atom.x, right_atom.y)))

    def test_select_tool_drag_context_matches_selection_hit_test_for_selected_arrow_rect(self) -> None:
        self.window.canvas.set_tool("select")
        arrow = self.window.canvas.add_arrow(QPointF(-40.0, 0.0), QPointF(20.0, 20.0), "arrow")

        self._select_items(arrow)

        select_tool = self.window.canvas.tools.tools["select"]
        atom_ids, selection_items = select_tool._selection_drag_context()

        self.assertEqual(atom_ids, set())
        self.assertEqual(selection_items, [arrow])

        rect = arrow.sceneBoundingRect()
        interior_point = QPointF(rect.left() + 6.0, rect.bottom() - 6.0)
        self.assertIsNone(self.window.canvas.item_at_scene_pos(interior_point))
        self.assertTrue(self.window.canvas.selection_hit_test(interior_point))

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
