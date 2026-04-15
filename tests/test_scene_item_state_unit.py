import os
import sys
import unittest
from pathlib import Path
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


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
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
        self.assertEqual(note._last_text, "Mechanism")
        self.assertEqual((note.pos().x(), note.pos().y()), (14.0, -9.0))
        self.assertEqual(note.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)
        style_applier.assert_called_once_with(note)

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
        path = QPainterPath()
        path.addRect(QRectF(-6.0, -4.0, 12.0, 10.0))
        item.setPath(path)
        item.setPen(QPen(Qt.PenStyle.NoPen))

        state = scene_item_state(item, mark_center_getter=lambda _: QPointF())

        self.assertEqual(state["kind"], "ts_bracket")
        self.assertLess(state["left"], state["right"])
        self.assertLess(state["top"], state["bottom"])
        self.assertIsNone(ts_bracket_rect_from_state({"left": "bad", "top": 0, "right": 1, "bottom": 2}))

    def test_apply_ts_bracket_state_sets_path_pen_brush_and_metadata(self) -> None:
        item = QGraphicsPathItem()
        built_paths: list[QPainterPath] = []

        def build_path(rect: QRectF) -> QPainterPath:
            path = QPainterPath()
            path.addRect(rect)
            built_paths.append(path)
            return path

        apply_scene_item_state(
            item,
            {"kind": "ts_bracket", "left": -8.0, "top": -3.0, "right": 9.0, "bottom": 6.0},
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
        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(item.brush().color().name(), "#123456")
        self.assertTrue(built_paths)

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
