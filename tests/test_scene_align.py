import os
import unittest
from itertools import pairwise

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)
from chemvas.ui.scene_align_logic import align_deltas, distribute_deltas
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_state_serialization import arrow_state_dict
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for


class AlignLogicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rects = [
            QRectF(0.0, 0.0, 10.0, 10.0),
            QRectF(30.0, 20.0, 20.0, 5.0),
            QRectF(5.0, 50.0, 40.0, 30.0),
        ]

    def test_align_modes_line_up_the_requested_edge_or_center(self) -> None:
        expected = {
            "left": [(0.0, 0.0), (-30.0, 0.0), (-5.0, 0.0)],
            "right": [(40.0, 0.0), (0.0, 0.0), (5.0, 0.0)],
            "center": [(20.0, 0.0), (-15.0, 0.0), (0.0, 0.0)],
            "top": [(0.0, 0.0), (0.0, -20.0), (0.0, -50.0)],
            "bottom": [(0.0, 70.0), (0.0, 55.0), (0.0, 0.0)],
            "middle": [(0.0, 35.0), (0.0, 17.5), (0.0, -25.0)],
        }
        for mode, deltas in expected.items():
            with self.subTest(mode=mode):
                self.assertEqual(align_deltas(self.rects, mode), deltas)

    def test_align_needs_two_rects_and_rejects_unknown_modes(self) -> None:
        self.assertEqual(align_deltas(self.rects[:1], "left"), [(0.0, 0.0)])
        with self.assertRaises(ValueError):
            align_deltas(self.rects, "diagonal")

    def test_distribute_equalizes_gaps_and_keeps_the_outer_rects(self) -> None:
        rects = [
            QRectF(0.0, 0.0, 10.0, 10.0),
            QRectF(12.0, 0.0, 10.0, 10.0),
            QRectF(90.0, 0.0, 10.0, 10.0),
        ]
        deltas = distribute_deltas(rects, "horizontal")
        # Free space 100 - 30 = 70, two gaps of 35: the middle box moves to x=45.
        self.assertEqual(deltas, [(0.0, 0.0), (33.0, 0.0), (0.0, 0.0)])

        vertical = [QRectF(0.0, y, 10.0, 10.0) for y in (0.0, 5.0, 100.0)]
        self.assertEqual(
            distribute_deltas(vertical, "vertical"),
            [(0.0, 0.0), (0.0, 45.0), (0.0, 0.0)],
        )

    def test_distribute_orders_by_center_and_needs_three_rects(self) -> None:
        rects = [
            QRectF(90.0, 0.0, 10.0, 10.0),
            QRectF(0.0, 0.0, 10.0, 10.0),
            QRectF(12.0, 0.0, 10.0, 10.0),
        ]
        self.assertEqual(
            distribute_deltas(rects, "horizontal"),
            [(0.0, 0.0), (0.0, 0.0), (33.0, 0.0)],
        )
        self.assertEqual(distribute_deltas(rects[:2], "horizontal"), [(0.0, 0.0)] * 2)
        with self.assertRaises(ValueError):
            distribute_deltas(rects, "diagonal")


class AlignGuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.window.show()
        self.canvas = active_canvas_for_window(self.window)
        self.canvas.setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _select(self, *items) -> None:
        self.canvas.scene().clearSelection()
        for item in items:
            item.setSelected(True)
        self.app.processEvents()

    def test_align_moves_structures_and_items_as_units_with_one_undo(self) -> None:
        canvas = self.canvas
        atom_a = add_atom_for(canvas, "C", 100.0, 40.0)
        atom_b = add_atom_for(canvas, "O", 120.0, 40.0)
        add_bond_for(canvas, atom_a, atom_b)
        arrow = add_arrow_for(canvas, QPointF(0.0, 0.0), QPointF(40.0, 0.0), "arrow")
        line = add_arrow_for(canvas, QPointF(30.0, 90.0), QPointF(70.0, 90.0), "line")
        self._select(
            visible_atom_item_for(canvas, atom_a),
            visible_atom_item_for(canvas, atom_b),
            arrow,
            line,
        )
        controller = canvas_services_for(
            canvas
        ).scene_operations.scene_transform_controller
        history = canvas.runtime_state.history_service
        before_gap = atom_for_id(canvas, atom_b).x - atom_for_id(canvas, atom_a).x

        self.assertTrue(controller.align_selected_items("left"))

        # The structure kept its shape and every object now starts at the
        # arrow's left edge; the arrow itself did not move.
        self.assertAlmostEqual(
            atom_for_id(canvas, atom_b).x - atom_for_id(canvas, atom_a).x, before_gap
        )
        self.assertEqual(arrow_state_dict(arrow)["start"], (0.0, 0.0))
        self.assertAlmostEqual(arrow_state_dict(line)["start"][0], 0.0, places=6)
        self.assertLess(atom_for_id(canvas, atom_a).x, 100.0)
        self.assertEqual(arrow_state_dict(line)["start"][1], 90.0)

        history.undo()
        self.assertEqual(atom_for_id(canvas, atom_a).x, 100.0)
        self.assertEqual(arrow_state_dict(line)["start"], (30.0, 90.0))
        history.redo()
        self.assertAlmostEqual(arrow_state_dict(line)["start"][0], 0.0, places=6)

    def test_distribute_spreads_three_arrows_evenly_and_ignores_pairs(self) -> None:
        canvas = self.canvas
        arrows = [
            add_arrow_for(canvas, QPointF(x, 0.0), QPointF(x + 20.0, 0.0), "arrow")
            for x in (0.0, 25.0, 200.0)
        ]
        controller = canvas_services_for(
            canvas
        ).scene_operations.scene_transform_controller

        self._select(arrows[0], arrows[1])
        self.assertFalse(controller.distribute_selected_items("horizontal"))

        self._select(*arrows)
        self.assertTrue(controller.distribute_selected_items("horizontal"))
        starts = sorted(
            arrow_state_dict(item)["start"][0] for item in arrow_items_for(canvas)
        )
        gaps = [b - a for a, b in pairwise(starts)]
        self.assertAlmostEqual(gaps[0], gaps[1], places=6)
        self.assertEqual(starts[0], 0.0)
        self.assertEqual(starts[-1], 200.0)
