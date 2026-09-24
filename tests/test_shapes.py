import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QGraphicsPathItem

from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    build_document_payload,
    extract_document_state,
    serialize_settings,
)
from chemvas.domain.document.state import _validate_shape_states
from chemvas.features.annotations import (
    SHAPE_KINDS,
    STROKE_STYLES,
    normalized_shape_kind,
    normalized_stroke_style,
    pen_style_for_stroke,
    shape_path,
)
from chemvas.features.selection import (
    resized_shape_rect,
    shape_resize_handle_positions,
)
from chemvas.ui.annotations.materialize import create_shape_item_from_state


class ShapeGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_shape_path_is_non_empty_for_every_kind(self) -> None:
        rect = QRectF(0.0, 0.0, 40.0, 20.0)
        for kind in SHAPE_KINDS:
            path = shape_path(rect, kind)
            self.assertFalse(path.isEmpty(), kind)

    def test_circle_is_inscribed_square_using_shorter_side(self) -> None:
        bounds = shape_path(QRectF(0.0, 0.0, 40.0, 20.0), "circle").boundingRect()
        # diameter == shorter side (20), centered
        self.assertAlmostEqual(bounds.width(), 20.0, places=3)
        self.assertAlmostEqual(bounds.height(), 20.0, places=3)
        self.assertAlmostEqual(bounds.center().x(), 20.0, places=3)

    def test_normalizers_fall_back_to_defaults(self) -> None:
        self.assertEqual(normalized_shape_kind("nonsense"), "circle")
        self.assertEqual(normalized_stroke_style("nonsense"), "solid")
        self.assertEqual(normalized_shape_kind("rect"), "rect")

    def test_pen_style_distinct_per_stroke(self) -> None:
        styles = {pen_style_for_stroke(s) for s in STROKE_STYLES}
        self.assertEqual(len(styles), len(STROKE_STYLES))
        # "none" maps to NoPen so the outline is dropped entirely.
        self.assertEqual(pen_style_for_stroke("none"), Qt.PenStyle.NoPen)


class ShapeItemFromStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_create_from_state_draws_the_state(self) -> None:
        state = {
            "kind": "shape",
            "left": 10.0,
            "top": 20.0,
            "right": 70.0,
            "bottom": 60.0,
            "shape_kind": "rounded_rect",
            "stroke_style": "dashed",
            "fill": "#2196f3",
            "fill_alpha": 0.25,
        }

        built = create_shape_item_from_state(state, build_shape_item=self._build)

        self.assertIsNotNone(built)
        self.assertEqual(
            built.path(), shape_path(QRectF(10.0, 20.0, 60.0, 40.0), "rounded_rect")
        )
        self.assertEqual(built.brush().color().name(), "#2196f3")
        self.assertGreater(built.brush().color().alphaF(), 0.0)

    def _build(self, rect, kind, stroke, fill):
        item = QGraphicsPathItem(shape_path(rect, kind))
        item.setData(0, "shape")
        item.setBrush(fill if fill is not None else QColor(0, 0, 0, 0))
        return item


