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
    from ui.main_window import MainWindow


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI tests")
class SceneItemRestoreTest(unittest.TestCase):
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

    def test_create_scene_item_from_state_restores_atom_bound_mark_registration(self) -> None:
        atom_id = self.window.canvas.add_atom("C", 12.0, -8.0)
        state = {
            "kind": "mark",
            "mark_kind": "minus",
            "atom_id": atom_id,
            "dx": 16.0,
            "dy": -6.0,
            "x": -500.0,
            "y": -500.0,
        }

        item = self.window.canvas.create_scene_item_from_state(state)

        self.assertIsNotNone(item)
        self.assertIn(item, self.window.canvas.mark_items)
        self.assertIn(item, self.window.canvas._marks_by_atom[atom_id])
        center = self.window.canvas._mark_center(item)
        self.assertAlmostEqual(center.x(), 28.0)
        self.assertAlmostEqual(center.y(), -14.0)

    def test_create_scene_item_from_state_restores_note_style_and_last_text(self) -> None:
        self.window.canvas.set_text_size(19)
        self.window.canvas.set_text_weight(63)
        self.window.canvas.set_text_italic(True)
        state = {"kind": "note", "text": "Mechanism", "x": 18.0, "y": -12.0}

        item = self.window.canvas.create_scene_item_from_state(state)

        self.assertIsNotNone(item)
        self.assertIn(item, self.window.canvas.note_items)
        self.assertEqual(item.toPlainText(), "Mechanism")
        self.assertEqual(item._last_text, "Mechanism")
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

        item = self.window.canvas.create_scene_item_from_state(state)

        self.assertIsNotNone(item)
        self.assertIn(item, self.window.canvas.arrow_items)
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

        item = self.window.canvas.create_scene_item_from_state(state)
        restored_state = self.window.canvas.scene_item_state(item)

        self.assertIsNotNone(item)
        self.assertIn(item, self.window.canvas.ts_bracket_items)
        self.assertEqual(restored_state["kind"], "ts_bracket")
        self.assertAlmostEqual(restored_state["left"], state["left"])
        self.assertAlmostEqual(restored_state["top"], state["top"])
        self.assertAlmostEqual(restored_state["right"], state["right"])
        self.assertAlmostEqual(restored_state["bottom"], state["bottom"])

    def test_create_scene_item_from_state_restores_orbital_with_registry_metadata(self) -> None:
        self.window.canvas.set_bond_length(30.0)
        state = {
            "kind": "orbital",
            "orbital_kind": "sp2",
            "center": (16.0, -11.0),
            "scale": 1.4,
            "rotation": 27.0,
        }

        item = self.window.canvas.create_scene_item_from_state(state)

        self.assertIsNotNone(item)
        self.assertIn(item, self.window.canvas.orbital_items)
        self.assertIs(item.scene(), self.window.canvas.scene())
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
