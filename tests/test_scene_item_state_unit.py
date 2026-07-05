import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItemGroup,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None
    QPointF = None
    QRectF = None
    Qt = None

if QApplication is not None:
    from ui.note_item_access import committed_note_text_for
    from ui.scene_item_restore import create_note_item_from_state
    from ui.scene_item_state import (
        apply_scene_item_state,
        arrow_state_dict,
        mark_center_from_state,
        scene_item_state,
        ts_bracket_rect_from_state,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene item state tests")
class SceneItemStateUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_scene_item_state_returns_empty_for_none_and_unknown_kind(self) -> None:
        item = QGraphicsTextItem("unknown")

        self.assertEqual(scene_item_state(None, mark_center_getter=lambda _: QPointF()), {})
        self.assertEqual(scene_item_state(item, mark_center_getter=lambda _: QPointF()), {})

    def test_scene_item_state_serializes_ring_and_apply_restores_fallback_brush(self) -> None:
        ring = QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)]))
        ring.setData(0, "ring")
        ring.setData(2, (7, 8, 9))
        ring.setBrush(QColor("#336699"))
        brush = ring.brush()
        brush.setStyle(Qt.BrushStyle.SolidPattern)
        brush.setColor(QColor("#336699"))
        brush.setColor(QColor(51, 102, 153, 128))
        ring.setBrush(brush)

        state = scene_item_state(ring, mark_center_getter=lambda _: QPointF())

        self.assertEqual(state["kind"], "ring")
        self.assertEqual(state["atom_ids"], (7, 8, 9))
        self.assertEqual(state["color"], "#336699")
        self.assertAlmostEqual(state["alpha"], 128 / 255)

        ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        apply_scene_item_state(
            ring,
            {"kind": "ring", "points": [(0.0, 0.0), (6.0, 0.0), (3.0, 4.0)]},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )

        self.assertEqual(ring.brush().color().name(), "#aa4400")
        self.assertEqual(len(ring.polygon()), 3)

    def test_apply_ring_state_prefers_explicit_color_and_alpha(self) -> None:
        ring = QGraphicsPolygonItem()

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
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
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
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )

        self.assertEqual(note.toPlainText(), "Mechanism")
        self.assertEqual(committed_note_text_for(note), "Mechanism")
        self.assertEqual((note.pos().x(), note.pos().y()), (14.0, -9.0))
        self.assertEqual(note.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)
        style_applier.assert_called_once_with(note)

    def test_note_state_sanitizes_resource_bearing_html_on_apply_and_restore(self) -> None:
        unsafe_html = '<p onclick="bad()">Safe<img src="file:///tmp/secret"><script>bad()</script><b>Bold</b></p>'
        style_applier = mock.Mock()
        note = QGraphicsTextItem("old")
        note.setData(0, "note")

        apply_scene_item_state(
            note,
            {"kind": "note", "text": "fallback", "html": unsafe_html, "x": 1.0, "y": 2.0},
            model_atoms={},
            note_style_applier=style_applier,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )
        restored = create_note_item_from_state(
            {"kind": "note", "text": "fallback", "html": unsafe_html, "x": 1.0, "y": 2.0},
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

    def test_apply_mark_state_updates_metadata_and_prefers_atom_offset_center(self) -> None:
        mark = QGraphicsTextItem("+")
        mark.setData(0, "mark")
        mark.setData(1, {"kind": "plus", "atom_id": 1, "dx": 2.0, "dy": -1.0, "text": "+"})
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
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
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

    def test_mark_center_from_state_falls_back_to_xy_when_atom_data_is_missing(self) -> None:
        center = mark_center_from_state({"atom_id": 8, "x": 7.5, "y": -2.5}, {})

        self.assertEqual((center.x(), center.y()), (7.5, -2.5))
        self.assertIsNone(mark_center_from_state({"atom_id": 1}, {}))

    def test_ts_bracket_helpers_use_fallback_bounds_and_validate_state(self) -> None:
        item = QGraphicsPathItem()
        item.setData(0, "ts_bracket")
        item.setData(1, {"rect": QRectF(-6.0, -4.0, 12.0, 10.0), "bracket_kind": "brace_left"})
        path = QPainterPath()
        path.addRect(QRectF(-6.0, -4.0, 12.0, 10.0))
        item.setPath(path)
        item.setPen(QPen(Qt.PenStyle.NoPen))

        state = scene_item_state(item, mark_center_getter=lambda _: QPointF())

        self.assertEqual(state["kind"], "ts_bracket")
        self.assertEqual(state["bracket_kind"], "brace_left")
        self.assertLess(state["left"], state["right"])
        self.assertLess(state["top"], state["bottom"])
        self.assertIsNone(ts_bracket_rect_from_state({"left": "bad", "top": 0, "right": 1, "bottom": 2}))

    def test_ts_bracket_rect_from_state_restores_legacy_rect_payload(self) -> None:
        rect = ts_bracket_rect_from_state(
            {"kind": "ts_bracket", "rect": (12.0, 8.0, -4.0, -10.0)}
        )

        self.assertIsNotNone(rect)
        self.assertEqual(
            (rect.left(), rect.top(), rect.right(), rect.bottom()),
            (8.0, -2.0, 12.0, 8.0),
        )

    def test_apply_ts_bracket_state_sets_path_pen_brush_and_metadata(self) -> None:
        item = QGraphicsPathItem()
        built_paths: list[QPainterPath] = []

        built_kinds: list[str] = []

        def build_path(rect: QRectF, bracket_kind: str) -> QPainterPath:
            path = QPainterPath()
            path.addRect(rect)
            built_paths.append(path)
            built_kinds.append(bracket_kind)
            return path

        apply_scene_item_state(
            item,
            {
                "kind": "ts_bracket",
                "left": -8.0,
                "top": -3.0,
                "right": 9.0,
                "bottom": 6.0,
                "bracket_kind": "parentheses_pair",
            },
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=build_path,
            bond_color="#123456",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )

        rect = item.data(1)["rect"]
        self.assertEqual((rect.left(), rect.top(), rect.right(), rect.bottom()), (-8.0, -3.0, 9.0, 6.0))
        self.assertEqual(item.data(1)["bracket_kind"], "parentheses_pair")
        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(item.brush().color().name(), "#123456")
        self.assertTrue(built_paths)
        self.assertEqual(built_kinds, ["parentheses_pair"])

    def test_orbital_state_dict_and_apply_restore_transform_metadata(self) -> None:
        item = QGraphicsItemGroup()
        item.setData(0, "orbital")
        item.setData(1, {"center": QPointF(3.0, -4.0)})
        item.setScale(1.25)
        item.setRotation(37.0)

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
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=24.0,
        )

        data = item.data(1)
        self.assertEqual((data["center"].x(), data["center"].y()), (8.0, 9.0))
        self.assertEqual(data["base_handle_dist"], 24.0)
        self.assertEqual((item.transformOriginPoint().x(), item.transformOriginPoint().y()), (8.0, 9.0))
        self.assertAlmostEqual(item.scale(), 1.5)
        self.assertAlmostEqual(item.rotation(), 22.0)

    def test_arrow_state_helpers_handle_missing_points_and_straight_rebuild(self) -> None:
        item = QGraphicsPathItem()
        item.setData(0, "arrow")
        item.setData(2, {"start": "bad", "end": None, "control": None, "double": 1})

        state = arrow_state_dict(item)

        self.assertEqual(state["kind"], "arrow")
        self.assertIsNone(state["start"])
        self.assertIsNone(state["end"])
        self.assertTrue(state["double"])

        rebuilt = QGraphicsPathItem()
        rebuilt_path = QPainterPath()
        rebuilt_path.moveTo(1.0, 2.0)
        rebuilt_path.lineTo(6.0, 7.0)
        rebuilt.setPath(rebuilt_path)
        rebuilt.setPen(QPen(QColor("#224466")))
        rebuilt.setBrush(QBrush(QColor("#335577")))
        build_arrow_item = mock.Mock(return_value=rebuilt)

        apply_scene_item_state(
            item,
            {"kind": "equilibrium", "start": (1.0, 2.0), "end": (6.0, 7.0), "double": False},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=build_arrow_item,
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )

        data = item.data(2)
        self.assertEqual(item.data(0), "equilibrium")
        self.assertEqual((data["start"].x(), data["start"].y()), (1.0, 2.0))
        self.assertEqual((data["end"].x(), data["end"].y()), (6.0, 7.0))
        self.assertIsNone(data["control"])
        self.assertEqual(item.pen().color().name(), "#224466")
        self.assertEqual(item.brush().color().name(), "#335577")
        build_arrow_item.assert_called_once()

    def test_apply_curved_arrow_state_uses_curve_setter(self) -> None:
        item = QGraphicsPathItem()
        item.setData(0, "curved_double")
        set_curved_arrow_path = mock.Mock()
        build_arrow_item = mock.Mock()

        apply_scene_item_state(
            item,
            {
                "kind": "curved_double",
                "start": (-4.0, 0.0),
                "end": (4.0, 0.0),
                "control": (0.0, 6.0),
                "double": True,
            },
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=build_arrow_item,
            set_curved_arrow_path=set_curved_arrow_path,
            orbital_base_handle_dist=18.0,
        )

        data = item.data(2)
        self.assertEqual(item.data(0), "curved_double")
        self.assertEqual((data["control"].x(), data["control"].y()), (0.0, 6.0))
        self.assertTrue(data["double"])
        set_curved_arrow_path.assert_called_once()
        build_arrow_item.assert_not_called()

    def test_scene_item_state_serializes_note_and_apply_handles_none_or_empty_state(self) -> None:
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
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )
        apply_scene_item_state(
            note,
            {},
            model_atoms={},
            note_style_applier=style_applier,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )

        self.assertEqual(note.toPlainText(), "unchanged")
        style_applier.assert_not_called()

    def test_apply_mark_state_handles_non_text_items_none_text_and_missing_center(self) -> None:
        path_mark = QGraphicsPathItem()
        path_mark.setData(1, {"kind": "plus", "atom_id": 1, "dx": 2.0, "dy": 3.0, "text": "+"})
        center_setter = mock.Mock()

        apply_scene_item_state(
            path_mark,
            {"kind": "mark", "mark_kind": "minus", "atom_id": 99, "dx": 4.0, "dy": 5.0, "text": "-"},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=center_setter,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
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
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )

        self.assertEqual(text_mark.toPlainText(), "keep")
        self.assertEqual(text_mark.data(1)["kind"], "radical")

    def test_apply_scene_item_state_guard_paths_cover_ring_bracket_orbital_and_arrow(self) -> None:
        ring = QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)]))
        original_polygon = QPolygonF(ring.polygon())
        apply_scene_item_state(
            ring,
            {"kind": "ring", "points": [(0.0, 0.0), (1.0, 1.0)]},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#55AA11")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )
        self.assertEqual(len(ring.polygon()), len(original_polygon))
        self.assertEqual(ring.brush().color().name(), "#55aa11")

        bracket = QGraphicsPathItem()
        path_builder = mock.Mock()
        apply_scene_item_state(
            bracket,
            {"kind": "ts_bracket", "left": "bad", "top": 0.0, "right": 1.0, "bottom": 2.0},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=path_builder,
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )
        path_builder.assert_not_called()

        orbital = QGraphicsItemGroup()
        orbital.setData(1, {"center": QPointF(1.0, 2.0), "base_handle_dist": 11.0})
        apply_scene_item_state(
            orbital,
            {"kind": "orbital", "center": None, "scale": 2.0, "rotation": 45.0},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=lambda start, end, kind: QGraphicsPathItem(),
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=24.0,
        )
        self.assertEqual((orbital.data(1)["center"].x(), orbital.data(1)["center"].y()), (1.0, 2.0))
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
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=build_arrow_item,
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )
        self.assertEqual((arrow.data(2)["start"].x(), arrow.data(2)["start"].y()), (1.0, 1.0))
        build_arrow_item.assert_not_called()

        text_item = QGraphicsTextItem("x")
        apply_scene_item_state(
            text_item,
            {"kind": "arrow", "start": (0.0, 0.0), "end": (1.0, 1.0)},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#AA4400")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=build_arrow_item,
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
        )
        self.assertEqual(text_item.toPlainText(), "x")