class ShapeResizeTest(unittest.TestCase):
    def test_eight_handles_at_corners_and_edges(self) -> None:
        positions = dict(shape_resize_handle_positions(QRectF(0.0, 0.0, 100.0, 60.0)))
        self.assertEqual(len(positions), 8)
        self.assertEqual(positions["shape_nw"], QPointF(0.0, 0.0))
        self.assertEqual(positions["shape_se"], QPointF(100.0, 60.0))
        self.assertEqual(positions["shape_n"], QPointF(50.0, 0.0))

    def test_corner_drag_moves_only_that_corner(self) -> None:
        rect = resized_shape_rect(
            QRectF(0.0, 0.0, 60.0, 40.0), "shape_se", QPointF(100.0, 90.0)
        )
        self.assertEqual(rect, QRectF(0.0, 0.0, 100.0, 90.0))

    def test_edge_drag_moves_only_that_edge(self) -> None:
        rect = resized_shape_rect(
            QRectF(0.0, 0.0, 60.0, 40.0), "shape_n", QPointF(999.0, -20.0)
        )
        self.assertEqual(rect, QRectF(0.0, -20.0, 60.0, 60.0))

    def test_min_size_clamp_prevents_inversion(self) -> None:
        rect = resized_shape_rect(
            QRectF(0.0, 0.0, 60.0, 40.0),
            "shape_nw",
            QPointF(500.0, 500.0),
            min_size=8.0,
        )
        self.assertGreaterEqual(rect.width(), 8.0)
        self.assertGreaterEqual(rect.height(), 8.0)

    def test_shape_is_a_selectable_object(self) -> None:
        # Shapes must be selectable for resize handles and border editing to work.
        from chemvas.ui.selection.selection_structure_targets import (
            STRUCTURE_OVERLAY_KINDS,
        )

        self.assertIn("shape", STRUCTURE_OVERLAY_KINDS)


class ShapeDocumentValidationTest(unittest.TestCase):
    def _valid_shape(self):
        return {
            "kind": "shape",
            "left": 1.0,
            "top": 2.0,
            "right": 3.0,
            "bottom": 4.0,
            "shape_kind": "circle",
            "stroke_style": "solid",
        }

    def test_accepts_valid_shapes_and_empty_list_but_rejects_null(self) -> None:
        _validate_shape_states([])
        with self.assertRaises(ValueError):
            _validate_shape_states(None)
        _validate_shape_states([self._valid_shape()])
        with_fill = self._valid_shape()
        with_fill.update({"fill": "#ff0000", "fill_alpha": 0.25})
        _validate_shape_states([with_fill])
        borderless = self._valid_shape()
        borderless["stroke_style"] = "none"
        _validate_shape_states([borderless])

    def test_rejects_bad_kind_and_stroke(self) -> None:
        bad_kind = self._valid_shape()
        bad_kind["shape_kind"] = "triangle"
        with self.assertRaises(ValueError):
            _validate_shape_states([bad_kind])
        bad_stroke = self._valid_shape()
        bad_stroke["stroke_style"] = "wavy"
        with self.assertRaises(ValueError):
            _validate_shape_states([bad_stroke])
        bad_fill = self._valid_shape()
        bad_fill["fill"] = "red"
        with self.assertRaises(ValueError):
            _validate_shape_states([bad_fill])

    def test_document_payload_round_trips_shapes(self) -> None:
        state = {
            "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
            "ring_fills": [],
            "notes": [],
            "marks": [],
            "arrows": [],
            "ts_brackets": [],
            "shapes": [self._valid_shape()],
            "orbitals": [],
            "settings": serialize_settings(
                bond_length_px=20.0,
                arrow_line_width=1.0,
                arrow_head_scale=0.3,
                orbital_phase_enabled=False,
                text_font_size=12,
                text_font_weight=50,
                text_italic=False,
                sheet_size="A4",
                sheet_orientation="portrait",
            ),
            "last_smiles_input": None,
        }
        payload = build_document_payload(state, CANVAS_FILE_VERSION)
        restored = extract_document_state(payload)
        self.assertEqual(len(restored["shapes"]), 1)

    def test_current_document_without_shapes_key_is_rejected(self) -> None:
        state = {
            "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
            "ring_fills": [],
            "notes": [],
            "marks": [],
            "arrows": [],
            "ts_brackets": [],
            "orbitals": [],
            "settings": serialize_settings(
                bond_length_px=20.0,
                arrow_line_width=1.0,
                arrow_head_scale=0.3,
                orbital_phase_enabled=False,
                text_font_size=12,
                text_font_weight=50,
                text_italic=False,
                sheet_size="A4",
                sheet_orientation="portrait",
            ),
            "last_smiles_input": None,
        }
        with self.assertRaises(ValueError):
            build_document_payload(state, CANVAS_FILE_VERSION)
