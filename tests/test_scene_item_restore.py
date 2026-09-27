import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from chemvas.ui.annotations.state import scene_item_state_for
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_text_style_state import set_text_style_for
from chemvas.ui.scene.note_item_access import committed_note_text_for
from tests.canvas_factory import build_canvas_view


class SceneItemRestoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = build_canvas_view()

    def tearDown(self) -> None:
        self.canvas.deleteLater()
        self.app.processEvents()

    def test_create_scene_item_from_state_restores_atom_bound_mark_registration(
        self,
    ) -> None:
        atom_id = self.canvas.services.canvas_atom_mutation_service.add_atom(
            "C", 12.0, -8.0
        )
        state = {
            "kind": "mark",
            "mark_kind": "minus",
            "atom_id": atom_id,
            "dx": 16.0,
            "dy": -6.0,
            "x": -500.0,
            "y": -500.0,
        }

        item = self.canvas.services.scene_item_controller.create_scene_item_from_state(
            state
        )

        self.assertIsNotNone(item)
        self.assertIn(item, self.canvas.runtime_state.mark_items())
        self.assertIn(
            item,
            mark_registry_for(self.canvas).by_atom[atom_id],
        )
        center = self.canvas.services.scene_decoration_build_service.mark_center(item)
        self.assertAlmostEqual(center.x(), 28.0)
        self.assertAlmostEqual(center.y(), -14.0)

    def test_create_scene_item_from_state_restores_note_style_and_last_text(
        self,
    ) -> None:
        set_text_style_for(self.canvas, "text_font_size", 19)
        set_text_style_for(self.canvas, "text_font_weight", 63)
        set_text_style_for(self.canvas, "text_italic", True)
        state = {"kind": "note", "text": "Mechanism", "x": 18.0, "y": -12.0}

        item = self.canvas.services.scene_item_controller.create_scene_item_from_state(
            state
        )

        self.assertIsNotNone(item)
        self.assertIn(item, self.canvas.runtime_state.note_items())
        self.assertEqual(item.toPlainText(), "Mechanism")
        self.assertEqual(committed_note_text_for(item), "Mechanism")
        self.assertEqual(
            item.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction
        )
        self.assertEqual(item.font().pointSize(), 19)
        self.assertEqual(item.font().weight(), 63)
        self.assertTrue(item.font().italic())

    def test_create_scene_item_from_state_restores_curved_double_arrow_data(
        self,
    ) -> None:
        state = {
            "kind": "curved_double",
            "start": (-30.0, 0.0),
            "end": (30.0, 0.0),
            "control": (4.0, 18.0),
            "double": True,
        }

        item = self.canvas.services.scene_item_controller.create_scene_item_from_state(
            state
        )

        self.assertIsNotNone(item)
        self.assertIn(item, self.canvas.runtime_state.arrow_items())
        record = self.canvas.render_context.arrows.record(item)
        self.assertEqual(record.start, state["start"])
        self.assertEqual(record.end, state["end"])
        self.assertEqual(record.control, state["control"])
        self.assertTrue(record.double)

    def test_create_scene_item_from_state_round_trips_ts_bracket(self) -> None:
        state = {
            "kind": "ts_bracket",
            "left": -20.0,
            "top": -10.0,
            "right": 22.0,
            "bottom": 14.0,
            "bracket_kind": "square_pair",
        }

        item = self.canvas.services.scene_item_controller.create_scene_item_from_state(
            state
        )
        restored_state = scene_item_state_for(self.canvas, item)

        self.assertIsNotNone(item)
        self.assertIn(item, self.canvas.runtime_state.ts_bracket_items())
        self.assertEqual(restored_state["kind"], "ts_bracket")
        self.assertAlmostEqual(restored_state["left"], state["left"])
        self.assertAlmostEqual(restored_state["top"], state["top"])
        self.assertAlmostEqual(restored_state["right"], state["right"])
        self.assertAlmostEqual(restored_state["bottom"], state["bottom"])

    def test_create_scene_item_from_state_restores_orbital_with_registry_metadata(
        self,
    ) -> None:
        self.canvas.services.geometry_controller.set_bond_length(30.0)
        state = {
            "kind": "orbital",
            "orbital_kind": "sp2",
            "center": (16.0, -11.0),
            "scale": 1.4,
            "rotation": 27.0,
        }

        item = self.canvas.services.scene_item_controller.create_scene_item_from_state(
            state
        )

        self.assertIsNotNone(item)
        self.assertIn(item, self.canvas.runtime_state.orbital_items())
        self.assertIs(item.scene(), self.canvas.scene())
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
