import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QTest = None
    QPointF = None

if QApplication is not None:
    from ui.main_window import MainWindow


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI tests")
class SceneItemStateCodecTest(unittest.TestCase):
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

    def test_mark_scene_item_state_round_trips_and_prefers_atom_offset_center(self) -> None:
        atom_id = self.window.canvas.add_atom("C", 12.0, -8.0)
        mark_item = self.window.canvas.add_mark_for_atom(atom_id, QPointF(26.0, -4.0), kind="minus", record=False)

        state = self.window.canvas.scene_item_state(mark_item)

        self.assertEqual(state["kind"], "mark")
        self.assertEqual(state["mark_kind"], "minus")

        self.window.canvas.model.atoms[atom_id].x = 50.0
        self.window.canvas.model.atoms[atom_id].y = 25.0
        state["x"] = -999.0
        state["y"] = -999.0

        self.window.canvas.apply_scene_item_state(mark_item, state)

        center = self.window.canvas._mark_center(mark_item)
        self.assertAlmostEqual(center.x(), 50.0 + state["dx"])
        self.assertAlmostEqual(center.y(), 25.0 + state["dy"])

        restored_state = self.window.canvas.scene_item_state(mark_item)
        self.assertEqual(restored_state["kind"], "mark")
        self.assertEqual(restored_state["mark_kind"], "minus")
        self.assertAlmostEqual(restored_state["x"], center.x())
        self.assertAlmostEqual(restored_state["y"], center.y())

    def test_curved_double_arrow_scene_item_state_round_trips_after_apply(self) -> None:
        arrow_item = self.window.canvas.add_arrow(QPointF(-30.0, 0.0), QPointF(30.0, 0.0), "curved_double")
        self.window.canvas._update_curved_control(arrow_item, QPointF(0.0, -24.0))

        state = self.window.canvas.scene_item_state(arrow_item)

        self.assertEqual(state["kind"], "curved_double")
        self.assertEqual(state["start"], (-30.0, 0.0))
        self.assertEqual(state["end"], (30.0, 0.0))
        self.assertIsNotNone(state["control"])
        self.assertTrue(state["double"])

        updated_state = dict(state)
        updated_state["start"] = (-40.0, 5.0)
        updated_state["end"] = (40.0, 5.0)
        updated_state["control"] = (10.0, 28.0)

        self.window.canvas.apply_scene_item_state(arrow_item, updated_state)

        restored_state = self.window.canvas.scene_item_state(arrow_item)
        self.assertEqual(restored_state["kind"], "curved_double")
        self.assertEqual(restored_state["start"], updated_state["start"])
        self.assertEqual(restored_state["end"], updated_state["end"])
        self.assertEqual(restored_state["control"], updated_state["control"])
        self.assertTrue(restored_state["double"])


if __name__ == "__main__":
    unittest.main()
