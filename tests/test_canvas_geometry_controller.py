import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.atom_coords_access import CanvasAtomCoords3DState
    from ui.canvas_atom_graphics_state import set_atom_items_for
    from ui.canvas_geometry_controller import CanvasGeometryController
    from ui.canvas_scene_items_state import set_scene_item_collection_for


class _FakeRingItem:
    def __init__(self, atom_ids) -> None:
        self._atom_ids = atom_ids

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None


class _FakeLabelItem:
    def __init__(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    def sceneBoundingRect(self) -> QRectF:
        return QRectF(self._rect)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas geometry controller tests")
class CanvasGeometryControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_ring_for_bond_handles_invalid_none_missing_and_matching_cases(self) -> None:
        ring_item = _FakeRingItem([1, 2, 3])
        canvas = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None, Bond(4, 5, 1)]),
        )
        set_scene_item_collection_for(canvas, "ring_items", [_FakeRingItem("bad"), ring_item])
        controller = CanvasGeometryController(canvas)

        self.assertIsNone(controller.ring_for_bond(-1))
        self.assertIsNone(controller.ring_for_bond(1))
        self.assertIsNone(controller.ring_for_bond(2))
        self.assertIsNone(controller.ring_for_bond(9))
        self.assertIs(controller.ring_for_bond(0), ring_item)

    def test_ring_center_helpers_skip_invalid_and_missing_atoms(self) -> None:
        ring_item = _FakeRingItem([1, 2, 3])
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 3: Atom("C", 6.0, 12.0)}),
            atom_coords_3d_state=CanvasAtomCoords3DState(
                atom_coords_3d={
                    1: (0.0, 0.0, 0.0),
                    3: (6.0, 12.0, 9.0),
                }
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )
        set_scene_item_collection_for(canvas, "ring_items", [_FakeRingItem("bad"), ring_item, _FakeRingItem([7, 8])])
        controller = CanvasGeometryController(canvas)

        center = controller.ring_center_for_bond(Bond(1, 3, 1))
        self.assertEqual(center, QPointF(3.0, 6.0))
        self.assertIsNone(controller.ring_center_for_bond(Bond(7, 8, 1)))
        self.assertIsNone(controller.ring_center_3d_for_bond(Bond(1, 3, 1)))

        controller.canvas.model.atoms[2] = Atom("C", 3.0, 6.0)
        controller.canvas.atom_coords_3d_state.atom_coords_3d[2] = (3.0, 6.0, 3.0)
        self.assertEqual(controller.ring_center_3d_for_bond(Bond(1, 3, 1)), (3.0, 6.0, 4.0))

    def test_label_rect_helpers_return_none_for_missing_items_and_pad_present_items(self) -> None:
        controller = CanvasGeometryController(
            SimpleNamespace(
                atom_items={},
                renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=2.0)),
                model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}),
            )
        )

        self.assertIsNone(controller.label_rect_for_atom(1))
        self.assertIsNone(controller.visible_label_rect_for_atom(1))
        self.assertIsNone(controller.label_cut_radius_for_atom(1))

        label_item = QGraphicsTextItem("OH")
        label_item.setPos(1.0, 2.0)
        set_atom_items_for(controller.canvas, {1: label_item})
        label_rect = controller.label_rect_for_atom(1)
        visible_rect = controller.visible_label_rect_for_atom(1)
        base_label_rect = label_item.sceneBoundingRect()
        base_visible_rect = CanvasGeometryController.visible_text_rect(label_item)
        self.assertLess(label_rect.left(), base_label_rect.left())
        self.assertLess(label_rect.top(), base_label_rect.top())
        self.assertGreater(label_rect.right(), base_label_rect.right())
        self.assertGreater(label_rect.bottom(), base_label_rect.bottom())
        self.assertLess(visible_rect.left(), base_visible_rect.left())
        self.assertLess(visible_rect.top(), base_visible_rect.top())
        self.assertGreater(visible_rect.right(), base_visible_rect.right())
        self.assertGreater(visible_rect.bottom(), base_visible_rect.bottom())

        controller.canvas.model.atoms = {}
        self.assertIsNone(controller.label_cut_radius_for_atom(1))

    def test_visible_text_rect_covers_both_lines_of_a_stacked_hydride(self) -> None:
        from ui.graphics_items import AtomLabelItem

        stacked = AtomLabelItem()
        stacked.setFont(QFont("Helvetica", 13))
        stacked.setPlainText("NH")
        stacked.set_stack_anchor("N", hydrogens_below=True)

        visible_rect = CanvasGeometryController.visible_text_rect(stacked)
        one_line_rect = stacked.mapRectToScene(QGraphicsTextItem.boundingRect(stacked))
        # The two-line content box must be taller than the one-line Qt document
        # rect so a mark placed above/below clears the stacked hydrogen glyph.
        self.assertGreater(visible_rect.height(), one_line_rect.height())

    def test_mark_clearance_for_kind_covers_radical_plus_minus_and_default(self) -> None:
        style = SimpleNamespace(bond_length_px=20.0, bond_line_width=2.0)
        controller = CanvasGeometryController(
            SimpleNamespace(renderer=SimpleNamespace(style=style, atom_font=lambda: QFont()))
        )

        default_gap = max(0.6, style.bond_length_px * 0.05)
        self.assertEqual(controller.mark_clearance_for_kind("unknown"), default_gap)
        self.assertGreater(controller.mark_clearance_for_kind("radical"), default_gap)
        self.assertGreater(controller.mark_clearance_for_kind("plus"), default_gap)
        self.assertGreater(controller.mark_clearance_for_kind("minus"), default_gap)

    def test_math_wrapper_helpers_delegate_to_pure_geometry_logic(self) -> None:
        controller = CanvasGeometryController(SimpleNamespace())
        rect = QRectF(0.0, 0.0, 10.0, 10.0)

        self.assertEqual(controller.line_rect_clip_t(QPointF(-5.0, 5.0), QPointF(15.0, 5.0), rect), (0.25, 0.75))
        self.assertEqual(
            controller.segment_intersection_t(
                QPointF(0.0, 0.0),
                QPointF(10.0, 10.0),
                QPointF(0.0, 10.0),
                QPointF(10.0, 0.0),
            ),
            0.5,
        )
        self.assertEqual(controller.ray_rect_exit_distance(QPointF(5.0, 5.0), QPointF(1.0, 0.0), rect), 5.0)
        self.assertEqual(
            sorted(controller.line_rect_intersections(QPointF(-5.0, 5.0), QPointF(15.0, 5.0), rect)),
            [0.25, 0.75],
        )

    def test_trim_line_for_labels_handles_none_radii_and_min_span_clamp(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
        )
        controller = CanvasGeometryController(canvas)
        controller.label_cut_radius_for_atom = lambda atom_id: {1: None, 2: 49.6}.get(atom_id)

        self.assertEqual(controller.trim_line_for_labels(1, None, 0.0, 0.0, 100.0, 0.0), (0.0, 1.0))
        self.assertEqual(controller.trim_line_for_labels(None, 1, 0.0, 0.0, 100.0, 0.0), (0.0, 1.0))

        tight = controller.trim_line_for_labels(1, 2, 0.0, 0.0, 100.0, 0.0)
        self.assertAlmostEqual(tight[0], 0.0)
        self.assertAlmostEqual(tight[1], 0.503)

    def test_trim_line_for_labels_uses_visible_label_rect_for_wide_aliases(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=0.0)),
        )
        controller = CanvasGeometryController(canvas)
        controller.visible_label_rect_for_atom = lambda atom_id: {1: QRectF(-2.0, -5.0, 32.0, 10.0)}.get(atom_id)
        controller.label_cut_radius_for_atom = lambda atom_id: 5.0

        trimmed = controller.trim_line_for_labels(1, None, 0.0, 0.0, 100.0, 0.0)

        self.assertEqual(trimmed, (0.3, 1.0))

    def test_trim_line_for_labels_clamps_start_only_and_end_only_min_span(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
        )
        controller = CanvasGeometryController(canvas)
        controller.label_cut_radius_for_atom = lambda atom_id: {1: 99.9, 2: 99.9}.get(atom_id)

        self.assertEqual(controller.trim_line_for_labels(1, None, 0.0, 0.0, 100.0, 0.0), (0.98, 1.0))
        self.assertEqual(controller.trim_line_for_labels(None, 2, 0.0, 0.0, 100.0, 0.0), (0.0, 0.02))


if __name__ == "__main__":
    unittest.main()
