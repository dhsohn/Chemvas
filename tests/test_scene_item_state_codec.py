import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.ui.annotations.state import scene_item_state_for
from chemvas.ui.scene.scene_decoration_access import add_mark_for_atom_for
from tests.canvas_factory import build_canvas_view


class SceneItemStateCodecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = build_canvas_view()

    def tearDown(self) -> None:
        self.canvas.deleteLater()
        self.app.processEvents()

    def test_mark_scene_item_state_round_trips_and_prefers_atom_offset_center(
        self,
    ) -> None:
        atom_id = self.canvas.services.canvas_atom_mutation_service.add_atom(
            "C", 12.0, -8.0
        )
        mark_item = add_mark_for_atom_for(
            self.canvas,
            atom_id,
            QPointF(26.0, -4.0),
            kind="minus",
        )

        state = scene_item_state_for(self.canvas, mark_item)

        self.assertEqual(state["kind"], "mark")
        self.assertEqual(state["mark_kind"], "minus")

        self.canvas.model.atoms[atom_id].x = 50.0
        self.canvas.model.atoms[atom_id].y = 25.0
        state["x"] = -999.0
        state["y"] = -999.0

        self.canvas.services.scene_item_controller.apply_scene_item_state(
            mark_item, state
        )

        center = self.canvas.services.scene_decoration_build_service.mark_center(
            mark_item
        )
        self.assertAlmostEqual(center.x(), 50.0 + state["dx"])
        self.assertAlmostEqual(center.y(), 25.0 + state["dy"])

        restored_state = scene_item_state_for(self.canvas, mark_item)
        self.assertEqual(restored_state["kind"], "mark")
        self.assertEqual(restored_state["mark_kind"], "minus")
        self.assertAlmostEqual(restored_state["x"], center.x())
        self.assertAlmostEqual(restored_state["y"], center.y())

    def test_curved_double_arrow_scene_item_state_round_trips_after_apply(self) -> None:
        arrow_item = self.canvas.services.scene_decoration_service.add_arrow(
            QPointF(-30.0, 0.0), QPointF(30.0, 0.0), "curved_double"
        )
        self.canvas.services.handle_mutation_service.update_curved_control(
            arrow_item, QPointF(0.0, -24.0)
        )

        state = scene_item_state_for(self.canvas, arrow_item)

        self.assertEqual(state["kind"], "curved_double")
        self.assertEqual(state["start"], (-30.0, 0.0))
        self.assertEqual(state["end"], (30.0, 0.0))
        self.assertIsNotNone(state["control"])
        self.assertTrue(state["double"])

        updated_state = dict(state)
        updated_state["start"] = (-40.0, 5.0)
        updated_state["end"] = (40.0, 5.0)
        updated_state["control"] = (10.0, 28.0)

        self.canvas.services.scene_item_controller.apply_scene_item_state(
            arrow_item, updated_state
        )

        restored_state = scene_item_state_for(self.canvas, arrow_item)
        self.assertEqual(restored_state["kind"], "curved_double")
        self.assertEqual(restored_state["start"], updated_state["start"])
        self.assertEqual(restored_state["end"], updated_state["end"])
        self.assertEqual(restored_state["control"], updated_state["control"])
        self.assertTrue(restored_state["double"])
