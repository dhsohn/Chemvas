import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.orbital_support import make_orbital
from tests.ring_support import make_ring
from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsPathItem,
    QGraphicsTextItem,
)

from chemvas.ui.annotations.materialize import create_note_item_from_state
from chemvas.ui.annotations.state import (
    apply_scene_item_state,
    mark_center_from_state,
    mark_state_dict_for,
    scene_item_history_state,
    scene_item_state,
    scene_item_state_for,
    ts_bracket_rect_from_state,
)
from chemvas.ui.scene.note_item_access import committed_note_text_for


class SceneItemStateUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_scene_item_state_returns_empty_for_none_and_unknown_kind(self) -> None:
        item = QGraphicsTextItem("unknown")

        self.assertEqual(
            scene_item_state(None, mark_center_getter=lambda _: QPointF()), {}
        )
        self.assertEqual(
            scene_item_state(item, mark_center_getter=lambda _: QPointF()), {}
        )

    def test_history_mark_state_keeps_exact_local_position_without_mutating_input(
        self,
    ) -> None:
        for kind in ("plus", "minus", "radical", "circled_plus", "circled_minus"):
            for atom_id in (None, 7):
                with self.subTest(kind=kind, atom_id=atom_id):
                    item = QGraphicsTextItem("mark")
                    item.setData(0, "mark")
                    item.setData(1, {"kind": kind, "atom_id": atom_id})
                    item.setPos(0.1, math.nextafter(0.3, 1.0))
                    original = {
                        "kind": "mark",
                        "mark_kind": kind,
                        "atom_id": atom_id,
                        "dx": 4.125,
                        "dy": -6.375,
                        "x": 100.1,
                        "y": -50.3,
                        "color": "#Aa22Cc",
                    }
                    state = dict(original)
                    metadata = dict(item.data(1))

                    history = scene_item_history_state(item, state)

                    self.assertEqual(
                        history,
                        {**original, "item_pos": (0.1, math.nextafter(0.3, 1.0))},
                    )
                    self.assertEqual(state, original)
                    self.assertEqual(item.data(1), metadata)
                    self.assertNotIn("item_pos", state)

    def test_history_nonmark_state_does_not_read_or_add_a_position(self) -> None:
        item = mock.Mock()
        item.pos.side_effect = AssertionError("Only marks need local history positions")
        for state in ({}, {"kind": "note", "x": 0.1, "y": 0.3}):
            with self.subTest(state=state):
                self.assertEqual(scene_item_history_state(item, state), state)
                self.assertNotIn("item_pos", state)
        item.pos.assert_not_called()

    def test_history_capture_preserves_the_callers_serialization_precedence(
        self,
    ) -> None:
        item = QGraphicsTextItem("+")
        item.setData(0, "mark")
        item.setData(1, {"kind": "plus", "atom_id": 7, "dx": 4.0, "dy": -6.0})
        embedded = {"kind": "mark", "mark_kind": "minus", "x": 99.5, "y": 50.25}
        item.setData(9, embedded)
        item.setPos(0.1, 0.3)
        canvas = SimpleNamespace(
            services=canvas_runtime_services(
                scene_decoration_build_service=SimpleNamespace(
                    mark_center=mock.Mock(return_value=QPointF(1.25, 2.5))
                )
            )
        )
        generic = scene_item_state_for(canvas, item)
        typed = mark_state_dict_for(canvas, item)

        self.assertEqual(generic["mark_kind"], "plus")
        self.assertEqual(generic["x"], 1.25)
        self.assertEqual(typed, embedded)
        for state in (generic, typed):
            with self.subTest(state=state):
                self.assertEqual(
                    scene_item_history_state(item, state),
                    {**state, "item_pos": (0.1, 0.3)},
                )
                self.assertNotIn("item_pos", state)
        self.assertEqual(item.data(9), embedded)

    def test_scene_item_state_serializes_ring_and_partial_apply_restores_record_brush(
        self,
    ) -> None:
        ring = make_ring(
            QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)]),
            atom_ids=[7, 8, 9],
        )
        ring.setData(0, "ring")
        ring.setBrush(QColor("#336699"))
        brush = ring.brush()
        brush.setStyle(Qt.BrushStyle.SolidPattern)
        brush.setColor(QColor("#336699"))
        brush.setColor(QColor(51, 102, 153, 128))
        ring.set_fill(brush.color())

        state = scene_item_state(ring, mark_center_getter=lambda _: QPointF())

        self.assertEqual(state["kind"], "ring")
        self.assertEqual(state["atom_ids"], [7, 8, 9])
        self.assertEqual(state["color"], "#336699")
        self.assertAlmostEqual(state["alpha"], 128 / 255)

        ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        apply_scene_item_state(
            ring,
            {"kind": "ring", "points": [(0.0, 0.0), (6.0, 0.0), (3.0, 4.0)]},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )

        self.assertEqual(ring.brush().color().name(), "#336699")
        self.assertEqual(len(ring.polygon()), 3)

    def test_apply_ring_state_prefers_explicit_color_and_alpha(self) -> None:
        ring = make_ring()

        apply_scene_item_state(
            ring,
            {
                "kind": "ring",
                "points": [(0.0, 0.0), (5.0, 0.0), (2.5, 4.0)],
                "color": "#118833",
                "alpha": 0.4,
            },
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )

        self.assertEqual(ring.brush().color().name(), "#118833")
        self.assertAlmostEqual(ring.brush().color().alphaF(), 0.4)

    def test_apply_note_state_updates_text_position_and_flags(self) -> None:
        note = QGraphicsTextItem("old")
        note.setData(0, "note")
        style_applier = mock.Mock()

        apply_scene_item_state(
            note,
            {"kind": "note", "text": "Mechanism", "x": 14.0, "y": -9.0},
            model_atoms={},
            note_style_applier=style_applier,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )

        self.assertEqual(note.toPlainText(), "Mechanism")
        self.assertEqual(committed_note_text_for(note), "Mechanism")
        self.assertEqual((note.pos().x(), note.pos().y()), (14.0, -9.0))
        self.assertEqual(
            note.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction
        )
        style_applier.assert_called_once_with(note)

    def test_note_state_sanitizes_resource_bearing_html_on_apply_and_restore(
        self,
    ) -> None:
        unsafe_html = '<p onclick="bad()">Safe<img src="file:///tmp/secret"><script>bad()</script><b>Bold</b></p>'
        style_applier = mock.Mock()
        note = QGraphicsTextItem("old")
        note.setData(0, "note")

        apply_scene_item_state(
            note,
            {
                "kind": "note",
                "text": "fallback",
                "html": unsafe_html,
                "x": 1.0,
                "y": 2.0,
            },
            model_atoms={},
            note_style_applier=style_applier,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )
        restored = create_note_item_from_state(
            {
                "kind": "note",
                "text": "fallback",
                "html": unsafe_html,
                "x": 1.0,
                "y": 2.0,
            },
            note_item_factory=QGraphicsTextItem,
            note_style_applier=lambda item: None,
        )

        for item in (note, restored):
            html = item.toHtml().lower()
            self.assertIn("safe", item.toPlainText().lower())
            self.assertIn("bold", item.toPlainText().lower())
            self.assertNotIn("file://", html)
            self.assertNotIn("<img", html)
            self.assertNotIn("script", html)

    def test_apply_mark_state_updates_metadata_and_prefers_atom_offset_center(
        self,
    ) -> None:
        mark = QGraphicsTextItem("+")
        mark.setData(0, "mark")
        mark.setData(
            1, {"kind": "plus", "atom_id": 1, "dx": 2.0, "dy": -1.0, "text": "+"}
        )
        center_setter = mock.Mock()

        apply_scene_item_state(
            mark,
            {
                "kind": "mark",
                "mark_kind": "minus",
                "atom_id": 3,
                "dx": 5.0,
                "dy": -4.0,
                "text": "-",
                "x": 999.0,
                "y": 999.0,
            },
            model_atoms={3: SimpleNamespace(x=20.0, y=10.0)},
            note_style_applier=lambda item: None,
            mark_center_setter=center_setter,
            mark_color_setter=lambda item, color: None,
        )

        data = mark.data(1)
        self.assertEqual(mark.toPlainText(), "-")
        self.assertEqual(data["kind"], "minus")
        self.assertEqual(data["atom_id"], 3)
        self.assertEqual(data["dx"], 5.0)
        self.assertEqual(data["dy"], -4.0)
        self.assertEqual(data["text"], "-")
        center = center_setter.call_args.args[1]
        self.assertEqual((center.x(), center.y()), (25.0, 6.0))

    def test_mark_center_from_state_falls_back_to_xy_when_atom_data_is_missing(
        self,
    ) -> None:
        center = mark_center_from_state({"atom_id": 8, "x": 7.5, "y": -2.5}, {})

        self.assertEqual((center.x(), center.y()), (7.5, -2.5))
        self.assertIsNone(mark_center_from_state({"atom_id": 1}, {}))

    def test_ts_bracket_rect_from_state_rejects_invalid_coordinates(self) -> None:
        self.assertIsNone(
            ts_bracket_rect_from_state(
                {"left": "bad", "top": 0, "right": 1, "bottom": 2}
            )
        )

    def test_ts_bracket_rect_from_state_rejects_rect_payload(self) -> None:
        rect = ts_bracket_rect_from_state(
            {"kind": "ts_bracket", "rect": (12.0, 8.0, -4.0, -10.0)}
        )

        self.assertIsNone(rect)

    def test_orbital_state_dict_and_apply_restore_transform_metadata(self) -> None:
        item = make_orbital(center=(3.0, -4.0), scale=1.25, rotation=37.0)

        state = scene_item_state(item, mark_center_getter=lambda _: QPointF())

        self.assertEqual(state["kind"], "orbital")
        self.assertEqual(state["orbital_kind"], "s")
        self.assertEqual(state["center"], (3.0, -4.0))

        apply_scene_item_state(
            item,
            {"kind": "orbital", "center": (8.0, 9.0), "scale": 1.5, "rotation": 22.0},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )

        data = item.data(1)
        self.assertEqual((data["center"].x(), data["center"].y()), (8.0, 9.0))
        self.assertEqual(data["base_handle_dist"], 24.0)
        # The group translates by the center delta (3,-4) -> (8,9) so the lobes
        # follow, and the transform origin stays at the lobe center in local
        # coordinates (new center minus the new pos).
        self.assertEqual((item.pos().x(), item.pos().y()), (5.0, 13.0))
        self.assertEqual(
            (item.transformOriginPoint().x(), item.transformOriginPoint().y()),
            (3.0, -4.0),
        )
        self.assertAlmostEqual(item.scale(), 1.5)
        self.assertAlmostEqual(item.rotation(), 22.0)

    def test_apply_orbital_state_translates_group_from_prior_position(self) -> None:
        item = make_orbital(center=(2.0, 0.0), base_handle_dist=18.0)
        item.apply_orbital_state({"center": (10.0, 0.0)})

        apply_scene_item_state(
            item,
            {"kind": "orbital", "center": (0.0, 10.0), "scale": 1.0, "rotation": 90.0},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )

        # Center moves (10,0) -> (0,10): delta (-10,10), so pos (8,0) -> (-2,10).
        # Local lobe center is invariant at center - pos = (2,0).
        self.assertEqual((item.pos().x(), item.pos().y()), (-2.0, 10.0))
        self.assertEqual(
            (item.data(1)["center"].x(), item.data(1)["center"].y()), (0.0, 10.0)
        )
        self.assertEqual(
            (item.transformOriginPoint().x(), item.transformOriginPoint().y()),
            (2.0, 0.0),
        )

    def test_scene_item_state_serializes_note_and_apply_handles_none_or_empty_state(
        self,
    ) -> None:
        note = QGraphicsTextItem("memo")
        note.setData(0, "note")
        note.setPos(QPointF(2.0, -3.0))

        state = scene_item_state(note, mark_center_getter=lambda _: QPointF())

        self.assertEqual(
            {key: state[key] for key in ("kind", "text", "x", "y")},
            {"kind": "note", "text": "memo", "x": 2.0, "y": -3.0},
        )
        self.assertIn("memo", state["html"])

        style_applier = mock.Mock()
        note.setPlainText("unchanged")
        apply_scene_item_state(
            None,
            {"kind": "note", "text": "ignored"},
            model_atoms={},
            note_style_applier=style_applier,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )
        apply_scene_item_state(
            note,
            {},
            model_atoms={},
            note_style_applier=style_applier,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )

        self.assertEqual(note.toPlainText(), "unchanged")
        style_applier.assert_not_called()

    def test_apply_mark_state_handles_non_text_items_none_text_and_missing_center(
        self,
    ) -> None:
        path_mark = QGraphicsPathItem()
        path_mark.setData(
            1, {"kind": "plus", "atom_id": 1, "dx": 2.0, "dy": 3.0, "text": "+"}
        )
        center_setter = mock.Mock()

        apply_scene_item_state(
            path_mark,
            {
                "kind": "mark",
                "mark_kind": "minus",
                "atom_id": 99,
                "dx": 4.0,
                "dy": 5.0,
                "text": "-",
            },
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=center_setter,
            mark_color_setter=lambda item, color: None,
        )

        self.assertEqual(path_mark.data(1)["kind"], "minus")
        self.assertEqual(path_mark.data(1)["text"], "-")
        center_setter.assert_not_called()

        text_mark = QGraphicsTextItem("keep")
        text_mark.setData(1, {"kind": "plus"})
        apply_scene_item_state(
            text_mark,
            {"kind": "mark", "mark_kind": "radical", "atom_id": None, "text": None},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )

        self.assertEqual(text_mark.toPlainText(), "keep")
        self.assertEqual(text_mark.data(1)["kind"], "radical")

    def test_apply_scene_item_state_guard_paths_cover_ring_bracket_orbital_and_arrow(
        self,
    ) -> None:
        ring = make_ring(
            QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)])
        )
        original_polygon = QPolygonF(ring.polygon())
        apply_scene_item_state(
            ring,
            {"kind": "ring", "points": [(0.0, 0.0), (1.0, 1.0)]},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )
        self.assertEqual(len(ring.polygon()), len(original_polygon))
        self.assertEqual(ring.brush().style(), Qt.BrushStyle.NoBrush)

        orbital = make_orbital(center=(1.0, 2.0), base_handle_dist=11.0)
        apply_scene_item_state(
            orbital,
            {"kind": "orbital", "center": None, "scale": 2.0, "rotation": 45.0},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )
        self.assertEqual(
            (orbital.data(1)["center"].x(), orbital.data(1)["center"].y()), (1.0, 2.0)
        )
        self.assertAlmostEqual(orbital.scale(), 2.0)
        self.assertAlmostEqual(orbital.rotation(), 45.0)

        arrow = QGraphicsPathItem()
        arrow.setData(2, {"start": QPointF(1.0, 1.0), "end": QPointF(2.0, 2.0)})
        build_arrow_item = mock.Mock()
        apply_scene_item_state(
            arrow,
            {"kind": "arrow", "start": None, "end": (5.0, 5.0)},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )
        self.assertEqual(
            (arrow.data(2)["start"].x(), arrow.data(2)["start"].y()), (1.0, 1.0)
        )
        build_arrow_item.assert_not_called()

        text_item = QGraphicsTextItem("x")
        apply_scene_item_state(
            text_item,
            {"kind": "arrow", "start": (0.0, 0.0), "end": (1.0, 1.0)},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            mark_color_setter=lambda item, color: None,
        )
        self.assertEqual(text_item.toPlainText(), "x")
