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
    from ui.handle_mutation_access import update_curved_control_for
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.main_window_service_ports import services_for_window
    from ui.mark_item_access import mark_center_for
    from ui.scene_decoration_access import add_arrow_for, add_mark_for_atom_for
    from ui.scene_item_access import apply_scene_item_state
    from ui.scene_item_state import scene_item_state_for
    from ui.structure_mutation_access import add_atom_for


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI tests")
class SceneItemStateCodecTest(unittest.TestCase):
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

    def test_mark_scene_item_state_round_trips_and_prefers_atom_offset_center(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 12.0, -8.0)
        mark_item = add_mark_for_atom_for(active_canvas_for_window(self.window), atom_id, QPointF(26.0, -4.0), kind="minus", record=False)

        state = scene_item_state_for(active_canvas_for_window(self.window), mark_item)

        self.assertEqual(state["kind"], "mark")
        self.assertEqual(state["mark_kind"], "minus")

        active_canvas_for_window(self.window).model.atoms[atom_id].x = 50.0
        active_canvas_for_window(self.window).model.atoms[atom_id].y = 25.0
        state["x"] = -999.0
        state["y"] = -999.0

        apply_scene_item_state(active_canvas_for_window(self.window), mark_item, state)

        center = mark_center_for(active_canvas_for_window(self.window), mark_item)
        self.assertAlmostEqual(center.x(), 50.0 + state["dx"])
        self.assertAlmostEqual(center.y(), 25.0 + state["dy"])

        restored_state = scene_item_state_for(active_canvas_for_window(self.window), mark_item)
        self.assertEqual(restored_state["kind"], "mark")
        self.assertEqual(restored_state["mark_kind"], "minus")
        self.assertAlmostEqual(restored_state["x"], center.x())
        self.assertAlmostEqual(restored_state["y"], center.y())

    def test_curved_double_arrow_scene_item_state_round_trips_after_apply(self) -> None:
        arrow_item = add_arrow_for(active_canvas_for_window(self.window), QPointF(-30.0, 0.0), QPointF(30.0, 0.0), "curved_double")
        update_curved_control_for(active_canvas_for_window(self.window), arrow_item, QPointF(0.0, -24.0))

        state = scene_item_state_for(active_canvas_for_window(self.window), arrow_item)

        self.assertEqual(state["kind"], "curved_double")
        self.assertEqual(state["start"], (-30.0, 0.0))
        self.assertEqual(state["end"], (30.0, 0.0))
        self.assertIsNotNone(state["control"])
        self.assertTrue(state["double"])

        updated_state = dict(state)
        updated_state["start"] = (-40.0, 5.0)
        updated_state["end"] = (40.0, 5.0)
        updated_state["control"] = (10.0, 28.0)

        apply_scene_item_state(active_canvas_for_window(self.window), arrow_item, updated_state)

        restored_state = scene_item_state_for(active_canvas_for_window(self.window), arrow_item)
        self.assertEqual(restored_state["kind"], "curved_double")
        self.assertEqual(restored_state["start"], updated_state["start"])
        self.assertEqual(restored_state["end"], updated_state["end"])
        self.assertEqual(restored_state["control"], updated_state["control"])
        self.assertTrue(restored_state["double"])


if __name__ == "__main__":
    unittest.main()
