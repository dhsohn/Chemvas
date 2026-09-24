import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.annotations.state import scene_item_state_for
from chemvas.ui.scene.scene_decoration_access import materialize_mark_for_atom_for
from chemvas.ui.window.main_window_ports import active_canvas_for_window


class SceneItemStateCodecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.window.show()
        active_canvas_for_window(self.window).setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        document_service = self.window.services.canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def test_mark_scene_item_state_round_trips_and_prefers_atom_offset_center(
        self,
    ) -> None:
        atom_id = active_canvas_for_window(
            self.window
        ).services.canvas_atom_mutation_service.add_atom("C", 12.0, -8.0)
        mark_item = materialize_mark_for_atom_for(
            active_canvas_for_window(self.window),
            atom_id,
            QPointF(26.0, -4.0),
            kind="minus",
        )

        state = scene_item_state_for(active_canvas_for_window(self.window), mark_item)

        self.assertEqual(state["kind"], "mark")
        self.assertEqual(state["mark_kind"], "minus")

        active_canvas_for_window(self.window).model.atoms[atom_id].x = 50.0
        active_canvas_for_window(self.window).model.atoms[atom_id].y = 25.0
        state["x"] = -999.0
        state["y"] = -999.0

        active_canvas_for_window(
            self.window
        ).services.scene_item_controller.apply_scene_item_state(mark_item, state)

        center = active_canvas_for_window(
            self.window
        ).services.scene_decoration_build_service.mark_center(mark_item)
        self.assertAlmostEqual(center.x(), 50.0 + state["dx"])
        self.assertAlmostEqual(center.y(), 25.0 + state["dy"])

        restored_state = scene_item_state_for(
            active_canvas_for_window(self.window), mark_item
        )
        self.assertEqual(restored_state["kind"], "mark")
        self.assertEqual(restored_state["mark_kind"], "minus")
        self.assertAlmostEqual(restored_state["x"], center.x())
        self.assertAlmostEqual(restored_state["y"], center.y())

    def test_curved_double_arrow_scene_item_state_round_trips_after_apply(self) -> None:
        arrow_item = active_canvas_for_window(
            self.window
        ).services.scene_decoration_service.add_arrow(
            QPointF(-30.0, 0.0), QPointF(30.0, 0.0), "curved_double"
        )
        active_canvas_for_window(
            self.window
        ).services.handle_mutation_service.update_curved_control(
            arrow_item, QPointF(0.0, -24.0)
        )

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

        active_canvas_for_window(
            self.window
        ).services.scene_item_controller.apply_scene_item_state(
            arrow_item, updated_state
        )

        restored_state = scene_item_state_for(
            active_canvas_for_window(self.window), arrow_item
        )
        self.assertEqual(restored_state["kind"], "curved_double")
        self.assertEqual(restored_state["start"], updated_state["start"])
        self.assertEqual(restored_state["end"], updated_state["end"])
        self.assertEqual(restored_state["control"], updated_state["control"])
        self.assertTrue(restored_state["double"])
