import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsPathItem,
        QGraphicsTextItem,
        QToolButton,
    )
except ModuleNotFoundError:
    QApplication = None
    QTest = None
    Qt = None
    QPointF = None
    QRectF = None
    QEvent = None
    QGraphicsPathItem = None
    QGraphicsTextItem = None

if QApplication is not None:
    from core.history import MoveAtomsCommand
    from ui.atom_coords_access import atom_coords_3d_for, current_atom_coords_3d_for
    from ui.atom_label_access import add_or_update_atom_label, clear_atom_label_for
    from ui.bond_graphics_access import (
        add_bond_graphics_for,
        project_point_3d_for,
        ring_center_3d_for_bond_for,
    )
    from ui.bond_label_geometry_access import trim_line_for_labels_for
    from ui.canvas_atom_graphics_state import (
        atom_dots_for,
        atom_items_for,
        visible_atom_item_for,
    )
    from ui.canvas_bond_graphics_state import bond_items_for, bond_items_for_id
    from ui.canvas_bond_renderer_state import update_bond_geometry_for
    from ui.canvas_geometry_access import mark_target_distance_for_atom_for
    from ui.canvas_hover_refresh import refresh_hover_from_cursor_for
    from ui.canvas_hover_state import hover_state_for
    from ui.canvas_insert_state import insert_state_for
    from ui.canvas_mark_registry import mark_registry_for
    from ui.canvas_rotation_state import rotation_state_for
    from ui.canvas_scene_items_state import (
        arrow_items_for,
        mark_items_for,
        ring_items_for,
        ts_bracket_items_for,
    )
    from ui.canvas_scene_reset_access import clear_scene_for
    from ui.canvas_service_access import canvas_services_for
    from ui.canvas_tool_settings_state import tool_settings_state_for
    from ui.canvas_window_access import (
        restore_canvas_state_for,
        snapshot_canvas_state_for,
    )
    from ui.hover_interaction_access import update_hover_highlight_for
    from ui.main_window import MainWindow
    from ui.main_window_ports import active_canvas_for_window, services_for_window
    from ui.mark_item_access import mark_center_for
    from ui.move_access import move_atoms_for
    from ui.pick_radius_access import atom_pick_radius_for
    from ui.scene_decoration_access import (
        add_arrow_for,
        add_mark_for,
        add_mark_for_atom_for,
        add_ts_bracket_for,
    )
    from ui.scene_item_state import scene_item_state_for
    from ui.selection_collection_access import selected_ids_for
    from ui.selection_outline_state import selection_outlines_for
    from ui.selection_rotation_access import (
        center_for_coords_3d,
        fragment_plane_normal_for,
    )
    from ui.selection_style_access import selection_indicator_rect_for_atom_for
    from ui.structure_mutation_access import (
        add_atom_for,
        add_benzene_ring_for,
        add_bond_between_points_for,
        add_bond_for,
    )


    def refresh_hover_from_cursor_for_canvas(canvas) -> None:
        refresh_hover_from_cursor_for(
            canvas,
            update_hover_highlight=canvas.services.hover_interaction_service.update_hover_highlight,
            clear_hover_highlight=canvas.services.hover_scene_service.clear_hover_highlight,
        )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI smoke tests")
class GuiShortcutSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        active_canvas_for_window(self.window).setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _hover_scene_point(self, point: QPointF) -> None:
        viewport_pos = active_canvas_for_window(self.window).mapFromScene(point)
        QTest.mouseMove(active_canvas_for_window(self.window).viewport(), viewport_pos)
        self.app.processEvents()
        if insert_state_for(active_canvas_for_window(self.window)).template_active:
            active_canvas_for_window(self.window).services.insert_controller.render_template_preview(point)
        elif insert_state_for(active_canvas_for_window(self.window)).smiles_active:
            active_canvas_for_window(self.window).services.insert_controller.render_smiles_preview(point)
        else:
            update_hover_highlight_for(active_canvas_for_window(self.window), point)
        self.app.processEvents()
        QTest.qWait(10)

    def _click_scene_point(self, point: QPointF, modifiers=None) -> None:
        if modifiers is None:
            modifiers = Qt.KeyboardModifier.NoModifier
        viewport_pos = active_canvas_for_window(self.window).mapFromScene(point)
        QTest.mouseClick(
            active_canvas_for_window(self.window).viewport(),
            Qt.MouseButton.LeftButton,
            modifiers,
            viewport_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def _drag_scene_point(self, start: QPointF, end: QPointF, modifiers=None) -> None:
        if modifiers is None:
            modifiers = Qt.KeyboardModifier.NoModifier
        start_pos = active_canvas_for_window(self.window).mapFromScene(start)
        end_pos = active_canvas_for_window(self.window).mapFromScene(end)
        QTest.mousePress(
            active_canvas_for_window(self.window).viewport(),
            Qt.MouseButton.LeftButton,
            modifiers,
            start_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)
        QTest.mouseMove(active_canvas_for_window(self.window).viewport(), end_pos)
        self.app.processEvents()
        QTest.qWait(10)
        QTest.mouseRelease(
            active_canvas_for_window(self.window).viewport(),
            Qt.MouseButton.LeftButton,
            modifiers,
            end_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def _press_key(self, key: int, modifiers=None) -> None:
        if modifiers is None:
            modifiers = Qt.KeyboardModifier.NoModifier
        QTest.keyClick(active_canvas_for_window(self.window), key, modifiers)
        self.app.processEvents()
        QTest.qWait(10)

    def _select_atom_ids(self, *atom_ids: int) -> None:
        active_canvas_for_window(self.window).scene().clearSelection()
        for atom_id in atom_ids:
            item = visible_atom_item_for(active_canvas_for_window(self.window), atom_id)
            self.assertIsNotNone(item)
            item.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

    def _select_items(self, *items) -> None:
        active_canvas_for_window(self.window).scene().clearSelection()
        for item in items:
            self.assertIsNotNone(item)
            item.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

    def _assert_ring_polygon_matches_atoms(self, ring_item) -> None:
        ring_atom_ids = ring_item.data(2)
        self.assertIsInstance(ring_atom_ids, list)
        polygon = ring_item.polygon()
        self.assertEqual(polygon.count(), len(ring_atom_ids))
        for atom_id, point in zip(ring_atom_ids, polygon, strict=False):
            atom = active_canvas_for_window(self.window).model.atoms.get(atom_id)
            self.assertIsNotNone(atom)
            assert atom is not None
            self.assertAlmostEqual(point.x(), atom.x)
            self.assertAlmostEqual(point.y(), atom.y)

    def _bond_scene_segments(self, bond_id: int) -> list[tuple[float, float, float, float]]:
        segments = []
        for item in bond_items_for_id(active_canvas_for_window(self.window), bond_id):
            if not hasattr(item, "line"):
                continue
            line = item.line()
            p1 = item.mapToScene(line.p1())
            p2 = item.mapToScene(line.p2())
            segments.append((p1.x(), p1.y(), p2.x(), p2.y()))
        return segments

    def _assert_ring_double_bonds_face_inward(self, ring_item) -> None:
        ring_atom_ids = ring_item.data(2)
        self.assertIsInstance(ring_atom_ids, list)
        assert isinstance(ring_atom_ids, list)
        center_x = sum(active_canvas_for_window(self.window).model.atoms[atom_id].x for atom_id in ring_atom_ids) / len(ring_atom_ids)
        center_y = sum(active_canvas_for_window(self.window).model.atoms[atom_id].y for atom_id in ring_atom_ids) / len(ring_atom_ids)

        checked = 0
        for index, atom_a in enumerate(ring_atom_ids):
            atom_b = ring_atom_ids[(index + 1) % len(ring_atom_ids)]
            bond_id = active_canvas_for_window(self.window).services.canvas_graph_service.bond_id_between(atom_a, atom_b)
            self.assertIsNotNone(bond_id)
            assert bond_id is not None
            bond = active_canvas_for_window(self.window).model.bonds[bond_id]
            self.assertIsNotNone(bond)
            assert bond is not None
            if bond.order != 2:
                continue
            segments = self._bond_scene_segments(bond_id)
            self.assertEqual(len(segments), 2)
            outer = segments[0]
            inner = segments[1]
            outer_mid = ((outer[0] + outer[2]) * 0.5, (outer[1] + outer[3]) * 0.5)
            inner_mid = ((inner[0] + inner[2]) * 0.5, (inner[1] + inner[3]) * 0.5)
            outer_dist = math.hypot(outer_mid[0] - center_x, outer_mid[1] - center_y)
            inner_dist = math.hypot(inner_mid[0] - center_x, inner_mid[1] - center_y)
            outer_len = math.hypot(outer[2] - outer[0], outer[3] - outer[1])
            inner_len = math.hypot(inner[2] - inner[0], inner[3] - inner[1])
            self.assertLess(inner_dist, outer_dist - 0.1)
            self.assertLess(inner_len, outer_len - 0.1)
            checked += 1

        self.assertGreaterEqual(checked, 3)

    def test_generic_tool_shortcuts_switch_active_tool(self) -> None:
        self._press_key(Qt.Key.Key_X)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "bond")
        self.assertEqual(tool_settings_state_for(active_canvas_for_window(self.window)).active_bond_style, "single")
        self.assertEqual(tool_settings_state_for(active_canvas_for_window(self.window)).active_bond_order, 1)

        self._press_key(Qt.Key.Key_A)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "text")

        self._press_key(Qt.Key.Key_T)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "note")

        active_canvas_for_window(self.window).services.tool_mode_controller.set_arrow_type("curved_double")
        self._press_key(Qt.Key.Key_E)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "arrow")
        self.assertEqual(tool_settings_state_for(active_canvas_for_window(self.window)).active_arrow_type, "reaction")
        reaction_button = next(
            widget for widget in self.window.findChildren(QToolButton) if widget.toolTip() == "Reaction"
        )
        self.assertTrue(reaction_button.isChecked())

        self._press_key(Qt.Key.Key_J)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "benzene")
        hover_pos = QPointF(24.0, 18.0)
        self._hover_scene_point(hover_pos)
        self.assertTrue(insert_state_for(active_canvas_for_window(self.window)).template_active)
        self.assertTrue(insert_state_for(active_canvas_for_window(self.window)).template_preview_items)

        ring_count_before = len(ring_items_for(active_canvas_for_window(self.window)))
        self._press_key(Qt.Key.Key_X)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "bond")
        self.assertFalse(insert_state_for(active_canvas_for_window(self.window)).template_active)
        self.assertEqual(insert_state_for(active_canvas_for_window(self.window)).template_preview_items, [])
        self._click_scene_point(hover_pos)
        self.assertEqual(len(ring_items_for(active_canvas_for_window(self.window))), ring_count_before)

        tool_settings_state_for(active_canvas_for_window(self.window)).active_bracket_type = "dagger"
        self._hover_scene_point(QPointF(200.0, 200.0))
        self._press_key(Qt.Key.Key_T, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "ts_bracket")
        self.assertEqual(tool_settings_state_for(active_canvas_for_window(self.window)).active_bracket_type, "square_pair")
        square_bracket_button = next(
            widget for widget in self.window.findChildren(QToolButton) if widget.toolTip() == "Square Brackets"
        )
        self.assertTrue(square_bracket_button.isChecked())

        self._press_key(Qt.Key.Key_G, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "orbital")
        self.assertEqual(tool_settings_state_for(active_canvas_for_window(self.window)).active_orbital_type, "s")

        self._press_key(Qt.Key.Key_E, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "mark")
        self.assertEqual(tool_settings_state_for(active_canvas_for_window(self.window)).mark_kind, "plus")

        self._press_key(Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "perspective")

        self._press_key(Qt.Key.Key_Space)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "select")

    def test_new_canvas_button_opens_a_separate_window(self) -> None:
        from ui.main_window_app import open_windows

        before_count = self.window.tab_references.canvas_count()
        existing = set(open_windows())
        button = self.window.findChild(QToolButton, "new_canvas_button")
        self.assertIsNotNone(button)
        assert button is not None

        QTest.mouseClick(
            button,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.app.processEvents()
        QTest.qWait(10)

        spawned = [window for window in open_windows() if window not in existing]
        for window in spawned:
            self.addCleanup(window.close)

        self.assertEqual(len(spawned), 1)
        # The current window keeps its single document; the new canvas is its own window.
        self.assertEqual(self.window.tab_references.canvas_count(), before_count)
        self.assertEqual(spawned[0].tab_references.canvas_count(), 1)
        self.assertTrue(spawned[0].windowTitle().endswith("— Chemvas"))

    def test_close_canvas_tab_removes_clean_target_canvas(self) -> None:
        services_for_window(self.window).canvas_document_service.new_canvas(self.window)

        closed = services_for_window(self.window).canvas_tab_ui_service.close_canvas_tab(self.window, 0)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertIsNone(closed)
        self.assertEqual(self.window.tab_references.canvas_count(), 1)
        self.assertEqual(self.window.tab_references.canvas_tabs.count(), 1)
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(0), "Canvas 2")

    def test_close_last_canvas_tab_creates_replacement_canvas(self) -> None:
        first_canvas = active_canvas_for_window(self.window)

        closed = services_for_window(self.window).canvas_tab_ui_service.close_canvas_tab(self.window, 0)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertIsNone(closed)
        self.assertEqual(self.window.tab_references.canvas_count(), 1)
        self.assertIsNot(active_canvas_for_window(self.window), first_canvas)
        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(0), "Canvas 2")

    def test_shift_click_toggles_atom_selection(self) -> None:
        atom_a = add_atom_for(active_canvas_for_window(self.window), "C", -40.0, 0.0)
        atom_b = add_atom_for(active_canvas_for_window(self.window), "O", 40.0, 0.0)
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")

        self._click_scene_point(QPointF(-40.0, 0.0))
        self.assertEqual(selected_ids_for(active_canvas_for_window(self.window)), ({atom_a}, set()))

        self._click_scene_point(QPointF(40.0, 0.0), Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(selected_ids_for(active_canvas_for_window(self.window)), ({atom_a, atom_b}, set()))

        self._click_scene_point(QPointF(40.0, 0.0), Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(selected_ids_for(active_canvas_for_window(self.window)), ({atom_a}, set()))

    def test_shift_click_toggles_arrow_selection(self) -> None:
        arrow_a = add_arrow_for(active_canvas_for_window(self.window), QPointF(-70.0, -10.0), QPointF(-20.0, -10.0), "arrow")
        arrow_b = add_arrow_for(active_canvas_for_window(self.window), QPointF(20.0, -10.0), QPointF(70.0, -10.0), "arrow")
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")

        self._click_scene_point(QPointF(-45.0, -10.0))
        self.assertTrue(arrow_a.isSelected())
        self.assertFalse(arrow_b.isSelected())

        self._click_scene_point(QPointF(45.0, -10.0), Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(arrow_a.isSelected())
        self.assertTrue(arrow_b.isSelected())

        self._click_scene_point(QPointF(-45.0, -10.0), Qt.KeyboardModifier.ShiftModifier)
        self.assertFalse(arrow_a.isSelected())
        self.assertTrue(arrow_b.isSelected())

    def test_perspective_shift_click_toggles_atom_selection(self) -> None:
        atom_a = add_atom_for(active_canvas_for_window(self.window), "C", -40.0, 0.0)
        atom_b = add_atom_for(active_canvas_for_window(self.window), "O", 40.0, 0.0)
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("perspective")

        self._click_scene_point(QPointF(-40.0, 0.0))
        self.assertEqual(selected_ids_for(active_canvas_for_window(self.window)), ({atom_a}, set()))

        self._click_scene_point(QPointF(40.0, 0.0), Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(selected_ids_for(active_canvas_for_window(self.window)), ({atom_a, atom_b}, set()))

        self._click_scene_point(QPointF(40.0, 0.0), Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(selected_ids_for(active_canvas_for_window(self.window)), ({atom_a}, set()))

    def test_perspective_shift_click_toggles_arrow_selection(self) -> None:
        arrow_a = add_arrow_for(active_canvas_for_window(self.window), QPointF(-70.0, -10.0), QPointF(-20.0, -10.0), "arrow")
        arrow_b = add_arrow_for(active_canvas_for_window(self.window), QPointF(20.0, -10.0), QPointF(70.0, -10.0), "arrow")
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("perspective")

        self._click_scene_point(QPointF(-45.0, -10.0))
        self.assertTrue(arrow_a.isSelected())
        self.assertFalse(arrow_b.isSelected())

        self._click_scene_point(QPointF(45.0, -10.0), Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(arrow_a.isSelected())
        self.assertTrue(arrow_b.isSelected())

        self._click_scene_point(QPointF(-45.0, -10.0), Qt.KeyboardModifier.ShiftModifier)
        self.assertFalse(arrow_a.isSelected())
        self.assertTrue(arrow_b.isSelected())

    def test_ts_bracket_round_trips_in_snapshot_state(self) -> None:
        add_ts_bracket_for(active_canvas_for_window(self.window), QRectF(QPointF(10.0, 15.0), QPointF(56.0, 78.0)))

        state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
        self.assertEqual(len(state["ts_brackets"]), 1)

        clear_scene_for(active_canvas_for_window(self.window))
        restore_canvas_state_for(active_canvas_for_window(self.window), state)

        ts_bracket_items = ts_bracket_items_for(active_canvas_for_window(self.window))
        self.assertEqual(len(ts_bracket_items), 1)
        restored = scene_item_state_for(active_canvas_for_window(self.window), ts_bracket_items[0])
        self.assertEqual(restored["kind"], "ts_bracket")

    def test_mark_hover_preview_uses_pointer_position_on_empty_canvas(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_mark_kind("plus")
        hover_pos = QPointF(24.0, 31.0)

        update_hover_highlight_for(active_canvas_for_window(self.window), hover_pos)

        preview = next(item for item in hover_state_for(active_canvas_for_window(self.window)).items if isinstance(item, QGraphicsTextItem))
        center = mark_center_for(active_canvas_for_window(self.window), preview)
        self.assertAlmostEqual(center.x(), hover_pos.x(), places=2)
        self.assertAlmostEqual(center.y(), hover_pos.y(), places=2)

    def test_mark_hover_preview_matches_committed_atom_mark_position(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_mark_kind("minus")
        hover_pos = QPointF(5.0, -2.0)

        update_hover_highlight_for(active_canvas_for_window(self.window), hover_pos)

        preview = next(item for item in hover_state_for(active_canvas_for_window(self.window)).items if isinstance(item, QGraphicsTextItem))
        preview_center = mark_center_for(active_canvas_for_window(self.window), preview)
        committed = add_mark_for_atom_for(active_canvas_for_window(self.window), atom_id, hover_pos, kind="minus")
        committed_center = mark_center_for(active_canvas_for_window(self.window), committed)
        self.assertAlmostEqual(preview_center.x(), committed_center.x(), places=2)
        self.assertAlmostEqual(preview_center.y(), committed_center.y(), places=2)

    def test_atom_marks_use_fractional_label_clearance(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "Cl", 0.0, 0.0)
        atom = active_canvas_for_window(self.window).model.atoms[atom_id]
        base = active_canvas_for_window(self.window).renderer.style.bond_length_px * 0.2

        plus = add_mark_for_atom_for(active_canvas_for_window(self.window), atom_id, QPointF(0.0, 0.0), kind="plus", record=False)
        radical = add_mark_for_atom_for(active_canvas_for_window(self.window), atom_id, QPointF(0.0, 0.0), kind="radical", record=False)

        self.assertIsNotNone(plus)
        self.assertIsNotNone(radical)
        for kind, mark in (("plus", plus), ("radical", radical)):
            direction = mark_center_for(active_canvas_for_window(self.window), mark)
            dx = direction.x() - atom.x
            dy = direction.y() - atom.y
            distance = math.hypot(dx, dy)
            full_clearance = mark_target_distance_for_atom_for(
                active_canvas_for_window(self.window),
                atom_id,
                dx / distance,
                dy / distance,
                kind,
            )
            expected = base + (full_clearance - base) * 0.25
            self.assertGreater(distance, base)
            self.assertAlmostEqual(distance, expected, places=2)

    def test_hover_preview_clears_when_cursor_leaves_viewport(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        viewport_pos = active_canvas_for_window(self.window).mapFromScene(QPointF(0.0, 0.0))
        global_pos = active_canvas_for_window(self.window).viewport().mapToGlobal(viewport_pos)

        with patch("ui.canvas_hover_refresh.QCursor.pos", return_value=global_pos):
            refresh_hover_from_cursor_for_canvas(active_canvas_for_window(self.window))
            self.assertEqual(hover_state_for(active_canvas_for_window(self.window)).atom_id, atom_id)
            self.assertTrue(hover_state_for(active_canvas_for_window(self.window)).items)

            active_canvas_for_window(self.window).viewportEvent(QEvent(QEvent.Type.Leave))
            self.app.processEvents()
            QTest.qWait(10)

        self.assertIsNone(hover_state_for(active_canvas_for_window(self.window)).atom_id)
        self.assertIsNone(hover_state_for(active_canvas_for_window(self.window)).bond_id)
        self.assertEqual(hover_state_for(active_canvas_for_window(self.window)).items, [])

    def test_tool_change_refreshes_hover_preview_without_mouse_move(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_bond_style("wedge", 1)
        viewport_pos = active_canvas_for_window(self.window).mapFromScene(QPointF(0.0, 0.0))
        global_pos = active_canvas_for_window(self.window).viewport().mapToGlobal(viewport_pos)

        with patch("ui.canvas_hover_refresh.QCursor.pos", return_value=global_pos):
            refresh_hover_from_cursor_for_canvas(active_canvas_for_window(self.window))
            self.assertEqual(hover_state_for(active_canvas_for_window(self.window)).atom_id, atom_id)
            self.assertGreaterEqual(len(hover_state_for(active_canvas_for_window(self.window)).items), 2)

            canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
            self.app.processEvents()
            QTest.qWait(10)

        self.assertEqual(hover_state_for(active_canvas_for_window(self.window)).atom_id, atom_id)
        self.assertEqual(len(hover_state_for(active_canvas_for_window(self.window)).items), 1)

    def test_tool_shortcuts_refresh_cursor_preview_without_mouse_move(self) -> None:
        canvas = active_canvas_for_window(self.window)
        add_benzene_ring_for(canvas, QPointF(-80.0, -60.0))
        hover_pos = QPointF(24.0, 18.0)
        global_pos = canvas.viewport().mapToGlobal(canvas.mapFromScene(hover_pos))

        canvas_services_for(canvas).tool_mode_controller.set_tool("select")
        self.app.processEvents()

        with patch("ui.canvas_hover_refresh.QCursor.pos", return_value=global_pos):
            self._press_key(Qt.Key.Key_X)

        self.assertEqual(canvas.services.tools.active.name, "bond")
        self.assertTrue(hover_state_for(canvas).items)
        self.assertTrue((hover_state_for(canvas).style or "").startswith("single:1"))

        QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(QPointF(25.0, 18.0)))
        self.app.processEvents()
        QTest.qWait(10)

        self.assertTrue(hover_state_for(canvas).items)
        self.assertTrue((hover_state_for(canvas).style or "").startswith("single:1"))

        with patch("ui.canvas_hover_refresh.QCursor.pos", return_value=global_pos):
            self._press_key(Qt.Key.Key_J)

        self.assertEqual(canvas.services.tools.active.name, "benzene")
        self.assertTrue(insert_state_for(canvas).template_active)
        self.assertEqual(insert_state_for(canvas).template_ring_size, 6)
        self.assertEqual(insert_state_for(canvas).template_ring_style, "benzene")
        self.assertEqual(len(insert_state_for(canvas).template_preview_lines), 9)

    def test_benzene_tool_category_selects_default_benzene_template(self) -> None:
        hover_pos = QPointF(24.0, 18.0)

        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("benzene")
        self._hover_scene_point(hover_pos)

        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "benzene")
        self.assertEqual(insert_state_for(active_canvas_for_window(self.window)).benzene_preview_items, [])
        self.assertTrue(insert_state_for(active_canvas_for_window(self.window)).template_active)
        self.assertEqual(insert_state_for(active_canvas_for_window(self.window)).template_ring_size, 6)
        self.assertEqual(insert_state_for(active_canvas_for_window(self.window)).template_ring_style, "benzene")
        self.assertEqual(len(insert_state_for(active_canvas_for_window(self.window)).template_preview_lines), 9)

        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "select")
        self.assertEqual(insert_state_for(active_canvas_for_window(self.window)).benzene_preview_items, [])
        self.assertFalse(insert_state_for(active_canvas_for_window(self.window)).template_active)

        active_canvas_for_window(self.window).services.tools.active.deactivate()
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(insert_state_for(active_canvas_for_window(self.window)).benzene_preview_items, [])

    def test_bond_tool_drag_preview_clears_on_tool_change_and_deactivate(self) -> None:
        canvas = active_canvas_for_window(self.window)
        add_atom_for(canvas, "C", 0.0, 0.0)

        canvas_services_for(canvas).tool_mode_controller.set_tool("bond")
        bond_tool = canvas.services.tools.active
        self.assertEqual(bond_tool.name, "bond")
        self.assertEqual(bond_tool._preview_items, [])

        start = QPointF(0.0, 0.0)
        end = QPointF(52.0, 24.0)
        start_pos = canvas.mapFromScene(start)
        end_pos = canvas.mapFromScene(end)

        QTest.mousePress(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)
        QTest.mouseMove(canvas.viewport(), end_pos)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertTrue(bond_tool._preview_items)
        self.assertTrue(all(item.scene() is canvas.scene() for item in bond_tool._preview_items))

        canvas_services_for(canvas).tool_mode_controller.set_tool("select")
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(canvas.services.tools.active.name, "select")
        self.assertEqual(bond_tool._preview_items, [])

        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            end_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

        canvas_services_for(canvas).tool_mode_controller.set_tool("bond")
        bond_tool = canvas.services.tools.active
        self.assertEqual(bond_tool._preview_items, [])

        restart = QPointF(-24.0, 0.0)
        finish = QPointF(36.0, -28.0)
        restart_pos = canvas.mapFromScene(restart)
        finish_pos = canvas.mapFromScene(finish)

        QTest.mousePress(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            restart_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)
        QTest.mouseMove(canvas.viewport(), finish_pos)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertTrue(bond_tool._preview_items)
        self.assertTrue(all(item.scene() is canvas.scene() for item in bond_tool._preview_items))

        bond_tool.deactivate()
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(bond_tool._preview_items, [])

        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            finish_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

        canvas_services_for(canvas).tool_mode_controller.set_tool("select")

    def test_bond_tool_double_click_on_same_origin_creates_second_bond_without_selecting_atom(self) -> None:
        canvas = active_canvas_for_window(self.window)
        canvas_services_for(canvas).tool_mode_controller.set_tool("bond")

        origin = QPointF(0.0, 0.0)
        self._click_scene_point(origin)

        self.assertEqual(len([bond for bond in canvas.model.bonds if bond is not None]), 1)
        self.assertEqual(canvas.scene().selectedItems(), [])

        viewport_pos = canvas.mapFromScene(origin)
        QTest.mouseDClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_pos,
        )
        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(len([bond for bond in canvas.model.bonds if bond is not None]), 2)
        self.assertEqual(canvas.scene().selectedItems(), [])

    def test_arrow_tool_drag_preview_clears_on_tool_change_and_stale_release_does_not_commit(self) -> None:
        canvas = active_canvas_for_window(self.window)

        canvas_services_for(canvas).tool_mode_controller.set_tool("arrow")
        arrow_tool = canvas.services.tools.active
        self.assertEqual(arrow_tool.name, "arrow")
        self.assertEqual(len(arrow_items_for(canvas)), 0)

        start = QPointF(-12.0, -8.0)
        end = QPointF(64.0, 28.0)
        start_pos = canvas.mapFromScene(start)
        end_pos = canvas.mapFromScene(end)

        QTest.mousePress(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)
        QTest.mouseMove(canvas.viewport(), end_pos)
        self.app.processEvents()
        QTest.qWait(10)

        preview_item = arrow_tool._preview_item
        self.assertIsNotNone(preview_item)
        self.assertIsNotNone(arrow_tool._start_pos)
        assert preview_item is not None
        self.assertIs(preview_item.scene(), canvas.scene())

        canvas_services_for(canvas).tool_mode_controller.set_tool("select")
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(canvas.services.tools.active.name, "select")
        self.assertIsNone(arrow_tool._preview_item)
        self.assertIsNone(arrow_tool._start_pos)
        self.assertIsNone(preview_item.scene())

        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            end_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(len(arrow_items_for(canvas)), 0)

    def test_ts_bracket_drag_preview_clears_on_tool_change_and_stale_release_does_not_commit(self) -> None:
        canvas = active_canvas_for_window(self.window)

        canvas_services_for(canvas).tool_mode_controller.set_tool("ts_bracket")
        tool = canvas.services.tools.active
        self.assertEqual(tool.name, "ts_bracket")
        self.assertEqual(len(ts_bracket_items_for(canvas)), 0)

        start = QPointF(18.0, -24.0)
        end = QPointF(88.0, 42.0)
        start_pos = canvas.mapFromScene(start)
        end_pos = canvas.mapFromScene(end)

        QTest.mousePress(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)
        QTest.mouseMove(canvas.viewport(), end_pos)
        self.app.processEvents()
        QTest.qWait(10)

        preview_item = tool._preview_item
        self.assertIsNotNone(preview_item)
        self.assertIsNotNone(tool._start_pos)
        assert preview_item is not None
        self.assertIs(preview_item.scene(), canvas.scene())

        canvas_services_for(canvas).tool_mode_controller.set_tool("select")
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(canvas.services.tools.active.name, "select")
        self.assertIsNone(tool._preview_item)
        self.assertIsNone(tool._start_pos)
        self.assertIsNone(preview_item.scene())

        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            end_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(len(ts_bracket_items_for(canvas)), 0)

    def test_scroll_refresh_clears_stale_hover_preview(self) -> None:
        canvas = active_canvas_for_window(self.window)
        canvas.setSceneRect(QRectF(-2000.0, -2000.0, 4000.0, 4000.0))
        self.app.processEvents()
        atom_id = add_atom_for(canvas, "C", 0.0, 0.0)
        viewport_pos = canvas.mapFromScene(QPointF(0.0, 0.0))
        global_pos = canvas.viewport().mapToGlobal(viewport_pos)

        with patch("ui.canvas_hover_refresh.QCursor.pos", return_value=global_pos):
            refresh_hover_from_cursor_for_canvas(canvas)
            self.assertEqual(hover_state_for(canvas).atom_id, atom_id)

            h_scroll = canvas.horizontalScrollBar()
            start_value = h_scroll.value()
            h_scroll.setValue(min(h_scroll.maximum(), start_value + 240))
            self.assertNotEqual(h_scroll.value(), start_value)
            self.app.processEvents()
            QTest.qWait(10)

        self.assertIsNone(hover_state_for(canvas).atom_id)
        self.assertEqual(hover_state_for(canvas).items, [])

    def test_legacy_tool_shortcuts_do_not_switch_active_tool(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("text")

        self._press_key(Qt.Key.Key_V)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "text")

        self._press_key(Qt.Key.Key_B)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "text")

        self._press_key(Qt.Key.Key_R)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "text")

        self._press_key(Qt.Key.Key_A)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "text")

        self._press_key(Qt.Key.Key_O)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "text")

    def test_perspective_tool_keeps_selection_drag_mode(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("perspective")
        self.assertEqual(
            active_canvas_for_window(self.window).dragMode(),
            active_canvas_for_window(self.window).DragMode.RubberBandDrag,
        )

    def test_atom_hotkeys_apply_label_mark_and_sprout_bond(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        atom_point = QPointF(0.0, 0.0)
        self._hover_scene_point(atom_point)

        self._press_key(Qt.Key.Key_N)
        self.assertEqual(active_canvas_for_window(self.window).model.atoms[atom_id].element, "N")

        self._press_key(Qt.Key.Key_Plus)
        marks = mark_registry_for(active_canvas_for_window(self.window)).by_atom.get(atom_id, [])
        self.assertEqual(len(marks), 1)
        self.assertEqual((marks[0].data(1) or {}).get("kind"), "plus")

        initial_bond_count = sum(1 for bond in active_canvas_for_window(self.window).model.bonds if bond is not None)
        self._press_key(Qt.Key.Key_1)
        bond_count = sum(1 for bond in active_canvas_for_window(self.window).model.bonds if bond is not None)
        self.assertGreater(bond_count, initial_bond_count)

    def test_text_tool_preserves_entered_atom_label_case(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("text")
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_atom_symbol("OH")
        self._hover_scene_point(QPointF(0.0, 0.0))

        self._click_scene_point(QPointF(0.0, 0.0))

        self.assertEqual(active_canvas_for_window(self.window).model.atoms[atom_id].element, "OH")
        label = atom_items_for(active_canvas_for_window(self.window)).get(atom_id)
        self.assertIsNotNone(label)
        self.assertEqual(label.toPlainText(), "OH")

    def test_bond_hotkeys_modify_hovered_bond(self) -> None:
        start = QPointF(-40.0, 0.0)
        end = QPointF(40.0, 0.0)
        add_bond_between_points_for(active_canvas_for_window(self.window), start, end)
        bond_id = next(i for i, bond in enumerate(active_canvas_for_window(self.window).model.bonds) if bond is not None)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertIsNotNone(bond)
        midpoint = QPointF(0.0, 0.0)
        self._hover_scene_point(midpoint)

        self._press_key(Qt.Key.Key_2)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual(bond.order, 2)
        self.assertEqual(bond.style, "double")

        self._press_key(Qt.Key.Key_B, Qt.KeyboardModifier.ShiftModifier)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual(bond.order, 2)
        self.assertEqual(bond.style, "bold_in")

        self._press_key(Qt.Key.Key_H, Qt.KeyboardModifier.ShiftModifier)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual(bond.order, 1)
        self.assertEqual(bond.style, "hash")

        ring_count_before = len(ring_items_for(active_canvas_for_window(self.window)))
        self._press_key(Qt.Key.Key_A)
        self.assertEqual(active_canvas_for_window(self.window).services.tools.active.name, "bond")
        self.assertGreater(len(ring_items_for(active_canvas_for_window(self.window))), ring_count_before)

    def test_clicking_bond_toggles_single_and_double_without_variant_cycle(self) -> None:
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        bond_id = next(i for i, bond in enumerate(active_canvas_for_window(self.window).model.bonds) if bond is not None)
        midpoint = QPointF(0.0, 0.0)

        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_bond_style("single", 1)
        self._click_scene_point(midpoint)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual((bond.style, bond.order), ("double", 2))

        self._click_scene_point(midpoint)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual((bond.style, bond.order), ("single", 1))

        self._click_scene_point(midpoint)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual((bond.style, bond.order), ("double", 2))

        self._click_scene_point(midpoint)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual((bond.style, bond.order), ("single", 1))

    def test_drawing_single_bond_over_existing_double_upgrades_it_to_triple(self) -> None:
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        bond_id = next(i for i, bond in enumerate(active_canvas_for_window(self.window).model.bonds) if bond is not None)
        active_canvas_for_window(self.window).services.scene_transform_controller.apply_bond_style(bond_id, "double", 2)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual((bond.style, bond.order), ("double", 2))

        atom_a = active_canvas_for_window(self.window).model.atoms[bond.a]
        atom_b = active_canvas_for_window(self.window).model.atoms[bond.b]
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_bond_style("single", 1)
        self._drag_scene_point(QPointF(atom_a.x, atom_a.y), QPointF(atom_b.x, atom_b.y))

        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual((bond.style, bond.order), ("triple", 3))
        self.assertEqual(len([entry for entry in active_canvas_for_window(self.window).model.bonds if entry is not None]), 1)

    def test_adjacent_bold_bonds_mitre_to_shared_corners(self) -> None:
        canvas = active_canvas_for_window(self.window)
        a0 = add_atom_for(canvas, "C", 0.0, 0.0)
        a1 = add_atom_for(canvas, "C", 20.0, 0.0)
        a2 = add_atom_for(canvas, "C", 30.0, 17.320508)
        b0 = add_bond_for(canvas, a0, a1)
        b1 = add_bond_for(canvas, a1, a2)
        transform = canvas.services.scene_transform_controller
        transform.apply_bond_style(b0, "bold", 1)
        transform.apply_bond_style(b1, "bold", 1)

        vertex = QPointF(20.0, 0.0)

        def near_corners(bond_id):
            polygons = [item for item in bond_items_for_id(canvas, bond_id) if hasattr(item, "polygon")]
            self.assertEqual(len(polygons), 1)
            points = [polygons[0].mapToScene(point) for point in polygons[0].polygon()]
            return [p for p in points if math.hypot(p.x() - vertex.x(), p.y() - vertex.y()) < 8.0]

        corners0 = near_corners(b0)
        corners1 = near_corners(b1)
        # Each strip ends at the shared vertex with exactly two mitred corners.
        self.assertEqual(len(corners0), 2)
        self.assertEqual(len(corners1), 2)
        # Every vertex corner of one strip coincides with one of the other's, so
        # the two bold bonds share their end edge and read as one continuous outline.
        for c0 in corners0:
            self.assertTrue(
                any(math.hypot(c0.x() - c1.x(), c0.y() - c1.y()) < 1e-6 for c1 in corners1),
                f"bold strip corner ({c0.x()}, {c0.y()}) has no mitre partner",
            )

    def test_bold_bond_mitre_survives_geometry_update(self) -> None:
        # The in-place geometry update path (used during endpoint drags) must
        # produce the same mitred join as a full rebuild, not the old square strip.
        canvas = active_canvas_for_window(self.window)
        a0 = add_atom_for(canvas, "C", 0.0, 0.0)
        a1 = add_atom_for(canvas, "C", 20.0, 0.0)
        a2 = add_atom_for(canvas, "C", 30.0, 17.320508)
        b0 = add_bond_for(canvas, a0, a1)
        b1 = add_bond_for(canvas, a1, a2)
        transform = canvas.services.scene_transform_controller
        transform.apply_bond_style(b0, "bold", 1)
        transform.apply_bond_style(b1, "bold", 1)

        moved = QPointF(23.0, 4.0)
        canvas.model.atoms[a1].x = moved.x()
        canvas.model.atoms[a1].y = moved.y()
        update_bond_geometry_for(canvas, b0)
        update_bond_geometry_for(canvas, b1)

        def near_corners(bond_id):
            polygons = [item for item in bond_items_for_id(canvas, bond_id) if hasattr(item, "polygon")]
            self.assertEqual(len(polygons), 1)
            points = [polygons[0].mapToScene(point) for point in polygons[0].polygon()]
            return [p for p in points if math.hypot(p.x() - moved.x(), p.y() - moved.y()) < 8.0]

        corners0 = near_corners(b0)
        corners1 = near_corners(b1)
        self.assertEqual(len(corners0), 2)
        self.assertEqual(len(corners1), 2)
        for c0 in corners0:
            self.assertTrue(
                any(math.hypot(c0.x() - c1.x(), c0.y() - c1.y()) < 1e-6 for c1 in corners1),
                f"after update, bold strip corner ({c0.x()}, {c0.y()}) has no mitre partner",
            )

    def test_dotted_bond_tool_draws_new_bond_and_converts_plain_double_short_segment(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_bond_style("dotted", 1)
        self._drag_scene_point(QPointF(-40.0, 0.0), QPointF(40.0, 0.0))

        bond_id = next(i for i, bond in enumerate(active_canvas_for_window(self.window).model.bonds) if bond is not None)
        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual((bond.style, bond.order), ("dotted", 1))
        self.assertIsInstance(bond_items_for_id(active_canvas_for_window(self.window), bond_id)[0], QGraphicsPathItem)
        atom_a = active_canvas_for_window(self.window).model.atoms[bond.a]
        atom_b = active_canvas_for_window(self.window).model.atoms[bond.b]
        midpoint = QPointF((atom_a.x + atom_b.x) / 2.0, (atom_a.y + atom_b.y) / 2.0)

        active_canvas_for_window(self.window).services.scene_transform_controller.apply_bond_style(bond_id, "double", 2)
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_bond_style("dotted", 1)
        self._hover_scene_point(midpoint)
        self.assertEqual(hover_state_for(active_canvas_for_window(self.window)).bond_id, bond_id)
        self._click_scene_point(midpoint)

        bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertEqual((bond.style, bond.order), ("dotted_double", 2))
        bond_items = bond_items_for_id(active_canvas_for_window(self.window), bond_id)
        self.assertEqual(sum(isinstance(item, QGraphicsPathItem) for item in bond_items), 1)
        self.assertEqual(sum(not isinstance(item, QGraphicsPathItem) for item in bond_items), 1)

    def test_clicking_near_carbon_endpoint_prefers_atom_selection_over_bond(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0), QPointF(20.0, 0.0))

        carbon_dot = atom_dots_for(active_canvas_for_window(self.window))[0]
        self.assertEqual(carbon_dot.brush().color().alpha(), 0)

        self._click_scene_point(QPointF(3.0, 0.0))

        atom_ids, bond_ids = selected_ids_for(active_canvas_for_window(self.window))
        self.assertEqual(atom_ids, {0})
        self.assertEqual(bond_ids, set())
        self.assertTrue(selection_outlines_for(active_canvas_for_window(self.window)))
        max_width = max(item.sceneBoundingRect().width() for item in selection_outlines_for(active_canvas_for_window(self.window)))
        self.assertGreaterEqual(max_width, active_canvas_for_window(self.window).renderer.style.bond_length_px * 0.5)

    def test_explicit_atom_label_uses_circular_selection_indicator(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "P", 0.0, 0.0)
        add_or_update_atom_label(active_canvas_for_window(self.window), atom_id, "P", record=False)
        label = atom_items_for(active_canvas_for_window(self.window))[atom_id]

        self._select_atom_ids(atom_id)

        self.assertEqual(len(selection_outlines_for(active_canvas_for_window(self.window))), 1)
        rect = selection_outlines_for(active_canvas_for_window(self.window))[0].sceneBoundingRect()
        self.assertAlmostEqual(rect.width(), rect.height(), delta=0.5)
        hit_rect = label.shape().boundingRect()
        self.assertGreaterEqual(hit_rect.width(), atom_pick_radius_for(active_canvas_for_window(self.window)) * 2.0)

    def test_selected_atom_remains_hoverable_and_selected_when_dot_becomes_label(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        self._select_atom_ids(atom_id)

        add_or_update_atom_label(active_canvas_for_window(self.window), atom_id, "N", show_carbon=True, record=False)

        atom_ids, bond_ids = selected_ids_for(active_canvas_for_window(self.window))
        self.assertEqual(atom_ids, {atom_id})
        self.assertEqual(bond_ids, set())
        self.assertTrue(atom_items_for(active_canvas_for_window(self.window))[atom_id].isSelected())

        self._hover_scene_point(QPointF(40.0, 40.0))
        self._hover_scene_point(QPointF(0.0, 0.0))
        self.assertEqual(hover_state_for(active_canvas_for_window(self.window)).atom_id, atom_id)

    def test_selected_atom_remains_hoverable_and_selected_when_label_becomes_dot(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        atom_id = add_atom_for(active_canvas_for_window(self.window), "N", 0.0, 0.0)
        add_or_update_atom_label(active_canvas_for_window(self.window), atom_id, "N", record=False)
        self._select_atom_ids(atom_id)

        clear_atom_label_for(active_canvas_for_window(self.window), atom_id)

        atom_ids, bond_ids = selected_ids_for(active_canvas_for_window(self.window))
        self.assertEqual(atom_ids, {atom_id})
        self.assertEqual(bond_ids, set())
        self.assertTrue(atom_dots_for(active_canvas_for_window(self.window))[atom_id].isSelected())

        self._hover_scene_point(QPointF(40.0, 40.0))
        self._hover_scene_point(QPointF(0.0, 0.0))
        self.assertEqual(hover_state_for(active_canvas_for_window(self.window)).atom_id, atom_id)

    def test_clicking_left_side_of_ch3_label_selects_atom(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        add_or_update_atom_label(active_canvas_for_window(self.window), atom_id, "CH3", show_carbon=True, record=False)
        label = atom_items_for(active_canvas_for_window(self.window))[atom_id]
        rect = label.sceneBoundingRect()
        hit_rect = label.shape().boundingRect()
        self.assertGreater(hit_rect.width(), atom_pick_radius_for(active_canvas_for_window(self.window)) * 2.0)

        self._click_scene_point(QPointF(rect.left() + 1.0, rect.center().y()))

        atom_ids, bond_ids = selected_ids_for(active_canvas_for_window(self.window))
        self.assertEqual(atom_ids, {atom_id})
        self.assertEqual(bond_ids, set())

    def test_preferred_structure_item_on_labeled_atom_and_bond_prefers_atom(self) -> None:
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0), QPointF(20.0, 0.0))
        add_or_update_atom_label(active_canvas_for_window(self.window), 0, "P", record=False)

        item = active_canvas_for_window(self.window).services.selection_controller.preferred_structure_item_at_scene_pos(QPointF(4.0, 0.0))

        self.assertIsNotNone(item)
        self.assertEqual(item.data(0), "atom")

    def test_preferred_structure_item_near_ring_vertex_returns_atom(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        ring_atom_ids = ring_items_for(active_canvas_for_window(self.window))[0].data(2)
        self.assertIsInstance(ring_atom_ids, list)
        atom = active_canvas_for_window(self.window).model.atoms[ring_atom_ids[0]]

        item = active_canvas_for_window(self.window).services.selection_controller.preferred_structure_item_at_scene_pos(
            QPointF(atom.x + 1.0, atom.y + 1.0)
        )

        self.assertIsNotNone(item)
        self.assertEqual(item.data(0), "atom")
        self.assertEqual(item.data(1), ring_atom_ids[0])

    def test_hover_on_labeled_atom_and_bond_prefers_atom(self) -> None:
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0), QPointF(20.0, 0.0))
        add_or_update_atom_label(active_canvas_for_window(self.window), 0, "P", record=False)

        update_hover_highlight_for(active_canvas_for_window(self.window), QPointF(4.0, 0.0))

        self.assertEqual(hover_state_for(active_canvas_for_window(self.window)).atom_id, 0)
        self.assertIsNone(hover_state_for(active_canvas_for_window(self.window)).bond_id)

    def test_clicking_visible_left_side_of_compact_label_connected_bond_selects_atom(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        left = add_atom_for(active_canvas_for_window(self.window), "N", 0.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 20.0, 0.0)
        add_or_update_atom_label(active_canvas_for_window(self.window), left, "N", record=False)
        add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)
        label = atom_items_for(active_canvas_for_window(self.window))[left]
        rect = label.sceneBoundingRect()

        self._click_scene_point(QPointF(rect.left() + 1.0, rect.center().y()))

        atom_ids, bond_ids = selected_ids_for(active_canvas_for_window(self.window))
        self.assertEqual(atom_ids, {left})
        self.assertEqual(bond_ids, set())

    def test_hover_near_ring_vertex_prefers_atom(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        ring_atom_ids = ring_items_for(active_canvas_for_window(self.window))[0].data(2)
        self.assertIsInstance(ring_atom_ids, list)
        target_atom_id = ring_atom_ids[0]
        atom = active_canvas_for_window(self.window).model.atoms[target_atom_id]

        update_hover_highlight_for(active_canvas_for_window(self.window), QPointF(atom.x + 1.0, atom.y + 1.0))

        self.assertEqual(hover_state_for(active_canvas_for_window(self.window)).atom_id, target_atom_id)
        self.assertIsNone(hover_state_for(active_canvas_for_window(self.window)).bond_id)

    def test_benzene_ring_carbons_have_selectable_atom_dots(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        ring_atom_ids = ring_items_for(active_canvas_for_window(self.window))[0].data(2)

        self.assertIsInstance(ring_atom_ids, list)
        first_atom_id = ring_atom_ids[0]
        self.assertIn(first_atom_id, atom_dots_for(active_canvas_for_window(self.window)))

        atom = active_canvas_for_window(self.window).model.atoms[first_atom_id]
        self._hover_scene_point(QPointF(atom.x, atom.y))
        self._click_scene_point(QPointF(atom.x, atom.y))

        atom_ids, bond_ids = selected_ids_for(active_canvas_for_window(self.window))
        self.assertEqual(atom_ids, {first_atom_id})
        self.assertEqual(bond_ids, set())

    def test_multi_atom_selection_adds_component_overlay_without_center_marker(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -10.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 10.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)

        self._select_atom_ids(left, right)

        kinds = [item.data(2) or {} for item in selection_outlines_for(active_canvas_for_window(self.window))]
        self.assertEqual(sum(1 for data in kinds if data.get("kind") == "component"), 1)
        self.assertEqual(sum(1 for data in kinds if data.get("kind") == "center"), 0)
        self.assertTrue(all(data.get("kind") == "component" for data in kinds))
        component_outline = next(
            item
            for item in selection_outlines_for(active_canvas_for_window(self.window))
            if (item.data(2) or {}).get("kind") == "component"
        )
        self.assertEqual(component_outline.path().fillRule(), Qt.FillRule.WindingFill)
        self.assertEqual(component_outline.brush().color().name(), "#0d9488")

    def test_disconnected_atom_selection_adds_multiple_component_overlays(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -40.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 40.0, 0.0)

        self._select_atom_ids(left, right)

        component_outlines = [
            item
            for item in selection_outlines_for(active_canvas_for_window(self.window))
            if (item.data(2) or {}).get("kind") == "component"
        ]
        self.assertEqual(len(component_outlines), 2)
        self.assertFalse(any((item.data(2) or {}).get("kind") == "center" for item in selection_outlines_for(active_canvas_for_window(self.window))))

    def test_clearing_selection_removes_selection_outlines(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -10.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 10.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)

        self._select_atom_ids(left, right)
        self.assertTrue(selection_outlines_for(active_canvas_for_window(self.window)))

        active_canvas_for_window(self.window).scene().clearSelection()

        self.assertEqual(selection_outlines_for(active_canvas_for_window(self.window)), [])

    def test_arrow_selection_uses_filled_object_overlay(self) -> None:
        arrow = add_arrow_for(active_canvas_for_window(self.window), QPointF(-40.0, 0.0), QPointF(20.0, 20.0), "arrow")

        self._select_items(arrow)

        object_outlines = [
            item
            for item in selection_outlines_for(active_canvas_for_window(self.window))
            if (item.data(2) or {}).get("kind") == "object"
        ]
        self.assertEqual(len(object_outlines), 1)
        outline = object_outlines[0]
        self.assertEqual(outline.brush().color().name(), "#0d9488")
        self.assertGreater(outline.brush().color().alpha(), 0)
        self.assertEqual(outline.pen().style(), Qt.PenStyle.NoPen)

    def test_mark_and_ts_bracket_selection_use_filled_object_overlays(self) -> None:
        mark = add_mark_for(active_canvas_for_window(self.window), QPointF(10.0, 10.0), kind="plus")
        ts_bracket = add_ts_bracket_for(active_canvas_for_window(self.window), QRectF(QPointF(30.0, -20.0), QPointF(80.0, 30.0)))

        self._select_items(mark, ts_bracket)

        object_outlines = [
            item
            for item in selection_outlines_for(active_canvas_for_window(self.window))
            if (item.data(2) or {}).get("kind") == "object"
        ]
        self.assertEqual(len(object_outlines), 2)
        self.assertTrue(all(item.brush().color().name() == "#0d9488" for item in object_outlines))
        self.assertTrue(all(item.pen().style() == Qt.PenStyle.NoPen for item in object_outlines))

    def test_mark_selection_overlay_matches_single_atom_selection_radius(self) -> None:
        plus = add_mark_for(active_canvas_for_window(self.window), QPointF(-20.0, 10.0), kind="plus")
        minus = add_mark_for(active_canvas_for_window(self.window), QPointF(0.0, 10.0), kind="minus")
        radical = add_mark_for(active_canvas_for_window(self.window), QPointF(20.0, 10.0), kind="radical")
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 60.0, 10.0)

        self._select_items(plus, minus, radical)

        object_outlines = [
            item
            for item in selection_outlines_for(active_canvas_for_window(self.window))
            if (item.data(2) or {}).get("kind") == "object"
        ]
        self.assertEqual(len(object_outlines), 3)
        expected_rect = selection_indicator_rect_for_atom_for(active_canvas_for_window(self.window), atom_id)
        self.assertIsNotNone(expected_rect)
        for outline in object_outlines:
            bounds = outline.path().boundingRect()
            self.assertAlmostEqual(bounds.width(), expected_rect.width(), delta=0.5)
            self.assertAlmostEqual(bounds.height(), expected_rect.height(), delta=0.5)

    def test_perspective_tool_toggles_center_marker_for_multi_atom_selection(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -10.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 10.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)

        self._select_atom_ids(left, right)
        self.assertFalse(any((item.data(2) or {}).get("kind") == "center" for item in selection_outlines_for(active_canvas_for_window(self.window))))

        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("perspective")

        self.assertEqual(
            sum(1 for item in selection_outlines_for(active_canvas_for_window(self.window)) if (item.data(2) or {}).get("kind") == "center"),
            2,
        )

        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")

        self.assertFalse(any((item.data(2) or {}).get("kind") == "center" for item in selection_outlines_for(active_canvas_for_window(self.window))))

    def test_selection_hit_test_ignores_center_marker_for_disconnected_selection(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -50.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 50.0, 0.0)

        self._select_atom_ids(left, right)
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("perspective")

        center_markers = [
            item
            for item in selection_outlines_for(active_canvas_for_window(self.window))
            if (item.data(2) or {}).get("kind") == "center"
        ]
        self.assertEqual(len(center_markers), 2)
        self.assertFalse(active_canvas_for_window(self.window).services.selection_controller.selection_hit_test(QPointF(0.0, 0.0)))

    def test_ring_double_bond_selection_overlay_tracks_outer_bond_line(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        ring_atom_ids = ring_items_for(active_canvas_for_window(self.window))[0].data(2)

        self.assertIsInstance(ring_atom_ids, list)
        self._select_atom_ids(*ring_atom_ids)

        outer_mid = None
        inner_mid = None
        overlay_center = None
        for bond_id, items in bond_items_for(active_canvas_for_window(self.window)).items():
            if len(items) < 2 or not all(hasattr(item, "line") for item in items):
                continue
            first = items[0].line()
            second = items[1].line()
            outer_mid = QPointF((first.x1() + first.x2()) * 0.5, (first.y1() + first.y2()) * 0.5)
            inner_mid = QPointF((second.x1() + second.x2()) * 0.5, (second.y1() + second.y2()) * 0.5)
            overlay_center = active_canvas_for_window(self.window).services.selection_controller.selection_path_for_bond(bond_id).boundingRect().center()
            break
        self.assertIsNotNone(outer_mid)
        self.assertIsNotNone(inner_mid)
        self.assertIsNotNone(overlay_center)
        outer_distance = (overlay_center - outer_mid).manhattanLength()
        inner_distance = (overlay_center - inner_mid).manhattanLength()
        self.assertLess(outer_distance, inner_distance)

    def test_double_bond_selection_path_uses_single_bond_width(self) -> None:
        single_left = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 0.0)
        single_right = add_atom_for(active_canvas_for_window(self.window), "C", 20.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), single_left, single_right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)

        double_left = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 30.0)
        double_right = add_atom_for(active_canvas_for_window(self.window), "C", 20.0, 30.0)
        add_bond_for(active_canvas_for_window(self.window), double_left, double_right, order=2)
        add_bond_graphics_for(active_canvas_for_window(self.window), 1)

        single_rect = active_canvas_for_window(self.window).services.selection_controller.selection_path_for_bond(0).boundingRect()
        double_rect = active_canvas_for_window(self.window).services.selection_controller.selection_path_for_bond(1).boundingRect()

        self.assertAlmostEqual(single_rect.height(), double_rect.height(), delta=0.5)

    def test_selection_path_for_moved_bond_item_uses_scene_coordinates(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 20.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)

        move_atoms_for(
            active_canvas_for_window(self.window),
            {left, right},
            75.0,
            35.0,
            bond_ids={0},
            redraw_bond_ids=set(),
            update_selection=False,
        )

        bond_item = bond_items_for_id(active_canvas_for_window(self.window), 0)[0]
        path_rect = active_canvas_for_window(self.window).services.selection_controller.selection_path_for_bond_item(bond_item).boundingRect()
        bond_rect = bond_item.sceneBoundingRect()

        self.assertAlmostEqual(path_rect.center().x(), bond_rect.center().x(), delta=0.5)
        self.assertAlmostEqual(path_rect.center().y(), bond_rect.center().y(), delta=0.5)

    def test_dragging_double_bond_endpoint_after_fragment_move_keeps_geometry_and_undo(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "P", 0.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "O", 40.0, 0.0)
        bond_id = add_bond_for(active_canvas_for_window(self.window), left, right, order=2)
        add_bond_graphics_for(active_canvas_for_window(self.window), bond_id)

        move_atoms_for(
            active_canvas_for_window(self.window),
            {left, right},
            100.0,
            50.0,
            bond_ids={bond_id},
            redraw_bond_ids=set(),
            update_selection=False,
        )
        before_segments = self._bond_scene_segments(bond_id)
        self.assertEqual(len(before_segments), 2)
        self.assertTrue(
            any(
                abs(item.pos().x()) > 1e-6 or abs(item.pos().y()) > 1e-6
                for item in bond_items_for_id(active_canvas_for_window(self.window), bond_id)
            )
        )

        move_atoms_for(
            active_canvas_for_window(self.window),
            {right},
            20.0,
            30.0,
            bond_ids=set(),
            redraw_bond_ids={bond_id},
            update_selection=False,
        )
        active_canvas_for_window(self.window).runtime_state.history_service.push(
            MoveAtomsCommand(
                atom_ids={right},
                dx=20.0,
                dy=30.0,
                bond_ids=set(),
                redraw_bond_ids={bond_id},
            )
        )

        moved_atom_left = active_canvas_for_window(self.window).model.atoms[left]
        moved_atom_right = active_canvas_for_window(self.window).model.atoms[right]
        bond_mid_x = (moved_atom_left.x + moved_atom_right.x) * 0.5
        bond_mid_y = (moved_atom_left.y + moved_atom_right.y) * 0.5
        after_segments = self._bond_scene_segments(bond_id)
        self.assertEqual(len(after_segments), 2)
        for item in bond_items_for_id(active_canvas_for_window(self.window), bond_id):
            self.assertAlmostEqual(item.pos().x(), 0.0, delta=1e-6)
            self.assertAlmostEqual(item.pos().y(), 0.0, delta=1e-6)
        for x1, y1, x2, y2 in after_segments:
            self.assertLess(math.hypot(((x1 + x2) * 0.5) - bond_mid_x, ((y1 + y2) * 0.5) - bond_mid_y), 8.0)

        active_canvas_for_window(self.window).runtime_state.history_service.undo()

        undone_segments = self._bond_scene_segments(bond_id)
        self.assertEqual(len(undone_segments), len(before_segments))
        for (ax1, ay1, ax2, ay2), (bx1, by1, bx2, by2) in zip(undone_segments, before_segments, strict=False):
            self.assertAlmostEqual(ax1, bx1, delta=0.01)
            self.assertAlmostEqual(ay1, by1, delta=0.01)
            self.assertAlmostEqual(ax2, bx2, delta=0.01)
            self.assertAlmostEqual(ay2, by2, delta=0.01)

    def test_clicking_near_bond_selects_bond(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        left = add_atom_for(active_canvas_for_window(self.window), "C", -10.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 10.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)

        self._click_scene_point(QPointF(0.0, 3.5))

        atom_ids, bond_ids = selected_ids_for(active_canvas_for_window(self.window))
        self.assertEqual(atom_ids, set())
        self.assertEqual(bond_ids, {0})

    def test_preferred_structure_item_outside_labeled_atom_toward_bond_prefers_bond(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "N", 0.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 20.0, 0.0)
        add_or_update_atom_label(active_canvas_for_window(self.window), left, "N", record=False)
        add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)
        label = atom_items_for(active_canvas_for_window(self.window))[left]
        rect = label.sceneBoundingRect()

        item = active_canvas_for_window(self.window).services.selection_controller.preferred_structure_item_at_scene_pos(
            QPointF(rect.right() + 1.0, rect.center().y())
        )

        self.assertIsNotNone(item)
        self.assertEqual(item.data(0), "bond")

    def test_select_tool_drag_context_matches_selection_hit_test_for_selected_bond_endpoints(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        left = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "C", 20.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)

        self._select_items(*bond_items_for_id(active_canvas_for_window(self.window), 0))

        select_tool = active_canvas_for_window(self.window).services.tools.tools["select"]
        atom_ids, selection_items = select_tool._selection_drag_context()

        self.assertEqual(atom_ids, {left, right})
        self.assertTrue(selection_items)
        self.assertEqual({item.data(1) for item in selection_items}, {0})

        left_atom = active_canvas_for_window(self.window).model.atoms[left]
        right_atom = active_canvas_for_window(self.window).model.atoms[right]
        self.assertIsNotNone(left_atom)
        self.assertIsNotNone(right_atom)
        self.assertTrue(active_canvas_for_window(self.window).services.selection_controller.selection_hit_test(QPointF(left_atom.x, left_atom.y)))
        self.assertTrue(active_canvas_for_window(self.window).services.selection_controller.selection_hit_test(QPointF(right_atom.x, right_atom.y)))

    def test_select_tool_drag_context_limits_selected_arrow_hit_to_arrow_path(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        arrow = add_arrow_for(active_canvas_for_window(self.window), QPointF(-40.0, 0.0), QPointF(20.0, 20.0), "arrow")

        self._select_items(arrow)

        select_tool = active_canvas_for_window(self.window).services.tools.tools["select"]
        atom_ids, selection_items = select_tool._selection_drag_context()

        self.assertEqual(atom_ids, set())
        self.assertEqual(selection_items, [arrow])

        rect = arrow.sceneBoundingRect()
        interior_point = QPointF(rect.left() + 6.0, rect.bottom() - 6.0)
        self.assertIsNone(active_canvas_for_window(self.window).services.hit_testing_service.item_at_scene_pos(interior_point))
        self.assertFalse(active_canvas_for_window(self.window).services.selection_controller.selection_hit_test(interior_point))

        data = arrow.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        near_path_point = QPointF((start.x() + end.x()) * 0.5, (start.y() + end.y()) * 0.5)
        self.assertTrue(active_canvas_for_window(self.window).services.selection_controller.selection_hit_test(near_path_point))

    def test_select_tool_drag_moves_mixed_structure_and_arrow_selection(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        atom_item = visible_atom_item_for(active_canvas_for_window(self.window), atom_id)
        self.assertIsNotNone(atom_item)
        arrow = add_arrow_for(active_canvas_for_window(self.window), QPointF(30.0, -10.0), QPointF(70.0, 10.0), "arrow")

        self._select_items(atom_item, arrow)

        atom_before = active_canvas_for_window(self.window).model.atoms[atom_id]
        self.assertIsNotNone(atom_before)
        atom_before_x = atom_before.x
        atom_before_y = atom_before.y
        arrow_before = dict(arrow.data(2) or {})

        self._drag_scene_point(QPointF(atom_before_x, atom_before_y), QPointF(atom_before_x + 24.0, atom_before_y + 12.0))

        atom_after = active_canvas_for_window(self.window).model.atoms[atom_id]
        self.assertAlmostEqual(atom_after.x, atom_before_x + 24.0, places=3)
        self.assertAlmostEqual(atom_after.y, atom_before_y + 12.0, places=3)

        moved_arrow = arrow.data(2) or {}
        self.assertAlmostEqual(moved_arrow["start"].x(), arrow_before["start"].x() + 24.0, places=3)
        self.assertAlmostEqual(moved_arrow["start"].y(), arrow_before["start"].y() + 12.0, places=3)
        self.assertAlmostEqual(moved_arrow["end"].x(), arrow_before["end"].x() + 24.0, places=3)
        self.assertAlmostEqual(moved_arrow["end"].y(), arrow_before["end"].y() + 12.0, places=3)

        active_canvas_for_window(self.window).runtime_state.history_service.undo()

        atom_undone = active_canvas_for_window(self.window).model.atoms[atom_id]
        self.assertAlmostEqual(atom_undone.x, atom_before_x, places=3)
        self.assertAlmostEqual(atom_undone.y, atom_before_y, places=3)
        undone_arrow = arrow.data(2) or {}
        self.assertAlmostEqual(undone_arrow["start"].x(), arrow_before["start"].x(), places=3)
        self.assertAlmostEqual(undone_arrow["start"].y(), arrow_before["start"].y(), places=3)
        self.assertAlmostEqual(undone_arrow["end"].x(), arrow_before["end"].x(), places=3)
        self.assertAlmostEqual(undone_arrow["end"].y(), arrow_before["end"].y(), places=3)

    def test_copy_paste_duplicates_molecule_and_arrow_selection(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "O", 20.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)
        arrow = add_arrow_for(active_canvas_for_window(self.window), QPointF(40.0, -5.0), QPointF(90.0, 15.0), "arrow")

        self._select_items(*bond_items_for_id(active_canvas_for_window(self.window), 0), arrow)

        self.assertTrue(
            active_canvas_for_window(self.window).services.scene_clipboard_controller.copy_selection_to_clipboard()
        )
        self.assertTrue(
            active_canvas_for_window(self.window).services.scene_clipboard_controller.paste_selection_from_clipboard()
        )

        self.assertEqual(len(active_canvas_for_window(self.window).model.atoms), 4)
        self.assertEqual(sum(1 for bond in active_canvas_for_window(self.window).model.bonds if bond is not None), 2)
        self.assertEqual(len(arrow_items_for(active_canvas_for_window(self.window))), 2)

        paste_dx = paste_dy = max(18.0, active_canvas_for_window(self.window).renderer.style.bond_length_px * 0.35)
        new_atom_ids = sorted(atom_id for atom_id in active_canvas_for_window(self.window).model.atoms if atom_id not in {left, right})
        self.assertEqual(len(new_atom_ids), 2)

        original_positions = sorted(
            [
                (active_canvas_for_window(self.window).model.atoms[left].x, active_canvas_for_window(self.window).model.atoms[left].y),
                (active_canvas_for_window(self.window).model.atoms[right].x, active_canvas_for_window(self.window).model.atoms[right].y),
            ]
        )
        pasted_positions = sorted(
            [
                (active_canvas_for_window(self.window).model.atoms[new_atom_ids[0]].x, active_canvas_for_window(self.window).model.atoms[new_atom_ids[0]].y),
                (active_canvas_for_window(self.window).model.atoms[new_atom_ids[1]].x, active_canvas_for_window(self.window).model.atoms[new_atom_ids[1]].y),
            ]
        )
        for (orig_x, orig_y), (pasted_x, pasted_y) in zip(original_positions, pasted_positions, strict=False):
            self.assertAlmostEqual(pasted_x, orig_x + paste_dx, places=3)
            self.assertAlmostEqual(pasted_y, orig_y + paste_dy, places=3)

        pasted_arrow = arrow_items_for(active_canvas_for_window(self.window))[-1]
        pasted_arrow_data = pasted_arrow.data(2) or {}
        original_arrow_data = arrow.data(2) or {}
        self.assertAlmostEqual(pasted_arrow_data["start"].x(), original_arrow_data["start"].x() + paste_dx, places=3)
        self.assertAlmostEqual(pasted_arrow_data["start"].y(), original_arrow_data["start"].y() + paste_dy, places=3)
        self.assertAlmostEqual(pasted_arrow_data["end"].x(), original_arrow_data["end"].x() + paste_dx, places=3)
        self.assertAlmostEqual(pasted_arrow_data["end"].y(), original_arrow_data["end"].y() + paste_dy, places=3)

        active_canvas_for_window(self.window).runtime_state.history_service.undo()

        self.assertEqual(len(active_canvas_for_window(self.window).model.atoms), 2)
        self.assertEqual(sum(1 for bond in active_canvas_for_window(self.window).model.bonds if bond is not None), 1)
        self.assertEqual(len(arrow_items_for(active_canvas_for_window(self.window))), 1)

    def test_copy_paste_benzene_preserves_inner_double_bond_orientation(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        original_ring = ring_items_for(active_canvas_for_window(self.window))[0]
        self._assert_ring_double_bonds_face_inward(original_ring)

        self._select_items(original_ring)
        self.assertTrue(
            active_canvas_for_window(self.window).services.scene_clipboard_controller.copy_selection_to_clipboard()
        )
        self.assertTrue(
            active_canvas_for_window(self.window).services.scene_clipboard_controller.paste_selection_from_clipboard()
        )

        pasted_ring = ring_items_for(active_canvas_for_window(self.window))[-1]
        self._assert_ring_double_bonds_face_inward(pasted_ring)

        active_canvas_for_window(self.window).runtime_state.history_service.undo()
        self.assertEqual(len(ring_items_for(active_canvas_for_window(self.window))), 1)

        active_canvas_for_window(self.window).runtime_state.history_service.redo()
        self.assertEqual(len(ring_items_for(active_canvas_for_window(self.window))), 2)
        self._assert_ring_double_bonds_face_inward(ring_items_for(active_canvas_for_window(self.window))[-1])

    def test_delete_selected_items_atom_bound_mark_and_arrow_undo_restores_everything(self) -> None:
        atom_a = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 0.0)
        atom_b = add_atom_for(active_canvas_for_window(self.window), "O", 20.0, 0.0)
        bond_id = add_bond_for(active_canvas_for_window(self.window), atom_a, atom_b)
        add_bond_graphics_for(active_canvas_for_window(self.window), bond_id)
        mark = add_mark_for_atom_for(active_canvas_for_window(self.window), atom_a, QPointF(-12.0, -8.0), kind="minus", record=False)
        arrow = add_arrow_for(active_canvas_for_window(self.window), QPointF(40.0, -5.0), QPointF(90.0, 15.0), "arrow")
        atom_item = visible_atom_item_for(active_canvas_for_window(self.window), atom_a)
        self.assertIsNotNone(atom_item)
        self.assertIsNotNone(mark)
        original_mark_state = scene_item_state_for(active_canvas_for_window(self.window), mark)

        self._select_items(atom_item, mark, arrow)

        self.assertTrue(active_canvas_for_window(self.window).services.scene_delete_controller.delete_selected_items())
        self.assertNotIn(atom_a, active_canvas_for_window(self.window).model.atoms)
        self.assertEqual(sum(1 for bond in active_canvas_for_window(self.window).model.bonds if bond is not None), 0)
        self.assertEqual(len(arrow_items_for(active_canvas_for_window(self.window))), 0)
        self.assertEqual(len(mark_items_for(active_canvas_for_window(self.window))), 0)
        self.assertFalse(mark_registry_for(active_canvas_for_window(self.window)).by_atom.get(atom_a))

        active_canvas_for_window(self.window).runtime_state.history_service.undo()

        self.assertIn(atom_a, active_canvas_for_window(self.window).model.atoms)
        self.assertIn(atom_b, active_canvas_for_window(self.window).model.atoms)
        self.assertEqual(sum(1 for bond in active_canvas_for_window(self.window).model.bonds if bond is not None), 1)
        self.assertEqual(len(arrow_items_for(active_canvas_for_window(self.window))), 1)
        self.assertIn(arrow, arrow_items_for(active_canvas_for_window(self.window)))
        restored_marks = mark_registry_for(active_canvas_for_window(self.window)).by_atom.get(atom_a, [])
        self.assertEqual(len(restored_marks), 1)
        self.assertEqual(scene_item_state_for(active_canvas_for_window(self.window), restored_marks[0]), original_mark_state)
        self.assertIn(restored_marks[0], mark_items_for(active_canvas_for_window(self.window)))

    def test_delete_selected_items_single_bond_preserves_atoms_and_undo_restores_bond(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "O", 20.0, 0.0)
        bond_id = add_bond_for(active_canvas_for_window(self.window), left, right)
        add_bond_graphics_for(active_canvas_for_window(self.window), bond_id)
        bond_item = bond_items_for_id(active_canvas_for_window(self.window), bond_id)[0]

        self._select_items(bond_item)

        self.assertTrue(active_canvas_for_window(self.window).services.scene_delete_controller.delete_selected_items())
        self.assertEqual(set(active_canvas_for_window(self.window).model.atoms), {left, right})
        self.assertIsNone(active_canvas_for_window(self.window).model.bonds[bond_id])
        self.assertFalse(bond_items_for_id(active_canvas_for_window(self.window), bond_id))

        active_canvas_for_window(self.window).runtime_state.history_service.undo()

        restored_bond = active_canvas_for_window(self.window).model.bonds[bond_id]
        self.assertIsNotNone(restored_bond)
        assert restored_bond is not None
        self.assertEqual((restored_bond.a, restored_bond.b), (left, right))
        self.assertTrue(bond_items_for_id(active_canvas_for_window(self.window), bond_id))

    def test_color_preset_preserves_ring_fill_on_selected_ring(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        ring_item = ring_items_for(active_canvas_for_window(self.window))[0]
        ring_atom_ids = ring_item.data(2)

        active_canvas_for_window(self.window).scene().clearSelection()
        ring_item.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

        fill_color = "#f4d06f"
        stroke_color = "#2f6ed3"
        services_for_window(self.window).tool_routing_service.apply_ring_fill_preset(self.window, fill_color)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(ring_item.brush().color().name(), fill_color)

        services_for_window(self.window).tool_routing_service.apply_color_preset(self.window, stroke_color)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(ring_item.brush().color().name(), fill_color)
        self.assertIsInstance(ring_atom_ids, list)
        for atom_id in ring_atom_ids:
            self.assertEqual(active_canvas_for_window(self.window).model.atoms[atom_id].color, stroke_color)

    def test_object_shortcuts_flip_selected_structures_in_place(self) -> None:
        left_a = add_atom_for(active_canvas_for_window(self.window), "C", -60.0, 0.0)
        right_a = add_atom_for(active_canvas_for_window(self.window), "O", -20.0, 20.0)
        add_bond_for(active_canvas_for_window(self.window), left_a, right_a)

        left_b = add_atom_for(active_canvas_for_window(self.window), "N", 40.0, 10.0)
        right_b = add_atom_for(active_canvas_for_window(self.window), "S", 80.0, 30.0)
        add_bond_for(active_canvas_for_window(self.window), left_b, right_b)

        untouched_left = add_atom_for(active_canvas_for_window(self.window), "F", 140.0, -10.0)
        untouched_right = add_atom_for(active_canvas_for_window(self.window), "Cl", 180.0, 10.0)
        add_bond_for(active_canvas_for_window(self.window), untouched_left, untouched_right)

        self._select_atom_ids(left_a, right_a, left_b, right_b)

        self._press_key(Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[left_a].x, -20.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[right_a].x, -60.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[left_a].y, 0.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[right_a].y, 20.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[left_b].x, 80.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[right_b].x, 40.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[left_b].y, 10.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[right_b].y, 30.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[untouched_left].x, 140.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[untouched_right].x, 180.0)

        self._press_key(Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[left_a].x, -20.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[right_a].x, -60.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[left_a].y, 20.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[right_a].y, 0.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[left_b].x, 80.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[right_b].x, 40.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[left_b].y, 30.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[right_b].y, 10.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[untouched_left].x, 140.0)
        self.assertAlmostEqual(active_canvas_for_window(self.window).model.atoms[untouched_right].x, 180.0)

    def test_object_shortcuts_flip_selected_arrow(self) -> None:
        arrow = add_arrow_for(active_canvas_for_window(self.window), QPointF(-40.0, 0.0), QPointF(20.0, 20.0), "arrow")
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
        left_id = add_atom_for(active_canvas_for_window(self.window), "C", -80.0, 0.0)
        center_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        right_id = add_atom_for(active_canvas_for_window(self.window), "C", 80.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left_id, center_id)
        add_bond_for(active_canvas_for_window(self.window), center_id, right_id)
        active_canvas_for_window(self.window).services.structure_build_service.render_model()

        self._select_atom_ids(left_id, center_id, right_id)

        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 20.0),
        )

        self.assertTrue(rotating)
        rotation_state = rotation_state_for(active_canvas_for_window(self.window))
        self.assertEqual(rotation_state.mode, "rigid")
        self.assertEqual(rotation_state.atom_ids, {left_id, center_id, right_id})
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

    def test_perspective_rotation_without_axis_hint_uses_rigid_mode_for_partial_selection(self) -> None:
        left_id = add_atom_for(active_canvas_for_window(self.window), "C", -80.0, 0.0)
        center_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        right_id = add_atom_for(active_canvas_for_window(self.window), "C", 80.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left_id, center_id)
        add_bond_for(active_canvas_for_window(self.window), center_id, right_id)
        active_canvas_for_window(self.window).services.structure_build_service.render_model()

        self._select_atom_ids(center_id, right_id)

        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(40.0, 20.0),
        )

        self.assertTrue(rotating)
        rotation_state = rotation_state_for(active_canvas_for_window(self.window))
        self.assertEqual(rotation_state.mode, "rigid")
        self.assertEqual(rotation_state.atom_ids, {center_id, right_id})
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

    def test_perspective_tool_press_on_selected_atom_keeps_partial_selection_rigid(self) -> None:
        left_id = add_atom_for(active_canvas_for_window(self.window), "C", -80.0, 0.0)
        center_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        right_id = add_atom_for(active_canvas_for_window(self.window), "C", 80.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left_id, center_id)
        add_bond_for(active_canvas_for_window(self.window), center_id, right_id)
        active_canvas_for_window(self.window).services.structure_build_service.render_model()

        self._select_atom_ids(center_id, right_id)
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("perspective")

        viewport_pos = active_canvas_for_window(self.window).mapFromScene(QPointF(80.0, 0.0))
        QTest.mousePress(
            active_canvas_for_window(self.window).viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

        rotation_state = rotation_state_for(active_canvas_for_window(self.window))
        self.assertEqual(rotation_state.mode, "rigid")
        self.assertEqual(rotation_state.atom_ids, {center_id, right_id})

        QTest.mouseRelease(
            active_canvas_for_window(self.window).viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def test_perspective_rotation_on_partial_selection_prefers_selected_side_for_axis_hint(self) -> None:
        left_id = add_atom_for(active_canvas_for_window(self.window), "C", -80.0, 0.0)
        center_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        right_id = add_atom_for(active_canvas_for_window(self.window), "C", 80.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left_id, center_id)
        bond_id = add_bond_for(active_canvas_for_window(self.window), center_id, right_id)
        active_canvas_for_window(self.window).services.structure_build_service.render_model()

        self._select_atom_ids(center_id, right_id)

        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            axis_hint=bond_id,
            press_pos=QPointF(0.0, 0.0),
        )

        self.assertTrue(rotating)
        rotation_state = rotation_state_for(active_canvas_for_window(self.window))
        self.assertEqual(rotation_state.mode, "bond")
        self.assertEqual(rotation_state.atom_ids, {right_id})
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

    def test_perspective_rigid_rotation_uses_bounding_box_center(self) -> None:
        left_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        center_id = add_atom_for(active_canvas_for_window(self.window), "C", 10.0, 20.0)
        right_id = add_atom_for(active_canvas_for_window(self.window), "C", 100.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left_id, center_id)
        add_bond_for(active_canvas_for_window(self.window), center_id, right_id)
        active_canvas_for_window(self.window).services.structure_build_service.render_model()

        self._select_atom_ids(left_id, center_id, right_id)

        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(40.0, 10.0),
        )

        self.assertTrue(rotating)
        rotation_state = rotation_state_for(active_canvas_for_window(self.window))
        self.assertEqual(rotation_state.mode, "rigid")
        self.assertEqual(rotation_state.center_3d, (50.0, 10.0, 0.0))
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

    def test_perspective_rotation_foreshortens_depth_in_screen_space(self) -> None:
        left_id = add_atom_for(active_canvas_for_window(self.window), "C", -80.0, 0.0)
        center_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        right_id = add_atom_for(active_canvas_for_window(self.window), "C", 80.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left_id, center_id)
        add_bond_for(active_canvas_for_window(self.window), center_id, right_id)
        active_canvas_for_window(self.window).services.structure_build_service.render_model()

        self._select_atom_ids(left_id, center_id, right_id)
        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 0.0),
        )
        self.assertTrue(rotating)

        active_canvas_for_window(self.window).services.selection_rotation_controller.update_selection_3d_rotation(200.0, 0.0)

        center_x = active_canvas_for_window(self.window).model.atoms[center_id].x
        left_dist = center_x - active_canvas_for_window(self.window).model.atoms[left_id].x
        right_dist = active_canvas_for_window(self.window).model.atoms[right_id].x - center_x
        self.assertGreater(abs(left_dist - right_dist), 5.0)
        atom_coords_3d = atom_coords_3d_for(active_canvas_for_window(self.window))
        left_z = atom_coords_3d[left_id][2]
        right_z = atom_coords_3d[right_id][2]
        self.assertGreater(abs(left_z), 1.0)
        self.assertGreater(abs(right_z), 1.0)
        self.assertLess(left_z * right_z, 0.0)
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

    def test_select_drag_after_perspective_rebuilds_selection_overlay_at_current_position(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        ring_atom_ids = ring_items_for(active_canvas_for_window(self.window))[0].data(2)
        self.assertIsInstance(ring_atom_ids, list)

        self._select_atom_ids(*ring_atom_ids)
        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("perspective")
        self._drag_scene_point(QPointF(0.0, 20.0), QPointF(120.0, 100.0))

        old_component = next(
            item
            for item in selection_outlines_for(active_canvas_for_window(self.window))
            if (item.data(2) or {}).get("kind") == "component"
        )
        old_center = old_component.sceneBoundingRect().center()

        canvas_services_for(active_canvas_for_window(self.window)).tool_mode_controller.set_tool("select")
        self._drag_scene_point(QPointF(0.0, 0.0), QPointF(100.0, 60.0))

        components = [
            item
            for item in selection_outlines_for(active_canvas_for_window(self.window))
            if (item.data(2) or {}).get("kind") == "component"
        ]
        self.assertEqual(len(components), 1)
        self.assertFalse(components[0].path().contains(old_center))
        self.assertFalse(components[0].sceneBoundingRect().contains(old_center))

    def test_perspective_rotated_benzene_double_bonds_follow_ring_plane(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        ring_atom_ids = ring_items_for(active_canvas_for_window(self.window))[0].data(2)
        self.assertIsInstance(ring_atom_ids, list)
        self._select_atom_ids(*ring_atom_ids)

        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 20.0),
        )
        self.assertTrue(rotating)

        active_canvas_for_window(self.window).services.selection_rotation_controller.update_selection_3d_rotation(220.0, 160.0)

        checked = 0
        for bond_id, items in bond_items_for(active_canvas_for_window(self.window)).items():
            if len(items) < 2 or not all(hasattr(item, "line") for item in items[:2]):
                continue
            bond = active_canvas_for_window(self.window).model.bonds[bond_id]
            if bond is None or bond.order != 2:
                continue
            center_3d = ring_center_3d_for_bond_for(active_canvas_for_window(self.window), bond)
            self.assertIsNotNone(center_3d)
            atom_coords_3d = atom_coords_3d_for(active_canvas_for_window(self.window))
            coords_a = atom_coords_3d.get(bond.a)
            coords_b = atom_coords_3d.get(bond.b)
            self.assertIsNotNone(coords_a)
            self.assertIsNotNone(coords_b)
            t0, t1 = trim_line_for_labels_for(
                active_canvas_for_window(self.window),
                bond.a,
                bond.b,
                active_canvas_for_window(self.window).model.atoms[bond.a].x,
                active_canvas_for_window(self.window).model.atoms[bond.a].y,
                active_canvas_for_window(self.window).model.atoms[bond.b].x,
                active_canvas_for_window(self.window).model.atoms[bond.b].y,
            )
            ax, ay, az = coords_a
            bx, by, bz = coords_b
            dx = bx - ax
            dy = by - ay
            dz = bz - az
            mid_x = ax + dx * ((t0 + t1) * 0.5)
            mid_y = ay + dy * ((t0 + t1) * 0.5)
            mid_z = az + dz * ((t0 + t1) * 0.5)
            cx, cy, cz = center_3d
            bond_len_sq = dx * dx + dy * dy + dz * dz
            self.assertGreater(bond_len_sq, 1e-9)
            inward_x = cx - mid_x
            inward_y = cy - mid_y
            inward_z = cz - mid_z
            dot = (inward_x * dx + inward_y * dy + inward_z * dz) / bond_len_sq
            perp3_x = inward_x - dx * dot
            perp3_y = inward_y - dy * dot
            perp3_z = inward_z - dz * dot
            perp3_len = math.sqrt(perp3_x * perp3_x + perp3_y * perp3_y + perp3_z * perp3_z)
            if perp3_len <= 1e-6:
                continue
            spacing = active_canvas_for_window(self.window).renderer.style.bond_spacing_px * 1.1
            mid_proj = project_point_3d_for(active_canvas_for_window(self.window), (mid_x, mid_y, mid_z))
            inner_mid_proj = project_point_3d_for(
                active_canvas_for_window(self.window),
                (
                    mid_x + perp3_x / perp3_len * spacing,
                    mid_y + perp3_y / perp3_len * spacing,
                    mid_z + perp3_z / perp3_len * spacing,
                ),
            )
            perp_x = inner_mid_proj[0] - mid_proj[0]
            perp_y = inner_mid_proj[1] - mid_proj[1]
            proj_len = math.hypot(perp_x, perp_y)
            if proj_len <= 1e-3:
                continue

            outer_line = items[0].line()
            inner_line = items[1].line()
            disp_x = ((inner_line.x1() + inner_line.x2()) - (outer_line.x1() + outer_line.x2())) * 0.5
            disp_y = ((inner_line.y1() + inner_line.y2()) - (outer_line.y1() + outer_line.y2())) * 0.5
            disp_len = math.hypot(disp_x, disp_y)
            self.assertGreater(disp_len, 1e-3)

            cosine = (disp_x * perp_x + disp_y * perp_y) / (disp_len * proj_len)
            self.assertGreater(cosine, 0.8)
            checked += 1

        self.assertGreaterEqual(checked, 2)
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

    def test_move_selected_perspective_benzene_ring_keeps_fused_ring_polygons_and_undo(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0), attach_bond_id=0)

        self._select_atom_ids(*sorted(active_canvas_for_window(self.window).model.atoms))
        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 20.0),
        )
        self.assertTrue(rotating)
        active_canvas_for_window(self.window).services.selection_rotation_controller.update_selection_3d_rotation(160.0, 110.0)
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

        before_polygons = [
            [(point.x(), point.y()) for point in ring_item.polygon()]
            for ring_item in ring_items_for(active_canvas_for_window(self.window))
        ]

        selected_ring = ring_items_for(active_canvas_for_window(self.window))[0]
        self._select_items(selected_ring)
        atom_ids, _ = selected_ids_for(active_canvas_for_window(self.window))
        bond_ids, boundary_bond_ids = active_canvas_for_window(self.window).services.canvas_graph_service.bond_sets_for_atoms(atom_ids)

        move_atoms_for(
            active_canvas_for_window(self.window),
            atom_ids,
            40.0,
            25.0,
            bond_ids=bond_ids,
            redraw_bond_ids=boundary_bond_ids,
            update_selection=False,
        )
        active_canvas_for_window(self.window).runtime_state.history_service.push(
            MoveAtomsCommand(
                atom_ids=set(atom_ids),
                dx=40.0,
                dy=25.0,
                bond_ids=set(bond_ids),
                redraw_bond_ids=set(boundary_bond_ids),
            )
        )

        for ring_item in ring_items_for(active_canvas_for_window(self.window)):
            self._assert_ring_polygon_matches_atoms(ring_item)

        active_canvas_for_window(self.window).runtime_state.history_service.undo()

        for ring_item, before_points in zip(ring_items_for(active_canvas_for_window(self.window)), before_polygons, strict=False):
            polygon = ring_item.polygon()
            self.assertEqual(polygon.count(), len(before_points))
            for point, (before_x, before_y) in zip(polygon, before_points, strict=False):
                self.assertAlmostEqual(point.x(), before_x)
                self.assertAlmostEqual(point.y(), before_y)
            self._assert_ring_polygon_matches_atoms(ring_item)

    def test_perspective_rotation_reflattens_planar_ring_fragments(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        ring_atom_ids = ring_items_for(active_canvas_for_window(self.window))[0].data(2)
        self.assertIsInstance(ring_atom_ids, list)
        atom_coords_3d = atom_coords_3d_for(active_canvas_for_window(self.window))
        for index, atom_id in enumerate(ring_atom_ids):
            atom = active_canvas_for_window(self.window).model.atoms[atom_id]
            atom_coords_3d[atom_id] = (atom.x, atom.y, 6.0 if index % 2 else -4.0)
        self._select_atom_ids(*ring_atom_ids)

        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 0.0),
        )
        self.assertTrue(rotating)
        active_canvas_for_window(self.window).services.selection_rotation_controller.update_selection_3d_rotation(120.0, 80.0)

        coords = {
            atom_id: atom_coords_3d[atom_id]
            for atom_id in ring_atom_ids
        }
        normal = fragment_plane_normal_for(set(ring_atom_ids), coords)
        self.assertIsNotNone(normal)
        centroid = center_for_coords_3d(set(ring_atom_ids), coords)
        self.assertIsNotNone(centroid)
        nx, ny, nz = normal
        cx, cy, cz = centroid
        max_distance = max(
            abs((point[0] - cx) * nx + (point[1] - cy) * ny + (point[2] - cz) * nz)
            for point in coords.values()
        )
        self.assertLess(max_distance, 1e-3)
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

    def test_undo_perspective_rotation_restores_planar_benzene_state(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        ring_atom_ids = ring_items_for(active_canvas_for_window(self.window))[0].data(2)
        self.assertIsInstance(ring_atom_ids, list)

        before_positions = {
            atom_id: (active_canvas_for_window(self.window).model.atoms[atom_id].x, active_canvas_for_window(self.window).model.atoms[atom_id].y)
            for atom_id in ring_atom_ids
        }
        before_coords = {
            atom_id: current_atom_coords_3d_for(active_canvas_for_window(self.window), atom_id)
            for atom_id in ring_atom_ids
        }

        self._select_atom_ids(*ring_atom_ids)
        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 20.0),
        )
        self.assertTrue(rotating)
        active_canvas_for_window(self.window).services.selection_rotation_controller.update_selection_3d_rotation(220.0, 160.0)
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

        active_canvas_for_window(self.window).runtime_state.history_service.undo()

        rotation_state = rotation_state_for(active_canvas_for_window(self.window))
        self.assertIsNone(rotation_state.projection_center_3d)
        self.assertIsNone(rotation_state.projection_anchor_2d)

        for atom_id in ring_atom_ids:
            atom = active_canvas_for_window(self.window).model.atoms[atom_id]
            before_x, before_y = before_positions[atom_id]
            self.assertAlmostEqual(atom.x, before_x)
            self.assertAlmostEqual(atom.y, before_y)
            coords = atom_coords_3d_for(active_canvas_for_window(self.window)).get(atom_id)
            self.assertIsNotNone(coords)
            assert coords is not None
            before_coord = before_coords[atom_id]
            self.assertIsNotNone(before_coord)
            assert before_coord is not None
            self.assertAlmostEqual(coords[0], before_coord[0])
            self.assertAlmostEqual(coords[1], before_coord[1])
            self.assertAlmostEqual(coords[2], before_coord[2])

    def test_undo_second_perspective_rotation_restores_previous_projection_for_multi_ring_molecule(self) -> None:
        ring_centers = [QPointF(-120.0, 0.0), QPointF(120.0, -100.0), QPointF(120.0, 100.0)]
        for center in ring_centers:
            add_benzene_ring_for(active_canvas_for_window(self.window), center)
        ring_items = list(ring_items_for(active_canvas_for_window(self.window)))

        p_id = add_atom_for(active_canvas_for_window(self.window), "P", 0.0, 0.0)
        for ring_item in ring_items:
            ring_atom_ids = ring_item.data(2)
            self.assertIsInstance(ring_atom_ids, list)
            assert isinstance(ring_atom_ids, list)
            attach_atom_id = min(
                ring_atom_ids,
                key=lambda atom_id: math.hypot(
                    active_canvas_for_window(self.window).model.atoms[atom_id].x,
                    active_canvas_for_window(self.window).model.atoms[atom_id].y,
                ),
            )
            add_bond_for(active_canvas_for_window(self.window), p_id, attach_atom_id, 1)
        active_canvas_for_window(self.window).services.structure_build_service.render_model()

        self._select_atom_ids(*sorted(active_canvas_for_window(self.window).model.atoms))

        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 20.0),
        )
        self.assertTrue(rotating)
        active_canvas_for_window(self.window).services.selection_rotation_controller.update_selection_3d_rotation(240.0, 120.0)
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

        rotation_state = rotation_state_for(active_canvas_for_window(self.window))
        before_projection_center = rotation_state.projection_center_3d
        before_projection_anchor = rotation_state.projection_anchor_2d
        self.assertIsNotNone(before_projection_center)
        self.assertIsNotNone(before_projection_anchor)

        tracked_segments: dict[int, list[tuple[float, float, float, float]]] = {}
        for ring_item in ring_items:
            self._assert_ring_double_bonds_face_inward(ring_item)
            ring_atom_ids = ring_item.data(2)
            assert isinstance(ring_atom_ids, list)
            for index, atom_a in enumerate(ring_atom_ids):
                atom_b = ring_atom_ids[(index + 1) % len(ring_atom_ids)]
                bond_id = active_canvas_for_window(self.window).services.canvas_graph_service.bond_id_between(atom_a, atom_b)
                self.assertIsNotNone(bond_id)
                assert bond_id is not None
                bond = active_canvas_for_window(self.window).model.bonds[bond_id]
                self.assertIsNotNone(bond)
                assert bond is not None
                if bond.order == 2:
                    tracked_segments[bond_id] = self._bond_scene_segments(bond_id)

        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            press_pos=QPointF(0.0, 20.0),
        )
        self.assertTrue(rotating)
        active_canvas_for_window(self.window).services.selection_rotation_controller.update_selection_3d_rotation(-200.0, 180.0)
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()

        active_canvas_for_window(self.window).runtime_state.history_service.undo()

        rotation_state = rotation_state_for(active_canvas_for_window(self.window))
        self.assertEqual(rotation_state.projection_center_3d, before_projection_center)
        self.assertEqual(rotation_state.projection_anchor_2d, before_projection_anchor)
        for ring_item in ring_items:
            self._assert_ring_double_bonds_face_inward(ring_item)
        for bond_id, before_segments in tracked_segments.items():
            after_segments = self._bond_scene_segments(bond_id)
            self.assertEqual(len(after_segments), len(before_segments))
            for after_segment, before_segment in zip(after_segments, before_segments, strict=False):
                for after_value, before_value in zip(after_segment, before_segment, strict=False):
                    self.assertAlmostEqual(after_value, before_value)

    def test_perspective_rotation_on_selected_bond_chooses_clicked_side(self) -> None:
        left_id = add_atom_for(active_canvas_for_window(self.window), "C", -80.0, 0.0)
        center_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        right_id = add_atom_for(active_canvas_for_window(self.window), "C", 80.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left_id, center_id)
        bond_id = add_bond_for(active_canvas_for_window(self.window), center_id, right_id)
        active_canvas_for_window(self.window).services.structure_build_service.render_model()

        self._select_atom_ids(left_id, center_id, right_id)

        rotating = active_canvas_for_window(self.window).services.selection_rotation_controller.begin_selection_3d_rotation(
            axis_hint=bond_id,
            press_pos=QPointF(65.0, 0.0),
        )

        self.assertTrue(rotating)
        rotation_state = rotation_state_for(active_canvas_for_window(self.window))
        self.assertEqual(rotation_state.mode, "bond")
        self.assertEqual(rotation_state.atom_ids, {right_id})
        active_canvas_for_window(self.window).services.selection_rotation_controller.end_selection_3d_rotation()


if __name__ == "__main__":
    unittest.main()
