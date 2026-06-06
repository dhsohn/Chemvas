import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QTest = None
    Qt = None

if QApplication is not None:
    from ui.canvas_mark_registry import mark_registry_for
    from ui.canvas_scene_items_state import (
        arrow_items_for,
        mark_items_for,
        note_items_for,
        orbital_items_for,
        ts_bracket_items_for,
    )
    from ui.canvas_service_access import canvas_services_for
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.mark_item_access import mark_center_for
    from ui.note_item_access import committed_note_text_for
    from ui.scene_item_access import create_scene_item_from_state
    from ui.scene_item_state import scene_item_state_for
    from ui.structure_mutation_access import add_atom_for


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI tests")
class SceneItemRestoreTest(unittest.TestCase):
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
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_create_scene_item_from_state_restores_atom_bound_mark_registration(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 12.0, -8.0)
        state = {
            "kind": "mark",
            "mark_kind": "minus",
            "atom_id": atom_id,
            "dx": 16.0,
            "dy": -6.0,
            "x": -500.0,
            "y": -500.0,
        }

        item = create_scene_item_from_state(active_canvas_for_window(self.window), state)

        self.assertIsNotNone(item)
        self.assertIn(item, mark_items_for(active_canvas_for_window(self.window)))
        self.assertIn(item, mark_registry_for(active_canvas_for_window(self.window)).by_atom[atom_id])
        center = mark_center_for(active_canvas_for_window(self.window), item)
        self.assertAlmostEqual(center.x(), 28.0)
        self.assertAlmostEqual(center.y(), -14.0)

    def test_create_scene_item_from_state_restores_note_style_and_last_text(self) -> None:
        style_controller = canvas_services_for(active_canvas_for_window(self.window)).style_controller
        style_controller.set_text_size(19)
        style_controller.set_text_weight(63)
        style_controller.set_text_italic(True)
        state = {"kind": "note", "text": "Mechanism", "x": 18.0, "y": -12.0}

        item = create_scene_item_from_state(active_canvas_for_window(self.window), state)

        self.assertIsNotNone(item)
        self.assertIn(item, note_items_for(active_canvas_for_window(self.window)))
        self.assertEqual(item.toPlainText(), "Mechanism")
        self.assertEqual(committed_note_text_for(item), "Mechanism")
        self.assertEqual(item.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)
        self.assertEqual(item.font().pointSize(), 19)
        self.assertEqual(item.font().weight(), 63)
        self.assertTrue(item.font().italic())

    def test_create_scene_item_from_state_restores_curved_double_arrow_data(self) -> None:
        state = {
            "kind": "curved_double",
            "start": (-30.0, 0.0),
            "end": (30.0, 0.0),
            "control": (4.0, 18.0),
            "double": True,
        }

        item = create_scene_item_from_state(active_canvas_for_window(self.window), state)

        self.assertIsNotNone(item)
        self.assertIn(item, arrow_items_for(active_canvas_for_window(self.window)))
        data = item.data(2) or {}
        self.assertEqual((data["start"].x(), data["start"].y()), state["start"])
        self.assertEqual((data["end"].x(), data["end"].y()), state["end"])
        self.assertEqual((data["control"].x(), data["control"].y()), state["control"])
        self.assertTrue(data["double"])

    def test_create_scene_item_from_state_round_trips_ts_bracket(self) -> None:
        state = {
            "kind": "ts_bracket",
            "left": -20.0,
            "top": -10.0,
            "right": 22.0,
            "bottom": 14.0,
        }

        item = create_scene_item_from_state(active_canvas_for_window(self.window), state)
        restored_state = scene_item_state_for(active_canvas_for_window(self.window), item)

        self.assertIsNotNone(item)
        self.assertIn(item, ts_bracket_items_for(active_canvas_for_window(self.window)))
        self.assertEqual(restored_state["kind"], "ts_bracket")
        self.assertAlmostEqual(restored_state["left"], state["left"])
        self.assertAlmostEqual(restored_state["top"], state["top"])
        self.assertAlmostEqual(restored_state["right"], state["right"])
        self.assertAlmostEqual(restored_state["bottom"], state["bottom"])

    def test_create_scene_item_from_state_restores_orbital_with_registry_metadata(self) -> None:
        canvas_services_for(active_canvas_for_window(self.window)).geometry_controller.set_bond_length(30.0)
        state = {
            "kind": "orbital",
            "orbital_kind": "sp2",
            "center": (16.0, -11.0),
            "scale": 1.4,
            "rotation": 27.0,
        }

        item = create_scene_item_from_state(active_canvas_for_window(self.window), state)

        self.assertIsNotNone(item)
        self.assertIn(item, orbital_items_for(active_canvas_for_window(self.window)))
        self.assertIs(item.scene(), active_canvas_for_window(self.window).scene())
        data = item.data(1) or {}
        meta = item.data(2) or {}
        center = data.get("center")
        self.assertEqual(meta.get("kind"), "sp2")
        self.assertAlmostEqual(center.x(), 16.0)
        self.assertAlmostEqual(center.y(), -11.0)
        self.assertAlmostEqual(data.get("base_handle_dist"), 24.0)
        self.assertAlmostEqual(item.transformOriginPoint().x(), 16.0)
        self.assertAlmostEqual(item.transformOriginPoint().y(), -11.0)
        self.assertAlmostEqual(item.scale(), 1.4)
        self.assertAlmostEqual(item.rotation(), 27.0)


if __name__ == "__main__":
    unittest.main()
